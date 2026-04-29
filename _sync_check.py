"""Quick sync check between Python and PLC registries."""
import json, re
from pathlib import Path

py_reg = json.load(open('plc_var_registry.json'))
plc_reg = json.load(open(r'C:\Work\Indigo\As45\SimulatorMainBranch\PLC-plc\Logical\GlobalOps\ProtoBufCom\plc_var_registry.json'))
plc_dir = Path(r'C:\Work\Indigo\As45\SimulatorMainBranch\PLC-plc\Logical\GlobalOps\ProtoBufCom\ProtoBufCom')

ok = True
def check(label, passed, detail=""):
    global ok
    status = "OK" if passed else "FAIL"
    if not passed: ok = False
    print(f"  [{status}] {label}" + (f" — {detail}" if detail else ""))

print("=== Python <-> PLC Sync Check ===\n")

# 1
check("Registries match", py_reg == plc_reg, f"Python={len(py_reg)}, PLC={len(plc_reg)}")

# 2
var_content = (plc_dir / 'ProtoBufCom.var').read_text(encoding='utf-8')
m = re.search(r'ARRAY\[0\.\.(\d+)\]', var_content)
arr_size = int(m.group(1)) + 1
check("vmRegistry array size", arr_size >= len(plc_reg), f"[0..{arr_size-1}] for {len(plc_reg)} entries")

# 3
disp = (plc_dir / 'VarMon_RegInit.st').read_text(encoding='utf-8')
counts = re.findall(r'vmRegCount := (\d+)', disp)
final_count = int(counts[-1])
check("Dispatcher vmRegCount", final_count == len(plc_reg), f"{final_count}")

# 4
py_gm = [v['name'] for v in py_reg.values() if v['name'].startswith('gMachine.')]
plc_gm = [v['name'] for v in plc_reg.values() if v['name'].startswith('gMachine.')]
check("gMachine vars in both", py_gm == plc_gm, f"{len(py_gm)} vars")

# 5
py_prof = [v['name'] for v in py_reg.values() if v['name'].startswith('prof')]
plc_prof = [v['name'] for v in plc_reg.values() if v['name'].startswith('prof')]
check("No old prof* in registries", len(py_prof) == 0 and len(plc_prof) == 0,
      f"Python={len(py_prof)}, PLC={len(plc_prof)}")

# 6
sub_calls = re.findall(r'VarMon_RegInit_(\w+);', disp)
missing = [s for s in sub_calls if not (plc_dir / f'VarMon_RegInit_{s}.st').exists()]
check("All dispatcher .st files exist", len(missing) == 0,
      f"{len(sub_calls)} subsystems, {len(missing)} missing")

# 7
gv = Path(r'C:\Work\Indigo\As45\SimulatorMainBranch\PLC-plc\Logical\Global.var').read_text(encoding='utf-8')
check("Global.var has gMachine", 'gMachine : gMachine_typ' in gv)
check("Global.var no old prof scalars", 'profCycleTimeUs' not in gv)

# 8
gt = Path(r'C:\Work\Indigo\As45\SimulatorMainBranch\PLC-plc\Logical\Global.typ').read_text(encoding='utf-8')
check("Global.typ has CpuMeasurement_typ", 'CpuMeasurement_typ' in gt)
check("Global.typ has gMachine_typ", 'gMachine_typ' in gt)

# 9
main_st = Path(r'C:\Work\Indigo\As45\SimulatorMainBranch\PLC-plc\Logical\Simulation\IO\ProgramST\Main.st').read_text(encoding='utf-8')
check("Main.st uses gMachine.Out.Monitors.Cpu", 'gMachine.Out.Monitors.Cpu.CycleTimeUs' in main_st)
check("Main.st no old profCycleTimeUs", 'profCycleTimeUs' not in main_st)

print(f"\n{'ALL CHECKS PASSED' if ok else 'ISSUES FOUND'}")
