"""
Fix VarMonitor registry to remove subsystems with private/inaccessible variables.
Also fixes the CSDriveStatus ACTION name mismatch.
"""
import re
from pathlib import Path

LOGICAL_DIR = Path(r'C:\Work\Indigo\As45\SimulatorMainBranch\PLC-plc\Logical')
VARMON_DIR = Path(r'C:\Work\Indigo\As45\SimulatorMainBranch\PLC-plc\Logical\Simulation\VarMonitor')


def is_private_var_file(var_file: Path) -> bool:
    """Check if a .var file is marked Private='true' in its Package.pkg."""
    pkg_file = var_file.parent / 'Package.pkg'
    if not pkg_file.exists():
        return False
    try:
        content = pkg_file.read_text(encoding='utf-8', errors='replace')
        fname = var_file.name
        # Find Object tags and check for Private="true" alongside the filename
        for m in re.finditer(r'(<Object[^>]*>)([^<]+)(</Object>)', content):
            tag_attr = m.group(1)
            tag_text = m.group(2).strip()
            if tag_text == fname and 'Private="true"' in tag_attr:
                return True
    except Exception:
        pass
    return False


def build_accessible_roots() -> set:
    """Build set of root variable names from non-private global .var files."""
    global_roots = set()
    private_count = 0
    total = 0
    for vf in LOGICAL_DIR.rglob('*.var'):
        total += 1
        if is_private_var_file(vf):
            private_count += 1
            continue
        try:
            content = vf.read_text(encoding='utf-8', errors='replace')
            in_var = False
            for line in content.splitlines():
                s = line.strip()
                if re.match(r'^VAR\b', s, re.I):
                    in_var = True
                elif re.match(r'^END_VAR', s, re.I):
                    in_var = False
                elif in_var:
                    mm = re.match(r'^(\w+)\s*:', s)
                    if mm:
                        global_roots.add(mm.group(1))
        except Exception:
            pass
    print(f'  Scanned {total} .var files, {private_count} private, {len(global_roots)} accessible root vars')
    return global_roots


def find_bad_subsystems(accessible_roots: set):
    """
    Find all VarMon_RegInit_*.st files where the root variable is not accessible.
    Returns list of (file_stem, action_name, root_var) for bad subsystems.
    """
    bad = []
    # Also check for duplicate dispatcher entries (CSDriveStatus issue)
    all_actions_by_root = {}  # root_var -> list of (file_stem, action_name)

    for st_file in sorted(VARMON_DIR.glob('VarMon_RegInit_*.st')):
        if st_file.name == 'VarMon_RegInit.st':
            continue
        content = st_file.read_text(encoding='utf-8', errors='replace')
        am = re.search(r'ACTION\s+(VarMon_RegInit_\w+)', content)
        if not am:
            continue
        action_name = am.group(1)
        adr_m = re.search(r'ADR\((\w+)\.', content)
        root_var = adr_m.group(1) if adr_m else None

        if root_var:
            if root_var not in all_actions_by_root:
                all_actions_by_root[root_var] = []
            all_actions_by_root[root_var].append((st_file.stem, action_name))

            if root_var not in accessible_roots:
                bad.append((st_file.stem, action_name, root_var))

    return bad, all_actions_by_root


def fix_dispatcher_and_iecprg(bad_subsystems, all_actions_by_root):
    """
    Remove bad subsystem calls from VarMon_RegInit.st (dispatcher).
    Remove bad subsystem entries from IEC.prg.
    Also fix CSDriveStatus duplicate: remove the non-existent ACTION name call.
    """
    dispatcher_path = VARMON_DIR / 'VarMon_RegInit.st'
    iec_prg_path = VARMON_DIR / 'IEC.prg'

    dispatcher = dispatcher_path.read_text(encoding='utf-8')
    iec_prg = iec_prg_path.read_text(encoding='utf-8')

    removed_dispatcher = 0
    removed_iec = 0

    # Build set of action names to REMOVE from dispatcher
    actions_to_remove = set()

    # 1. Bad subsystems (private/inaccessible vars) - remove their action calls
    for file_stem, action_name, root_var in bad_subsystems:
        actions_to_remove.add(action_name)
        print(f'  Removing {action_name} (inaccessible: {root_var})')

    # 2. Fix CSDriveStatus mismatch: file is VarMon_RegInit_CSDriveStatus.st
    #    but ACTION inside is VarMon_RegInit_csDriveStatus
    #    Dispatcher has BOTH calls → remove VarMon_RegInit_CSDriveStatus (the non-existent one)
    csd_file = VARMON_DIR / 'VarMon_RegInit_CSDriveStatus.st'
    if csd_file.exists():
        csd_content = csd_file.read_text(encoding='utf-8', errors='replace')
        am = re.search(r'ACTION\s+(VarMon_RegInit_\w+)', csd_content)
        if am:
            actual_action = am.group(1)  # e.g. VarMon_RegInit_csDriveStatus
            # Check if dispatcher also calls the capitalized version
            cap_action = 'VarMon_RegInit_CSDriveStatus'
            if cap_action != actual_action and cap_action in dispatcher:
                actions_to_remove.add(cap_action)
                print(f'  Removing duplicate dispatcher call {cap_action} (actual action: {actual_action})')

    # Remove from dispatcher
    for action in actions_to_remove:
        pattern = rf'[ \t]*{re.escape(action)}\s*;\s*\r?\n?'
        new_dispatcher, n = re.subn(pattern, '', dispatcher)
        if n > 0:
            dispatcher = new_dispatcher
            removed_dispatcher += n
        else:
            # Also try without newline at end
            pattern2 = rf'[ \t]*{re.escape(action)}\s*;'
            new_dispatcher, n = re.subn(pattern2, '', dispatcher)
            if n > 0:
                dispatcher = new_dispatcher
                removed_dispatcher += n

    # Remove from IEC.prg - match both by action name and file name
    # IEC.prg has entries like: <File ...>VarMon_RegInit_EcmClient.st</File>
    for file_stem, action_name, root_var in bad_subsystems:
        file_name = f'{file_stem}.st'
        pattern = rf'[ \t]*<File[^>]*>{re.escape(file_name)}</File>\s*\r?\n?'
        new_iec, n = re.subn(pattern, '', iec_prg)
        if n > 0:
            iec_prg = new_iec
            removed_iec += n

    dispatcher_path.write_text(dispatcher, encoding='utf-8')
    iec_prg_path.write_text(iec_prg, encoding='utf-8')

    print(f'\nRemoved {removed_dispatcher} dispatcher calls')
    print(f'Removed {removed_iec} IEC.prg entries')


if __name__ == '__main__':
    print('Step 1: Building accessible variable roots...')
    accessible_roots = build_accessible_roots()

    print('\nStep 2: Finding bad subsystems...')
    bad_subsystems, all_actions = find_bad_subsystems(accessible_roots)
    print(f'Found {len(bad_subsystems)} subsystems with inaccessible variables:')
    for f, a, r in bad_subsystems:
        print(f'  {a} (root: {r})')

    if bad_subsystems:
        print('\nStep 3: Fixing dispatcher and IEC.prg...')
        fix_dispatcher_and_iecprg(bad_subsystems, all_actions)
        print('Done!')
    else:
        print('\nNo bad subsystems found - checking for CSDriveStatus issue only...')
        fix_dispatcher_and_iecprg([], all_actions)

    print('\nSummary:')
    print(f'  Total subsystems checked: {len(list(VARMON_DIR.glob("VarMon_RegInit_*.st"))) - 1}')
    print(f'  Removed: {len(bad_subsystems)}')
