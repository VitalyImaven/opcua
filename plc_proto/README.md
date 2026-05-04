# plc_proto — Reusable Protobuf Transport for B&R PLC Communication

A self-contained Python package for communicating with B&R PLCs running the VarMonLib protobuf server. Handles TCP/UDP transport, message framing, subscription management, and variable value encoding/decoding.

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│                    Your Application                        │
├──────────────────────────────────────────────────────────┤
│  PlcConnection (connection.py)                            │
│  - connect / disconnect / subscribe / write_var           │
│  - Background receiver threads (TCP + UDP)                │
│  - Value cache + callbacks                                │
├──────────────────────────────────────────────────────────┤
│  Messages (messages.py)     │  Types (types.py)           │
│  - build_subscribe()        │  - encode_value()           │
│  - build_config()           │  - decode_var_value()       │
│  - build_write_var()        │  - type code mappings       │
├──────────────────────────────────────────────────────────┤
│  Framing (framing.py)                                     │
│  - frame_message()  → [4B LE len][protobuf bytes]         │
│  - read_framed_messages() ← parse TCP buffer              │
├──────────────────────────────────────────────────────────┤
│  Constants (constants.py)                                 │
│  - MSG_*, ACTION_*, TRANSPORT_*, TYPE_*                   │
├──────────────────────────────────────────────────────────┤
│  Protobuf Schema (_pb2.py + plcmonitor.proto)             │
│  - PlcMessage, VarUpdatePacket, SubscribeCommand, etc.    │
└──────────────────────────────────────────────────────────┘
```

## Quick Start

### High-Level: PlcConnection

```python
from plc_proto import PlcConnection

# Connect to PLC
conn = PlcConnection()
result = conn.connect("192.168.101.10", transport="tcp")
print(result)  # {"ok": True, "ip": "...", "transport": "TCP"}

# Subscribe to variables by registry index
conn.subscribe([0, 1, 2, 3, 4], interval_ms=10)

# Receive updates via callback
def on_update(sequence, timestamp_us, values):
    """Called from background thread on every VarUpdatePacket."""
    for var_id, value in values.items():
        print(f"  var[{var_id}] = {value}")

conn.on_update = on_update

# Or poll the value cache
import time
time.sleep(1)
print(conn.values)  # {0: True, 1: 42, 2: 3.14, ...}

# Write a variable
conn.write_var(var_id=5, plc_type="REAL", value=3.14)

# Disconnect
conn.disconnect()
```

### Mid-Level: Build Messages Manually

```python
import socket, struct
from plc_proto import (
    build_subscribe, build_config, build_write_var,
    frame_message, read_framed_messages,
    ACTION_SET, TRANSPORT_TCP, DEFAULT_TCP_PORT,
)

# Connect raw TCP
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.connect(("192.168.101.10", DEFAULT_TCP_PORT))

# Set transport to TCP
msg = build_config(TRANSPORT_TCP)
sock.sendall(frame_message(msg.SerializeToString()))

# Subscribe to variables 0-99
msg = build_subscribe(ACTION_SET, var_ids=list(range(100)), interval_ms=10)
sock.sendall(frame_message(msg.SerializeToString()))

# Receive loop
buf = b""
while True:
    buf += sock.recv(65536)
    messages, buf = read_framed_messages(buf)
    for pb_bytes in messages:
        from plc_proto._pb2 import PlcMessage
        msg = PlcMessage()
        msg.ParseFromString(pb_bytes)
        if msg.type == 0:  # VAR_UPDATE
            from plc_proto.types import decode_var_values
            values = decode_var_values(msg.update)
            print(f"seq={msg.update.sequence} values={values}")
```

### Low-Level: Type Encoding

```python
from plc_proto.types import encode_value, decode_var_value
from plc_proto.constants import TYPE_ENCODING, TYPE_NAME_TO_CODE

# Encode a REAL value to bytes for writing
raw = encode_value("REAL", 3.14159)
# b'\xd0\x0fI@'  (little-endian float)

# Encode a BOOL
raw = encode_value("BOOL", True)
# b'\x01'
```

## Wire Protocol

### TCP Framing

All TCP messages use length-delimited framing:

```
┌─────────────────┬────────────────────────────┐
│ Length (4B, LE)  │ Protobuf Bytes (Length B)   │
└─────────────────┴────────────────────────────┘
```

### UDP

UDP packets carry raw `VarUpdatePacket` protobuf bytes without framing (each UDP datagram = one complete message).

### Message Types (PlcMessage.MsgType)

| Code | Name              | Direction     | Description                    |
|------|-------------------|---------------|--------------------------------|
| 0    | VAR_UPDATE        | PLC → Python  | Variable values (periodic)     |
| 1    | SUBSCRIBE_CMD     | Python → PLC  | Subscribe/unsubscribe          |
| 2    | REGISTRY_REQUEST  | Python → PLC  | Request variable registry      |
| 3    | REGISTRY_RESPONSE | PLC → Python  | Variable registry entries      |
| 4    | HEARTBEAT         | Both          | Keep-alive / registry sync     |
| 5    | CONFIG_CMD        | Python → PLC  | Set transport mode             |
| 6    | CONFIG_RESPONSE   | PLC → Python  | Confirm transport mode         |
| 7    | WRITE_VAR         | Python → PLC  | Write single variable          |
| 8    | WRITE_VAR_RESP    | PLC → Python  | Write acknowledgment           |

### PLC Type Codes

| Code | Type   | Size | Python Type |
|------|--------|------|-------------|
| 0    | BOOL   | 1B   | bool        |
| 1    | INT    | 2B   | int         |
| 2    | UINT   | 2B   | int         |
| 3    | DINT   | 4B   | int         |
| 4    | UDINT  | 4B   | int         |
| 5    | REAL   | 4B   | float       |
| 6    | LREAL  | 8B   | float       |
| 7    | STRING | var  | str         |
| 8    | USINT  | 1B   | int         |
| 9    | SINT   | 1B   | int         |

## Adapting for Your Own Project

To use this package for a new PLC protobuf application:

1. **Copy the `plc_proto/` directory** into your project
2. **Install protobuf**: `pip install protobuf>=5.29`
3. **If you modify the schema**: regenerate with `protoc --python_out=. plcmonitor.proto` and rename output to `_pb2.py`
4. **Use `PlcConnection`** for simple monitoring, or build custom logic using the lower-level modules

### Extending the Protocol

To add new message types:

1. Edit `plcmonitor.proto` — add new message + MsgType enum value
2. Regenerate `_pb2.py`
3. Add constant to `constants.py`
4. Add builder to `messages.py`
5. Add handler in `connection.py._handle_message()`

## Requirements

- Python 3.10+
- `protobuf >= 5.29`

## PLC Side

The PLC must run **VarMonLib** (`VM_Server` function block) which implements:
- TCP server on port 55000 (configurable)
- Protobuf message encoding/decoding in IEC 61131-3 Structured Text
- Variable registry with address resolution
- Delta encoding for efficient updates
- Chunked initial snapshot for large subscriptions
