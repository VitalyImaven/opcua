"""
plc_proto.framing — TCP length-delimited framing for protobuf messages.

Wire format:
    [LENGTH : 4 bytes, little-endian uint32] [PROTOBUF_BYTES : LENGTH bytes]

This is the standard framing used between the Python client and the
B&R PLC's VarMonLib TCP server. All messages (commands, responses,
variable updates) use this framing on the TCP channel.

UDP packets carry raw protobuf bytes without a length prefix.

Usage:
    from plc_proto.framing import frame_message, read_framed_messages

    # Send
    sock.sendall(frame_message(msg.SerializeToString()))

    # Receive (accumulate buffer from sock.recv)
    messages, remaining = read_framed_messages(buffer)
"""

import struct
from typing import List, Tuple

# Maximum valid message length (matches PLC iTcpDataBuf size: 512 KB)
MAX_MESSAGE_LENGTH = 524288


def frame_message(pb_bytes: bytes) -> bytes:
    """Wrap serialized protobuf bytes in a length-delimited TCP frame.

    Args:
        pb_bytes: Serialized protobuf message bytes.

    Returns:
        Framed bytes: [4-byte LE length prefix] + [protobuf bytes].
    """
    return struct.pack("<I", len(pb_bytes)) + pb_bytes


def read_framed_messages(buf: bytes) -> Tuple[List[bytes], bytes]:
    """Extract complete length-delimited protobuf messages from a TCP buffer.

    Reads as many complete [LENGTH][PAYLOAD] frames as possible from ``buf``.
    Returns the extracted message payloads and any remaining incomplete bytes.

    If a length prefix exceeds MAX_MESSAGE_LENGTH, the single byte is
    skipped (resynchronization) and scanning continues.

    Args:
        buf: Accumulated bytes from TCP recv calls.

    Returns:
        Tuple of (list of protobuf payload bytes, remaining buffer bytes).
    """
    messages: List[bytes] = []
    pos = 0

    while pos + 4 <= len(buf):
        msg_len = struct.unpack_from("<I", buf, pos)[0]

        # Sanity check — skip invalid lengths
        if msg_len > MAX_MESSAGE_LENGTH:
            pos += 1
            continue

        # Wait for complete message
        if pos + 4 + msg_len > len(buf):
            break

        messages.append(buf[pos + 4 : pos + 4 + msg_len])
        pos += 4 + msg_len

    return messages, buf[pos:]
