"""
PLC Variable Scanner
Scans B&R Automation Studio project (.var and .typ files) to find all
global struct-typed variables and recursively resolve them to leaf fields.

Outputs:
  - Summary of struct variables found
  - Total leaf field count
  - JSON registry mapping every flat path to its primitive type
"""

import re
import os
import json
from pathlib import Path
from collections import defaultdict

# ─── Configuration ───────────────────────────────────────────────────────
PLC_ROOT = Path(r"C:\Work\Indigo\As45\SimulatorMainBranch\PLC-plc")
LOGICAL_DIR = PLC_ROOT / "Logical"

# B&R primitive types (not structs, not enums with _typ suffix)
PRIMITIVE_TYPES = {
    "BOOL", "USINT", "SINT", "UINT", "INT", "UDINT", "DINT",
    "REAL", "LREAL", "STRING", "BYTE", "WORD", "DWORD",
    "TIME", "DATE", "DATE_AND_TIME", "TOD", "ULINT", "LINT",
}

# Types to skip (very large B&R axis/SDC types - not your application data)
SKIP_TYPES = {
    "ACP10AXIS_typ", "ACP10VAXIS_typ",
    "SdcHwCfg_typ", "SdcDrvIf16_typ", "SdcEncIf16_typ", "SdcDiDoIf_typ",
    "ACPiModuleX64_type",
}

# ─── Parsing ─────────────────────────────────────────────────────────────

# Regex patterns
RE_VAR_DECL = re.compile(
    r'^\s+(\w+)\s*:\s*'            # variable name
    r'(\w+_typ\w*|CSIO_type)\s*'   # type name (ending in _typ or known types)
    r'(?::=\s*\([^)]*\))?\s*;',    # optional initialization
    re.IGNORECASE
)

RE_STRUCT_START = re.compile(
    r'^\s*(\w+)\s*:\s*STRUCT\s*$', re.IGNORECASE
)

RE_STRUCT_FIELD = re.compile(
    r'^\s+(\w+)\s*:\s*'                               # field name
    r'(ARRAY\s*\[.*?\]\s*OF\s+)?'                      # optional array prefix
    r'(\w+)'                                            # type
    r'(?:\s*\[.*?\])?'                                  # optional string length
    r'\s*(?::=\s*[^;]*)?\s*;',                         # optional init
    re.IGNORECASE
)

RE_END_STRUCT = re.compile(r'^\s*END_STRUCT\s*;', re.IGNORECASE)
RE_TYPE_BLOCK = re.compile(r'^TYPE\s*$', re.IGNORECASE)
RE_END_TYPE = re.compile(r'^END_TYPE\s*$', re.IGNORECASE)

RE_ENUM_START = re.compile(
    r'^\s*(\w+)\s*:\s*$', re.IGNORECASE  # enum type name followed by (
)

RE_VAR_BLOCK = re.compile(r'^VAR\b', re.IGNORECASE)
RE_END_VAR = re.compile(r'^END_VAR', re.IGNORECASE)

# More flexible var declaration for struct types
RE_VAR_STRUCT = re.compile(
    r'^\s+(\w+)\s*:\s*'           # variable name
    r'(?:\{[^}]*\}\s*)?'          # optional pragmas like {REDUND_UNREPLICABLE}
    r'([\w]+)'                     # type name
    r'(?:\s*\[.*?\])?'            # optional string length
    r'\s*(?::=\s*[^;]*)?\s*;',    # optional init
    re.IGNORECASE
)


def is_primitive(type_name: str) -> bool:
    """Check if a type is a primitive B&R type."""
    base = type_name.upper()
    # Handle STRING[n]
    if base.startswith("STRING"):
        return True
    return base in PRIMITIVE_TYPES


def is_enum(type_name: str, enums: set) -> bool:
    """Check if type is a known enum."""
    return type_name in enums


def _typ_file_depth(typ_file: Path, logical_dir: Path) -> int:
    """Return the depth of a .typ file relative to logical_dir. Shallower = more global."""
    return len(typ_file.relative_to(logical_dir).parts)


def parse_typ_files(logical_dir: Path) -> tuple[dict, set]:
    """
    Parse all .typ files under Logical/ to build a type registry.
    Returns: (struct_registry, enum_set)
    
    struct_registry: { "TypeName": [ (field_name, field_type, is_array), ... ] }
    enum_set: set of enum type names

    When the same type is defined in multiple .typ files, the definition from the
    SHALLOWER (more global) file takes precedence, because sub-package 'Interface'
    files can redefine types with extra/different fields that the compiler ignores.
    """
    structs = {}
    enums = set()
    # Track which file each type was defined in (to prefer shallower definitions)
    struct_source_depth: dict[str, int] = {}

    typ_files = list(logical_dir.rglob("*.typ"))
    # Sort by depth (shallowest first) so shallower definitions are stored first;
    # deeper definitions will only override if type not yet seen.
    typ_files.sort(key=lambda f: _typ_file_depth(f, logical_dir))
    print(f"Found {len(typ_files)} .typ files")
    
    for typ_file in typ_files:
        try:
            content = typ_file.read_text(encoding='utf-8', errors='replace')
        except Exception:
            continue
            
        lines = content.split('\n')
        i = 0
        in_type_block = False
        
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()
            
            # Remove comments
            # Handle (* ... *) comments (can span lines but usually inline)
            cleaned = re.sub(r'\(\*.*?\*\)', '', stripped)
            
            # Check for STRUCT definition
            # Pattern: TypeName : STRUCT
            m = re.match(r'^(\w+)\s*:\s*STRUCT\s*$', cleaned, re.IGNORECASE)
            if m:
                type_name = m.group(1)
                fields = []
                i += 1
                
                while i < len(lines):
                    fline = lines[i].strip()
                    fline_clean = re.sub(r'\(\*.*?\*\)', '', fline)
                    
                    if re.match(r'^END_STRUCT\s*;?', fline_clean, re.IGNORECASE):
                        break
                    
                    # Parse field: name : [ARRAY[...] OF] type [:= init];
                    fm = re.match(
                        r'^(\w+)\s*:\s*'
                        r'(ARRAY\s*\[.*?\]\s*OF\s+)?'
                        r'(\w+)'
                        r'(?:\s*\[.*?\])?'   # string length
                        r'\s*(?::=\s*[^;]*)?\s*;',
                        fline_clean, re.IGNORECASE
                    )
                    if fm:
                        fname = fm.group(1)
                        is_array = fm.group(2) is not None
                        ftype = fm.group(3)
                        fields.append((fname, ftype, is_array))
                    
                    i += 1
                
                current_depth = _typ_file_depth(typ_file, logical_dir)
                # Only store if not yet defined, or if this file is at same/shallower depth
                if (type_name not in structs or
                        current_depth <= struct_source_depth.get(type_name, 999)):
                    structs[type_name] = fields
                    struct_source_depth[type_name] = current_depth
                i += 1
                continue
            
            # Check for enum definition
            # Pattern: TypeName : \n ( ... );
            em = re.match(r'^(\w+)\s*:\s*$', cleaned)
            if em and i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                if next_line.startswith('('):
                    enums.add(em.group(1))
                    # Skip to end of enum
                    while i < len(lines) and ')' not in lines[i]:
                        i += 1
            
            i += 1
    
    return structs, enums


def is_private_var_file(var_file: Path) -> bool:
    """Check if a .var file is marked Private='true' in its Package.pkg."""
    pkg_file = var_file.parent / 'Package.pkg'
    if not pkg_file.exists():
        return False
    try:
        content = pkg_file.read_text(encoding='utf-8', errors='replace')
        fname = var_file.name
        for m in re.finditer(r'(<Object[^>]*>)([^<]+)(</Object>)', content):
            tag_attr = m.group(1)
            tag_text = m.group(2).strip()
            if tag_text == fname and 'Private="true"' in tag_attr:
                return True
    except Exception:
        pass
    return False


def parse_var_files(logical_dir: Path) -> list[tuple[str, str, str]]:
    """
    Parse all .var files under Logical/ to find global struct-typed variables.
    Only picks up variables whose type ends with _typ or _type.
    Skips .var files marked Private="true" in their Package.pkg.
    
    Returns: [ (var_name, type_name, source_file), ... ]
    """
    results = []
    
    # Focus on "Global" level .var files (not local task vars)
    # These are files directly under Logical/ or *Global*.var or *Interface*.var
    var_files = list(logical_dir.rglob("*.var"))
    print(f"Found {len(var_files)} .var files total")
    
    # Filter to global-scope files
    global_var_files = []
    private_skipped = 0
    for vf in var_files:
        name = vf.name.lower()
        # Include: Global.var, GIOGlobal.var, *Global*.var, *_Globals.var, *Interface*.var
        # Also include top-level package var files
        rel = vf.relative_to(logical_dir)
        parts = str(rel).lower()
        
        if ('global' in name or 
            name in ('global.var', 'gioglobal.var', 'global_whs.var', 'version.var') or
            'interface' in name or
            # Top-level Logical/*.var
            vf.parent == logical_dir):
            # Skip var files marked Private="true" in their Package.pkg
            if is_private_var_file(vf):
                private_skipped += 1
                continue
            global_var_files.append(vf)
    
    print(f"Skipped {private_skipped} private var files")
    
    print(f"Filtered to {len(global_var_files)} global-scope .var files (excluding {private_skipped} private)")
    
    for var_file in global_var_files:
        try:
            content = var_file.read_text(encoding='utf-8', errors='replace')
        except Exception:
            continue
        
        in_var_block = False
        for line in content.split('\n'):
            stripped = line.strip()
            cleaned = re.sub(r'\(\*.*?\*\)', '', stripped)
            
            if re.match(r'^VAR\b', cleaned, re.IGNORECASE):
                in_var_block = True
                continue
            if re.match(r'^END_VAR', cleaned, re.IGNORECASE):
                in_var_block = False
                continue
            
            if not in_var_block:
                continue
            
            # Match variable declarations with struct types
            m = re.match(
                r'^(\w+)\s*:\s*'
                r'(?:\{[^}]*\}\s*)?'    # optional pragmas
                r'(\w+)'                  # type name
                r'(?:\s*\[.*?\])?'        # optional string length  
                r'\s*(?::=\s*[^;]*)?\s*;',
                cleaned, re.IGNORECASE
            )
            if m:
                var_name = m.group(1)
                type_name = m.group(2)
                
                # Only include struct types (end with _typ or _type)
                if (re.search(r'_typ\w*$', type_name, re.IGNORECASE) or 
                    type_name.lower().endswith('_type')):
                    
                    # Skip axis/drive types (too large, not app data)
                    if type_name in SKIP_TYPES:
                        continue
                    
                    rel_path = str(var_file.relative_to(logical_dir))
                    results.append((var_name, type_name, rel_path))
    
    return results


def flatten_struct(var_path: str, type_name: str, structs: dict, enums: set,
                   depth: int = 0, visited: set = None) -> list[tuple[str, str]]:
    """
    Recursively flatten a struct variable into leaf paths.
    Returns: [ ("gExit.In.Cmd.Stop", "BOOL"), ... ]
    """
    if visited is None:
        visited = set()
    
    if depth > 15 or type_name in visited:
        return [(var_path, f"<recursive:{type_name}>")]
    
    visited = visited | {type_name}
    
    if is_primitive(type_name):
        return [(var_path, type_name)]
    
    if type_name in enums:
        return [(var_path, f"ENUM({type_name})")]
    
    if type_name not in structs:
        # Unknown type — treat as opaque
        return [(var_path, f"<unknown:{type_name}>")]
    
    result = []
    for field_name, field_type, is_array in structs[type_name]:
        child_path = f"{var_path}.{field_name}"
        
        if is_array:
            # For arrays, just note it as array — don't enumerate indices
            if is_primitive(field_type):
                result.append((child_path, f"ARRAY OF {field_type}"))
            elif field_type in structs:
                # Array of structs — show [i] pattern
                result.append((child_path + "[i]", f"ARRAY OF {field_type}"))
                # Also expand one element's fields for reference
                sub = flatten_struct(child_path + "[0]", field_type, structs, enums, depth + 1, visited)
                result.extend(sub)
            else:
                result.append((child_path, f"ARRAY OF {field_type}"))
        else:
            sub = flatten_struct(child_path, field_type, structs, enums, depth + 1, visited)
            result.extend(sub)
    
    return result


def main():
    print("=" * 70)
    print("PLC Global Struct Variable Scanner")
    print("=" * 70)
    print(f"\nScanning: {LOGICAL_DIR}\n")
    
    # Step 1: Parse all type definitions
    print("─── Step 1: Parsing .typ files ───")
    structs, enums = parse_typ_files(LOGICAL_DIR)
    print(f"  Parsed {len(structs)} struct types")
    print(f"  Found {len(enums)} enum types\n")
    
    # Step 2: Find all global struct variables
    print("─── Step 2: Finding global struct variables ───")
    global_vars = parse_var_files(LOGICAL_DIR)
    print(f"  Found {len(global_vars)} struct-typed global variables\n")
    
    # Step 3: Flatten all structs to leaf fields
    print("─── Step 3: Resolving struct fields ───")
    
    all_leaves = []
    var_summary = []
    unresolved_types = set()
    
    for var_name, type_name, source_file in global_vars:
        leaves = flatten_struct(var_name, type_name, structs, enums)
        
        # Count only resolved leaves (not unknown/recursive)
        resolved = [(p, t) for p, t in leaves if not t.startswith("<")]
        unresolved = [(p, t) for p, t in leaves if t.startswith("<unknown:")]
        
        for _, t in unresolved:
            m = re.search(r'<unknown:(\w+)>', t)
            if m:
                unresolved_types.add(m.group(1))
        
        all_leaves.extend(resolved)
        
        var_summary.append({
            "variable": var_name,
            "type": type_name,
            "source": source_file,
            "leaf_count": len(resolved),
            "unresolved_count": len(unresolved),
        })
    
    # Sort by leaf count descending
    var_summary.sort(key=lambda x: x["leaf_count"], reverse=True)
    
    # ─── Report ──────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("RESULTS")
    print("=" * 70)
    
    print(f"\n{'Variable':<40} {'Type':<35} {'Fields':>7}  Source")
    print("─" * 120)
    
    for v in var_summary:
        if v["leaf_count"] > 0:
            unr = f" (+{v['unresolved_count']} unres)" if v["unresolved_count"] > 0 else ""
            print(f"  {v['variable']:<38} {v['type']:<35} {v['leaf_count']:>5}{unr}  {v['source']}")
    
    total_leaves = len(all_leaves)
    print(f"\n{'─' * 70}")
    print(f"TOTAL: {len(var_summary)} struct variables → {total_leaves} leaf fields")
    
    if unresolved_types:
        print(f"\nUnresolved types ({len(unresolved_types)}):")
        for ut in sorted(unresolved_types)[:20]:
            print(f"  - {ut}")
        if len(unresolved_types) > 20:
            print(f"  ... and {len(unresolved_types) - 20} more")
    
    # ─── Type distribution ───────────────────────────────────────────
    print(f"\n{'─' * 70}")
    print("LEAF TYPE DISTRIBUTION:")
    type_counts = defaultdict(int)
    for _, t in all_leaves:
        # Normalize
        base = t.split("(")[0] if t.startswith("ENUM") else t.split(" OF ")[-1] if "ARRAY" in t else t
        type_counts[base] += 1
    
    for t, c in sorted(type_counts.items(), key=lambda x: -x[1]):
        print(f"  {t:<20} {c:>6}")
    
    # ─── Save full registry ──────────────────────────────────────────
    registry = {}
    for path, typ in all_leaves:
        registry[path] = typ
    
    output_file = Path(__file__).parent / "plc_var_registry.json"
    with open(output_file, 'w') as f:
        json.dump(registry, f, indent=2, sort_keys=True)
    
    print(f"\nFull registry saved to: {output_file}")
    print(f"Total entries: {len(registry)}")
    
    # Also save summary
    summary_file = Path(__file__).parent / "plc_var_summary.json"
    with open(summary_file, 'w') as f:
        json.dump({
            "total_struct_variables": len(var_summary),
            "total_leaf_fields": total_leaves,
            "variables": var_summary,
        }, f, indent=2)
    
    print(f"Summary saved to: {summary_file}")


if __name__ == "__main__":
    main()
