"""
plc_proto.messages — Build protobuf PlcMessage objects for the PLC wire protocol.

Provides simple factory functions that construct properly typed PlcMessage
instances ready for serialization. Each function returns a PlcMessage object
that can be sent using ``framing.frame_message(msg.SerializeToString())``.

Usage:
    from plc_proto.messages import build_subscribe, build_config, build_write_var
    from plc_proto.framing import frame_message

    msg = build_subscribe(action=ACTION_SET, var_ids=[0, 1, 2], interval_ms=10)
    sock.sendall(frame_message(msg.SerializeToString()))
"""

from . import _pb2 as pb
from .constants import (
    MSG_SUBSCRIBE_CMD, MSG_CONFIG_CMD, MSG_WRITE_VAR,
    MSG_HEARTBEAT, MSG_REGISTRY_REQUEST,
    ACTION_SET, ACTION_ADD, ACTION_REMOVE,
)


def build_subscribe(action: int = ACTION_SET,
                    var_ids: list[int] | None = None,
                    interval_ms: int | None = None) -> pb.PlcMessage:
    """Build a SUBSCRIBE_CMD message.

    Args:
        action: ACTION_SET (replace), ACTION_ADD, or ACTION_REMOVE.
        var_ids: List of variable registry indices to subscribe to.
        interval_ms: Desired update interval in milliseconds.

    Returns:
        PlcMessage ready for serialization.
    """
    msg = pb.PlcMessage()
    msg.type = MSG_SUBSCRIBE_CMD
    msg.subscribe.action = action
    if var_ids:
        msg.subscribe.var_ids.extend(var_ids)
    if interval_ms is not None:
        msg.subscribe.interval_ms = interval_ms
    return msg


def build_config(transport: int) -> pb.PlcMessage:
    """Build a CONFIG_CMD message to set the transport mode.

    Args:
        transport: TRANSPORT_TCP (0) or TRANSPORT_UDP (1).

    Returns:
        PlcMessage ready for serialization.
    """
    msg = pb.PlcMessage()
    msg.type = MSG_CONFIG_CMD
    msg.config_cmd.transport = transport
    return msg


def build_write_var(var_id: int, value_bytes: bytes) -> pb.PlcMessage:
    """Build a WRITE_VAR message.

    Args:
        var_id: Variable registry index.
        value_bytes: Raw value bytes (little-endian encoded).

    Returns:
        PlcMessage ready for serialization.
    """
    msg = pb.PlcMessage()
    msg.type = MSG_WRITE_VAR
    msg.write_var.var_id = var_id
    msg.write_var.value = value_bytes
    return msg


def build_heartbeat() -> pb.PlcMessage:
    """Build a HEARTBEAT message.

    Returns:
        PlcMessage ready for serialization.
    """
    msg = pb.PlcMessage()
    msg.type = MSG_HEARTBEAT
    return msg


def build_registry_request(full: bool = True) -> pb.PlcMessage:
    """Build a REGISTRY_REQUEST message.

    Args:
        full: Request the full variable list from PLC.

    Returns:
        PlcMessage ready for serialization.
    """
    msg = pb.PlcMessage()
    msg.type = MSG_REGISTRY_REQUEST
    msg.reg_req.full_registry = full
    return msg
