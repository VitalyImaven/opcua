"""
plc_proto — Reusable protobuf transport library for B&R PLC communication.

This package provides everything needed to communicate with a B&R PLC
running the VarMonLib protobuf server over TCP/UDP:

- **Protocol schema** (plcmonitor.proto) and generated Python code
- **TCP framing** — length-delimited message send/receive
- **Message builders** — construct subscribe, config, write commands
- **Type system** — PLC↔Python type encoding and decoding
- **PlcConnection** — high-level client with background receiver threads

Quick Start:
    from plc_proto import PlcConnection

    conn = PlcConnection()
    conn.connect("192.168.101.10")
    conn.on_update = lambda seq, ts, vals: print(f"Update #{seq}: {vals}")
    conn.subscribe([0, 1, 2, 3], interval_ms=10)
    # ... conn.values holds latest cached values ...
    conn.disconnect()

Lower-level usage:
    from plc_proto.messages import build_subscribe, build_config
    from plc_proto.framing import frame_message
    from plc_proto.constants import ACTION_SET, TRANSPORT_TCP
    from plc_proto.types import encode_value, decode_var_value

    # Build and frame a message manually
    msg = build_subscribe(ACTION_SET, var_ids=[0, 1, 2], interval_ms=10)
    raw = frame_message(msg.SerializeToString())
    sock.sendall(raw)

Package structure:
    plc_proto/
    ├── __init__.py          ← You are here (public API)
    ├── constants.py         ← Enums, type codes, ports
    ├── framing.py           ← TCP length-delimited framing
    ├── messages.py          ← PlcMessage factory functions
    ├── types.py             ← PLC type encoding/decoding
    ├── connection.py        ← High-level PlcConnection client
    ├── _pb2.py              ← Generated protobuf code (internal)
    ├── plcmonitor.proto     ← Protocol schema definition
    └── README.md            ← Usage guide and examples
"""

# Re-export the generated protobuf module as internal
from .constants import (
    # Message types
    MSG_VAR_UPDATE, MSG_SUBSCRIBE_CMD, MSG_REGISTRY_REQUEST,
    MSG_REGISTRY_RESP, MSG_HEARTBEAT, MSG_CONFIG_CMD,
    MSG_CONFIG_RESPONSE, MSG_WRITE_VAR, MSG_WRITE_VAR_RESP,
    MSG_TYPE_NAMES,
    # Subscription actions
    ACTION_SET, ACTION_ADD, ACTION_REMOVE, ACTION_NAMES,
    # Transport modes
    TRANSPORT_TCP, TRANSPORT_UDP, TRANSPORT_NAMES,
    # Ports
    DEFAULT_TCP_PORT, DEFAULT_UDP_PORT,
    # PLC type codes
    TYPE_BOOL, TYPE_INT, TYPE_UINT, TYPE_DINT, TYPE_UDINT,
    TYPE_REAL, TYPE_LREAL, TYPE_STRING, TYPE_USINT, TYPE_SINT,
    TYPE_CODE_NAMES, TYPE_NAME_TO_CODE, TYPE_ENCODING,
)
from .framing import frame_message, read_framed_messages
from .messages import (
    build_subscribe, build_config, build_write_var,
    build_heartbeat, build_registry_request,
)
from .types import (
    encode_value, decode_var_value, decode_var_values,
    type_code_to_name, type_name_to_code,
)
from .connection import PlcConnection

__all__ = [
    # Connection
    "PlcConnection",
    # Constants
    "MSG_VAR_UPDATE", "MSG_SUBSCRIBE_CMD", "MSG_REGISTRY_REQUEST",
    "MSG_REGISTRY_RESP", "MSG_HEARTBEAT", "MSG_CONFIG_CMD",
    "MSG_CONFIG_RESPONSE", "MSG_WRITE_VAR", "MSG_WRITE_VAR_RESP",
    "MSG_TYPE_NAMES",
    "ACTION_SET", "ACTION_ADD", "ACTION_REMOVE", "ACTION_NAMES",
    "TRANSPORT_TCP", "TRANSPORT_UDP", "TRANSPORT_NAMES",
    "DEFAULT_TCP_PORT", "DEFAULT_UDP_PORT",
    "TYPE_BOOL", "TYPE_INT", "TYPE_UINT", "TYPE_DINT", "TYPE_UDINT",
    "TYPE_REAL", "TYPE_LREAL", "TYPE_STRING", "TYPE_USINT", "TYPE_SINT",
    "TYPE_CODE_NAMES", "TYPE_NAME_TO_CODE", "TYPE_ENCODING",
    # Framing
    "frame_message", "read_framed_messages",
    # Messages
    "build_subscribe", "build_config", "build_write_var",
    "build_heartbeat", "build_registry_request",
    # Types
    "encode_value", "decode_var_value", "decode_var_values",
    "type_code_to_name", "type_name_to_code",
]
