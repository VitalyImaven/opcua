"""
plc_proto.constants — Protocol constants for PLC Protobuf communication.

This module defines all enumerations and constants used by the wire protocol:
message types, subscription actions, transport modes, PLC type codes, and
default network ports.
"""

# ── PlcMessage.MsgType ─────────────────────────────────────────
MSG_VAR_UPDATE       = 0
MSG_SUBSCRIBE_CMD    = 1
MSG_REGISTRY_REQUEST = 2
MSG_REGISTRY_RESP    = 3
MSG_HEARTBEAT        = 4
MSG_CONFIG_CMD       = 5
MSG_CONFIG_RESPONSE  = 6
MSG_WRITE_VAR        = 7
MSG_WRITE_VAR_RESP   = 8

MSG_TYPE_NAMES = {
    MSG_VAR_UPDATE:       "VAR_UPDATE",
    MSG_SUBSCRIBE_CMD:    "SUBSCRIBE_CMD",
    MSG_REGISTRY_REQUEST: "REGISTRY_REQUEST",
    MSG_REGISTRY_RESP:    "REGISTRY_RESPONSE",
    MSG_HEARTBEAT:        "HEARTBEAT",
    MSG_CONFIG_CMD:       "CONFIG_CMD",
    MSG_CONFIG_RESPONSE:  "CONFIG_RESPONSE",
    MSG_WRITE_VAR:        "WRITE_VAR",
    MSG_WRITE_VAR_RESP:   "WRITE_VAR_RESP",
}

# ── SubscribeCommand.Action ────────────────────────────────────
ACTION_SET    = 0   # Replace entire subscription list
ACTION_ADD    = 1   # Add to current subscription
ACTION_REMOVE = 2   # Remove from current subscription

ACTION_NAMES = {
    ACTION_SET:    "SET",
    ACTION_ADD:    "ADD",
    ACTION_REMOVE: "REMOVE",
}

# ── TransportMode ──────────────────────────────────────────────
TRANSPORT_TCP = 0   # Variable updates sent over TCP (default)
TRANSPORT_UDP = 1   # Variable updates sent over UDP

TRANSPORT_NAMES = {
    TRANSPORT_TCP: "TCP",
    TRANSPORT_UDP: "UDP",
}

# ── Default ports ──────────────────────────────────────────────
DEFAULT_TCP_PORT = 55000   # TCP command + data channel
DEFAULT_UDP_PORT = 55001   # UDP data channel (client-side)

# ── PLC type codes (matches VarMonLib VM_TypeCode_enum) ────────
TYPE_BOOL   = 0
TYPE_INT    = 1
TYPE_UINT   = 2
TYPE_DINT   = 3
TYPE_UDINT  = 4
TYPE_REAL   = 5
TYPE_LREAL  = 6
TYPE_STRING = 7
TYPE_USINT  = 8
TYPE_SINT   = 9

TYPE_CODE_NAMES = {
    TYPE_BOOL:   "BOOL",
    TYPE_INT:    "INT",
    TYPE_UINT:   "UINT",
    TYPE_DINT:   "DINT",
    TYPE_UDINT:  "UDINT",
    TYPE_REAL:   "REAL",
    TYPE_LREAL:  "LREAL",
    TYPE_STRING: "STRING",
    TYPE_USINT:  "USINT",
    TYPE_SINT:   "SINT",
}

# Reverse map: type name → type code
TYPE_NAME_TO_CODE = {v: k for k, v in TYPE_CODE_NAMES.items()}

# Type code → (struct_format, byte_size) for value encoding
TYPE_ENCODING = {
    TYPE_BOOL:   ("<B", 1),
    TYPE_INT:    ("<h", 2),
    TYPE_UINT:   ("<H", 2),
    TYPE_DINT:   ("<i", 4),
    TYPE_UDINT:  ("<I", 4),
    TYPE_REAL:   ("<f", 4),
    TYPE_LREAL:  ("<d", 8),
    TYPE_USINT:  ("<B", 1),
    TYPE_SINT:   ("<b", 1),
}
