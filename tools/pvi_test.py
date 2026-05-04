"""Quick PVI test: 5 vars with RF=1ms for 5 seconds using pure doEvents (no start/stop)."""
from pvi import Connection, Line, Device, Cpu, Variable
import datetime, time

pviConn = Connection()
line = Line(pviConn.root, 'LNANSL', CD='LNANSL')
device = Device(line, 'TCP', CD='/IF=TcpIp')
cpu = Cpu(device, 'plc', CD='/IP=192.168.101.10')

per_var = {}
var_objects = []
connected = [False]

def make_cb(name):
    per_var[name] = {'count': 0, 'last': None, 'prev': None, 'missed': 0}
    def on_val(value):
        d = per_var[name]
        d['count'] += 1
        if d['prev'] is not None and value != d['prev']:
            delta = value - d['prev']
            if delta < 0:
                delta += 4294967296
            if delta > 1:
                d['missed'] += delta - 1
        d['prev'] = value
        d['last'] = value
    return on_val

def on_cpu_error(err):
    if err == 0:
        connected[0] = True
        print('CPU connected')
cpu.errorChanged = on_cpu_error

# Phase 1: pump doEvents() until CPU connects (no start/stop!)
print('Waiting for PVI connection via doEvents()...')
t0 = time.perf_counter()
while not connected[0]:
    pviConn.doEvents()
    if time.perf_counter() - t0 > 10:
        print('Timeout waiting for connection')
        exit(1)
print(f'Connected in {time.perf_counter() - t0:.2f}s')

# Create variables
for i in range(1, 6):
    v = Variable(cpu, f'opctest{i}', RF=1)
    v.valueChanged = make_cb(f'opctest{i}')
    var_objects.append(v)
print('5 vars created with RF=1, running tight doEvents loop...')

# Run tight doEvents loop for 5 seconds
start = time.perf_counter()
loops = 0
while time.perf_counter() - start < 5.0:
    pviConn.doEvents()
    loops += 1

dur = time.perf_counter() - start
print(f'Loop ran {loops} times in {dur:.1f}s ({loops/dur:.0f} loops/sec)')
for name in sorted(per_var.keys(), key=lambda x: int(x.replace('opctest',''))):
    d = per_var[name]
    rate = d['count'] / dur
    print(f'  {name}: {d["count"]} notifs ({rate:.1f}/sec), missed={d["missed"]}')
total = sum(d['count'] for d in per_var.values())
print(f'Total: {total} notifs')

for v in var_objects:
    v.kill()
