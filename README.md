# PLC Variable Monitor

Industrial PLC variable monitoring system for B&R Automation Studio PLCs. Provides real-time variable streaming via a custom protobuf protocol with sub-millisecond update rates.

## Project Structure

```
├── plc_proto/              ★ REUSABLE PROTOBUF TRANSPORT PACKAGE
│   ├── __init__.py         Public API (PlcConnection, constants, builders)
│   ├── connection.py       High-level client with background threads
│   ├── messages.py         Message factory functions
│   ├── framing.py          TCP length-delimited framing
│   ├── types.py            PLC type encoding/decoding
│   ├── constants.py        All protocol constants and enums
│   ├── plcmonitor.proto    Protocol schema definition
│   ├── _pb2.py             Generated protobuf code
│   └── README.md           Package documentation
│
├── web/                    Web applications (FastAPI + WebSocket)
│   ├── plc_engine.py       PLC binary protocol engine
│   ├── plc_app.py          PLC monitor REST API + WebSocket
│   ├── opcua_engine.py     OPC UA polling engine
│   ├── opcua_sub_engine.py OPC UA subscription engine
│   ├── opcua_sub_app.py    OPC UA subscription web UI
│   ├── pvi_engine.py       B&R PVI ANSL engine
│   ├── app.py              Protocol test suite (all engines)
│   └── static/             Frontend HTML/CSS/JS
│
├── codegen/                PLC code generation pipeline
│   ├── scanner.py          Scan B&R project → variable registry
│   ├── codegen.py          Generate VarMon_RegInit_*.st files
│   ├── registry_from_st.py Rebuild registry from PLC code
│   └── gen_x2.py           Generate test variables
│
├── tools/                  Diagnostics & maintenance
│   ├── diag_tcp.py         Raw TCP protobuf diagnostic
│   ├── sync_check.py       Python ↔ PLC registry validation
│   ├── fix_varmon_private.py  Remove inaccessible vars
│   ├── add_varmonlib_to_configs.py  Patch PLC project
│   └── update_varmon.py    Update VarMonLib in project
│
├── examples/               Usage examples
│   ├── basic_monitor.py    High-level PlcConnection usage
│   └── low_level_protocol.py  Raw message building
│
├── desktop/                PyQt5 desktop GUI (legacy)
│   ├── main.py             OPC UA recorder GUI
│   └── opc_recorder.py     Recording logic
│
├── proto/                  Original proto files (legacy, use plc_proto/)
├── src/                    Legacy source (use web/ engines)
├── plc_code/               Generated PLC registration code
│
├── run_web.py              Launch: Protocol test suite (port 8080)
├── run_plc_web.py          Launch: PLC monitor (port 8082)
├── run_opcua_web.py        Launch: OPC UA subscriptions (port 8083)
├── plc_var_registry.json   Variable registry (shared data)
└── requirements.txt        Python dependencies
```

## Quick Start

### Install

```bash
pip install -r requirements.txt
```

### Connect to PLC (Programmatic)

```python
from plc_proto import PlcConnection

conn = PlcConnection()
conn.connect("192.168.101.10")
conn.on_update = lambda seq, ts, vals: print(vals)
conn.subscribe(list(range(100)), interval_ms=10)
```

### Launch Web UI

```bash
# PLC binary protocol monitor (recommended)
python run_plc_web.py
# → http://localhost:8082

# Protocol comparison test suite
python run_web.py
# → http://localhost:8080
```

### Code Generation Pipeline

```bash
# 1. Scan PLC project for variables
python codegen/scanner.py --plc-root "C:\Work\...\PLC-plc"

# 2. Generate PLC registration code
python codegen/codegen.py

# 3. Rebuild registry from PLC code (after PLC build)
python codegen/registry_from_st.py
```

## The plc_proto Package

**This is the core reusable component.** If you need to communicate with a B&R PLC using protobuf, copy `plc_proto/` into your project.

See [plc_proto/README.md](plc_proto/README.md) for full documentation.

### Key Features
- **Zero-copy framing** — efficient length-delimited TCP message parsing
- **Type-safe encoding** — automatic PLC↔Python type conversion
- **Production-ready** — handles chunked subscriptions, background threads, reconnection
- **100K variable support** — tested with up to 100,000 monitored variables
- **Delta encoding** — PLC sends only changed values for bandwidth efficiency

### Wire Protocol Summary

```
TCP: [4B LE length][protobuf PlcMessage]
UDP: [raw protobuf VarUpdatePacket]

Message types:
  VAR_UPDATE(0)        PLC→Client   Variable values stream
  SUBSCRIBE_CMD(1)     Client→PLC   Subscribe/unsubscribe
  CONFIG_CMD(5)        Client→PLC   Set TCP/UDP transport
  WRITE_VAR(7)         Client→PLC   Write single variable
  HEARTBEAT(4)         Both         Keep-alive
```

## Protocol Engines

The system supports 4 communication backends for head-to-head benchmarking:

| Engine | Protocol | Direction | Latency |
|--------|----------|-----------|---------|
| `PlcMonitorEngine` | Custom protobuf (TCP/UDP) | Push | <1ms |
| `OpcuaSubEngine` | OPC UA Subscriptions | Push | ~10ms |
| `OpcuaEngine` | OPC UA Polling | Pull | ~5ms |
| `PviEngine` | B&R PVI ANSL | Pull | ~2ms |

## Requirements

- Python 3.10+
- `protobuf >= 5.29`
- `fastapi` + `uvicorn` (web UI)
- `opcua` (OPC UA engines)
- PLC: B&R Automation Studio with VarMonLib library
