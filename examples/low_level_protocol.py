"""
Example: Low-level protobuf communication without PlcConnection.

Shows how to use the individual plc_proto modules directly for
custom communication patterns — useful when you need full control
over timing, threading, or message handling.

Prerequisites:
    pip install protobuf>=5.29
"""

import socket
import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from plc_proto import (
    # Message builders
    build_subscribe, build_config, build_write_var,
    # Framing
    frame_message, read_framed_messages,
    # Constants
    ACTION_SET, TRANSPORT_TCP, DEFAULT_TCP_PORT,
    MSG_VAR_UPDATE, MSG_TYPE_NAMES,
)
from plc_proto._pb2 import PlcMessage
from plc_proto.types import decode_var_values, encode_value


def main():
    plc_ip = sys.argv[1] if len(sys.argv) > 1 else "192.168.101.10"
    print(f"Low-level protobuf example → {plc_ip}:{DEFAULT_TCP_PORT}")

    # --- Step 1: Raw TCP connection ---
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(3.0)
    sock.connect((plc_ip, DEFAULT_TCP_PORT))
    sock.settimeout(1.0)
    print("TCP connected")

    # --- Step 2: Configure transport mode ---
    config_msg = build_config(TRANSPORT_TCP)
    sock.sendall(frame_message(config_msg.SerializeToString()))
    print("Sent CONFIG_CMD (TCP mode)")

    # --- Step 3: Subscribe to variables ---
    var_ids = list(range(0, 20))  # First 20 registry entries
    sub_msg = build_subscribe(ACTION_SET, var_ids, interval_ms=50)
    sock.sendall(frame_message(sub_msg.SerializeToString()))
    print(f"Sent SUBSCRIBE_CMD: {len(var_ids)} vars at 50ms")

    # --- Step 4: Receive loop ---
    print("\nReceiving for 3 seconds...")
    buf = b""
    deadline = time.time() + 3.0
    total_packets = 0
    total_vars = 0

    while time.time() < deadline:
        try:
            chunk = sock.recv(65536)
            if not chunk:
                print("Connection closed by PLC")
                break
            buf += chunk
        except socket.timeout:
            pass

        # Parse all complete messages from buffer
        messages, buf = read_framed_messages(buf)
        for pb_bytes in messages:
            msg = PlcMessage()
            msg.ParseFromString(pb_bytes)

            type_name = MSG_TYPE_NAMES.get(msg.type, "?")

            if msg.type == MSG_VAR_UPDATE and msg.HasField('update'):
                values = decode_var_values(msg.update)
                total_packets += 1
                total_vars += len(values)
                if total_packets <= 3:
                    print(f"  [{type_name}] seq={msg.update.sequence} "
                          f"vars={len(values)}")
                    for vid, val in list(values.items())[:3]:
                        print(f"    var[{vid}] = {val}")
            else:
                print(f"  [{type_name}] (non-data message)")

    print(f"\nSummary: {total_packets} packets, {total_vars} variable updates")

    # --- Step 5: Write a variable (example) ---
    # Encode a REAL value and send WRITE_VAR
    # val_bytes = encode_value("REAL", 99.5)
    # write_msg = build_write_var(var_id=5, value_bytes=val_bytes)
    # sock.sendall(frame_message(write_msg.SerializeToString()))
    # print("Sent WRITE_VAR")

    sock.close()
    print("Done.")


if __name__ == "__main__":
    main()
