"""Add VarMonLib to all Cpu.sw files that contain ProtoBufCom."""
from pathlib import Path

base = Path(r"C:\Work\Indigo\As45\SimulatorMainBranch\PLC-plc\Physical")
varmon_line = '    <LibraryObject Name="VarMonLib" Source="HPLibraries.VarMonLib.lby" Memory="UserROM" Language="IEC" Debugging="true" />'

count = 0
for cpu_sw in base.rglob("Cpu.sw"):
    content = cpu_sw.read_text(encoding="utf-8")
    if "VarMonLib" in content:
        print(f"  SKIP (already has): {cpu_sw.parent.parent.name}")
        continue
    if "ProtoBufCom" not in content:
        print(f"  SKIP (no ProtoBufCom): {cpu_sw.parent.parent.name}")
        continue

    lines = content.split("\n")
    insert_idx = None
    # Insert after the last existing HPLibraries entry
    for i, line in enumerate(lines):
        if "HPLibraries." in line and "LibraryObject" in line:
            insert_idx = i + 1
    if insert_idx is None:
        # Fallback: insert before first Libraries.* LibraryObject
        for i, line in enumerate(lines):
            if "Libraries." in line and "LibraryObject" in line:
                insert_idx = i
                break
    if insert_idx is None:
        print(f"  SKIP (no anchor): {cpu_sw.parent.parent.name}")
        continue

    lines.insert(insert_idx, varmon_line)
    cpu_sw.write_text("\n".join(lines), encoding="utf-8")
    count += 1
    print(f"  Added VarMonLib: {cpu_sw.parent.parent.name}")

print(f"\nTotal configs updated: {count}")
