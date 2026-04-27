"""
Generate plc_var_registry.json by reading the already-generated PLC
VarMon_RegInit_*.st files.  This guarantees the Python-side var_id
assignments are identical to the PLC's vmRegistry[] indices.

Usage:
    python plc_registry_from_st.py
"""

import json
import re
import sys
from pathlib import Path

# ── Configuration ────────────────────────────────────────────────────────────
ST_DIR = Path(r"C:\Work\Indigo\As45\SimulatorMainBranch\PLC-plc\Logical\Simulation\VarMonitor")
OUTPUT  = Path(__file__).parent / "plc_var_registry.json"

# B&R typeCode → human-readable name (matches plc_engine.py constants)
TYPE_NAMES = {
    0: "BOOL",
    1: "INT",
    2: "UINT",
    3: "DINT",
    4: "UDINT",
    5: "REAL",
    6: "LREAL",
    7: "STRING",
    8: "USINT",
    9: "SINT",
}

# Regexes
RE_ADDR = re.compile(
    r'vmRegistry\[(\d+)\]\.pAddress\s*:=\s*ADR\(([^)]+)\)\s*;'
)
RE_TYPE = re.compile(
    r'vmRegistry\[(\d+)\]\.typeCode\s*:=\s*(\d+)\s*;'
)

def main():
    st_files = sorted(ST_DIR.glob("VarMon_RegInit_*.st"))
    if not st_files:
        print(f"No VarMon_RegInit_*.st files found in {ST_DIR}", file=sys.stderr)
        sys.exit(1)

    # Collect (index, var_name, typeCode) from all files
    entries: dict[int, dict] = {}   # index → {"name": ..., "typeCode": ...}

    for st_file in st_files:
        text = st_file.read_text(encoding="utf-8", errors="replace")

        # Build a map: index → var_name from pAddress lines
        for m in RE_ADDR.finditer(text):
            idx  = int(m.group(1))
            name = m.group(2).strip()
            entries.setdefault(idx, {})["name"] = name

        # Fill in typeCode
        for m in RE_TYPE.finditer(text):
            idx       = int(m.group(1))
            type_code = int(m.group(2))
            entries.setdefault(idx, {})["typeCode"] = type_code

    if not entries:
        print("No registry entries found.", file=sys.stderr)
        sys.exit(1)

    # Build dict keyed by PLC index to preserve exact var_id mapping
    max_idx  = max(entries)
    registry = {}   # str(plc_index) → {"name": ..., "type": ...}

    missing_type = 0
    for idx in sorted(entries):
        entry = entries[idx]
        if "name" not in entry:
            continue
        type_code  = entry.get("typeCode", 4)   # default UDINT if missing
        plc_type   = TYPE_NAMES.get(type_code, f"UNKNOWN_{type_code}")
        if "typeCode" not in entry:
            missing_type += 1
        registry[str(idx)] = {"name": entry["name"], "type": plc_type}

    OUTPUT.write_text(json.dumps(registry, indent=None), encoding="utf-8")

    print(f"Extracted {len(registry)} variables (max index {max_idx})")
    print(f"  {missing_type} entries had no typeCode line (defaulted to UDINT)")
    print(f"Saved → {OUTPUT}")

if __name__ == "__main__":
    main()
