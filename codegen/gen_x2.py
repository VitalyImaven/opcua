"""Generate VarMon registration for gProtoTest x2 fields and update registry JSON."""
import json

fields = []

# Fast x2: 10 new vars
fast2 = [
    ('Counter3', 4, 4, 'UDINT'), ('Counter4', 3, 4, 'DINT'),
    ('SineWaveB', 5, 4, 'REAL'), ('CosineWaveB', 5, 4, 'REAL'),
    ('TriangleB', 5, 4, 'REAL'), ('FastRampB', 5, 4, 'REAL'),
    ('TickBoolB', 0, 1, 'BOOL'), ('NoiseB', 5, 4, 'REAL'),
    ('SpeedRPM_B', 5, 4, 'REAL'), ('TorqueRPM', 5, 4, 'REAL'),
]
for name, tc, sz, typ in fast2:
    fields.append((f'gProtoTest.Output.Fast.{name}', tc, sz, typ))

# Medium x2: 30 new vars
med2 = [
    ('Sawtooth3', 5, 4, 'REAL'), ('NegRampB', 5, 4, 'REAL'),
    ('Square100ms', 0, 1, 'BOOL'),
    ('Counter6', 4, 4, 'UDINT'), ('Counter7', 1, 2, 'INT'), ('Counter8', 2, 2, 'UINT'),
    ('SineX4', 5, 4, 'REAL'), ('CosineX3', 5, 4, 'REAL'), ('SineX5', 5, 4, 'REAL'),
    ('Pressure3', 5, 4, 'REAL'), ('Pressure4', 5, 4, 'REAL'),
    ('Temperature4', 5, 4, 'REAL'), ('Temperature5', 5, 4, 'REAL'), ('Temperature6', 5, 4, 'REAL'),
    ('Flow3', 5, 4, 'REAL'), ('Flow4', 5, 4, 'REAL'),
    ('Voltage3', 5, 4, 'REAL'), ('Voltage4', 5, 4, 'REAL'),
    ('Current3', 5, 4, 'REAL'), ('Current4', 5, 4, 'REAL'),
    ('TorqueB', 5, 4, 'REAL'), ('PositionB', 6, 8, 'LREAL'),
    ('VibrationB', 5, 4, 'REAL'), ('PowerB', 5, 4, 'REAL'),
    ('HumidityB', 5, 4, 'REAL'), ('LevelB', 5, 4, 'REAL'),
    ('DutyCycleB', 5, 4, 'REAL'), ('ErrorCodeB', 4, 4, 'UDINT'),
    ('StatusWordB', 2, 2, 'UINT'), ('ReactorTemp', 5, 4, 'REAL'),
]
for name, tc, sz, typ in med2:
    fields.append((f'gProtoTest.Output.Medium.{name}', tc, sz, typ))

# Slow x2: 60 new vars
slow2 = [
    ('SlowCounter3', 4, 4, 'UDINT'), ('SlowCounter4', 3, 4, 'DINT'),
    ('Setpoint6', 5, 4, 'REAL'), ('Setpoint7', 5, 4, 'REAL'), ('Setpoint8', 5, 4, 'REAL'),
    ('Setpoint9', 5, 4, 'REAL'), ('Setpoint10', 5, 4, 'REAL'),
    ('Actual6', 5, 4, 'REAL'), ('Actual7', 5, 4, 'REAL'), ('Actual8', 5, 4, 'REAL'),
    ('Actual9', 5, 4, 'REAL'), ('Actual10', 5, 4, 'REAL'),
    ('Deviation4', 5, 4, 'REAL'), ('Deviation5', 5, 4, 'REAL'), ('Deviation6', 5, 4, 'REAL'),
    ('SlowSineB', 5, 4, 'REAL'), ('SlowCosineB', 5, 4, 'REAL'),
    ('IntegralB', 6, 8, 'LREAL'),
    ('MinValueB', 5, 4, 'REAL'), ('MaxValueB', 5, 4, 'REAL'), ('AvgValueB', 5, 4, 'REAL'),
    ('StatBool5', 0, 1, 'BOOL'), ('StatBool6', 0, 1, 'BOOL'),
    ('StatBool7', 0, 1, 'BOOL'), ('StatBool8', 0, 1, 'BOOL'),
    ('BatchCountB', 4, 4, 'UDINT'),
    ('AlarmWord4', 2, 2, 'UINT'), ('AlarmWord5', 2, 2, 'UINT'), ('AlarmWord6', 2, 2, 'UINT'),
    ('Param11', 5, 4, 'REAL'), ('Param12', 5, 4, 'REAL'), ('Param13', 5, 4, 'REAL'),
    ('Param14', 5, 4, 'REAL'), ('Param15', 5, 4, 'REAL'), ('Param16', 5, 4, 'REAL'),
    ('Param17', 5, 4, 'REAL'), ('Param18', 5, 4, 'REAL'), ('Param19', 5, 4, 'REAL'),
    ('Param20', 5, 4, 'REAL'),
    ('Quality4', 5, 4, 'REAL'), ('Quality5', 5, 4, 'REAL'), ('Quality6', 5, 4, 'REAL'),
    ('EfficiencyB', 5, 4, 'REAL'), ('RuntimeB', 4, 4, 'UDINT'), ('PulseCountB', 4, 4, 'UDINT'),
    ('DoseB', 6, 8, 'LREAL'), ('EnergyTotalB', 6, 8, 'LREAL'),
    ('WearFactorB', 5, 4, 'REAL'), ('CyclesLeftB', 4, 4, 'UDINT'),
    ('OEE_B', 5, 4, 'REAL'), ('AvailabilityB', 5, 4, 'REAL'),
    ('PerformanceB', 5, 4, 'REAL'), ('QualityRateB', 5, 4, 'REAL'),
    ('StepNumberB', 2, 2, 'UINT'), ('PhaseIDB', 8, 1, 'USINT'),
    ('RecipeNumB', 8, 1, 'USINT'),
    ('LotSizeB', 4, 4, 'UDINT'), ('LotDoneB', 4, 4, 'UDINT'), ('LotRemainB', 4, 4, 'UDINT'),
    ('UptimeHours', 5, 4, 'REAL'),
]
for name, tc, sz, typ in slow2:
    fields.append((f'gProtoTest.Output.Slow.{name}', tc, sz, typ))

print(f'Total new fields: {len(fields)}')
print(f'Fast2: {len(fast2)}, Medium2: {len(med2)}, Slow2: {len(slow2)}')

# Sort alphabetically by path (like the codegen does)
fields.sort(key=lambda x: x[0])

# Write VarMon_RegInit_GProtoTest2.st
start_idx = 87234
lines = []
lines.append('(********************************************************************')
lines.append(' * VarMon Registry — GProtoTest x2 additions')
lines.append(f' * Variables: {len(fields)}  |  Start index: {start_idx}')
lines.append(' ********************************************************************)')
lines.append('ACTION VarMon_RegInit_GProtoTest2:')
for i, (path, tc, sz, typ) in enumerate(fields):
    idx = start_idx + i
    lines.append(f"    VM_RegVarByName(ADR(vmRegistry), {idx}, '{path}', {tc}, {sz});  (* {typ} *)")
lines.append('END_ACTION')

st_path = r'C:\Work\Indigo\As45\SimulatorMainBranch\PLC-plc\Logical\GlobalOps\ProtoBufCom\VarMon_RegInit_GProtoTest2.st'
with open(st_path, 'w') as f:
    f.write('\n'.join(lines))
print(f'Wrote {st_path}')
print(f'Index range: {start_idx} - {start_idx + len(fields) - 1}')

# Update plc_var_registry.json
d = json.load(open('plc_var_registry.json'))
for i, (path, tc, sz, typ) in enumerate(fields):
    d[str(start_idx + i)] = {'name': path, 'type': typ}
json.dump(d, open('plc_var_registry.json', 'w'), indent=2)
print(f'Registry now has {len(d)} entries')
