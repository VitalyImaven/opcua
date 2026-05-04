"""
plc_proto.types — PLC type system: encoding, decoding, and value extraction.

Handles the mapping between PLC data types (BOOL, INT, REAL, etc.) and
Python values, including:
- Encoding Python values to little-endian bytes for WriteVarCommand
- Decoding VarValue protobuf oneof fields to Python values
- Type code lookups and metadata

Usage:
    from plc_proto.types import encode_value, decode_var_value

    # Encode a Python value for writing to PLC
    raw = encode_value("REAL", 3.14)

    # Decode a VarValue protobuf object
    var_id, value = decode_var_value(var_val)
"""

import struct
from typing import Any, Optional, Tuple

from .constants import (
    TYPE_ENCODING, TYPE_NAME_TO_CODE, TYPE_CODE_NAMES,
    TYPE_BOOL, TYPE_STRING,
)


def encode_value(plc_type: str, value: Any) -> bytes:
    """Encode a Python value to little-endian bytes for a given PLC type.

    Args:
        plc_type: PLC type name (e.g. "BOOL", "REAL", "UINT").
        value: Python value to encode.

    Returns:
        Raw little-endian bytes suitable for WriteVarCommand.value.

    Raises:
        ValueError: If the PLC type is unsupported for writing.
    """
    plc_type = plc_type.upper()
    type_code = TYPE_NAME_TO_CODE.get(plc_type)
    if type_code is None:
        raise ValueError(f"Unsupported PLC type: {plc_type}")

    if type_code == TYPE_BOOL:
        return struct.pack("<B", 1 if value else 0)

    if type_code == TYPE_STRING:
        raise ValueError("String writes are not supported via WriteVarCommand")

    encoding = TYPE_ENCODING.get(type_code)
    if encoding is None:
        raise ValueError(f"No encoding for PLC type: {plc_type}")

    fmt, _ = encoding
    if plc_type in ("REAL", "LREAL"):
        return struct.pack(fmt, float(value))
    return struct.pack(fmt, int(value))


def decode_var_value(var_val) -> Tuple[int, Optional[Any]]:
    """Extract (var_id, python_value) from a protobuf VarValue object.

    Uses WhichOneof to determine which value field is set.

    Args:
        var_val: A plcmonitor_pb2.VarValue protobuf object.

    Returns:
        Tuple of (var_id, value). Value is None if no oneof field is set.
    """
    var_id = var_val.var_id
    which = var_val.WhichOneof("value")
    if which is None:
        return var_id, None

    value = getattr(var_val, which)

    # Round floating point for cleaner display
    if which == "real_val":
        value = round(value, 6)
    elif which == "lreal_val":
        value = round(value, 9)

    return var_id, value


def decode_var_values(update) -> dict[int, Any]:
    """Decode all VarValue entries from a VarUpdatePacket.

    Args:
        update: A plcmonitor_pb2.VarUpdatePacket protobuf object.

    Returns:
        Dict mapping var_id → Python value.
    """
    result = {}
    for var_val in update.values:
        var_id, value = decode_var_value(var_val)
        if value is not None:
            result[var_id] = value
    return result


def type_code_to_name(type_code: int) -> str:
    """Convert a numeric type code to its PLC type name.

    Args:
        type_code: Numeric type code (0-9).

    Returns:
        Type name string (e.g. "BOOL", "REAL").
    """
    return TYPE_CODE_NAMES.get(type_code, f"UNKNOWN({type_code})")


def type_name_to_code(type_name: str) -> Optional[int]:
    """Convert a PLC type name to its numeric type code.

    Args:
        type_name: PLC type name (case-insensitive).

    Returns:
        Numeric type code, or None if not recognized.
    """
    return TYPE_NAME_TO_CODE.get(type_name.upper())
