"""Direct TCP diagnostic: send CONFIG_CMD then subscribe, dump raw hex.

Usage: python -m tools.diag_tcp
   or: python tools/diag_tcp.py
"""
import socket
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from plc_proto import (
    build_config, build_subscribe,
    frame_message, read_framed_messages,
    TRANSPORT_TCP, ACTION_SET, DEFAULT_TCP_PORT,
    MSG_TYPE_NAMES,
)
from plc_proto._pb2 import PlcMessage
from plc_proto.types import decode_var_values

PLC_IP = "192.168.101.10"


def send_msg(sock, msg):
    frame = frame_message(msg.SerializeToString())
    sock.sendall(frame)
    print(f"[TX] {len(frame)}B: {frame.hex(' ')}")


def recv_all(sock, timeout=2.0):
    """Receive all available data within timeout."""
    sock.settimeout(timeout)
    buf = b""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            chunk = sock.recv(4096)
            if not chunk:
                break
            buf += chunk
            print(f"  [RX chunk] {len(chunk)}B")
        except socket.timeout:
            break
    return buf


def parse_and_print(buf):
    """Parse length-delimited messages and print decoded content."""
    messages, remaining = read_framed_messages(buf)
    print(f"\nReceived {len(messages)} messages")

    for i, pb_bytes in enumerate(messages[:10]):
        print(f"\n[RX msg {i}] {len(pb_bytes)}B: "
              f"{pb_bytes[:32].hex(' ')}{'...' if len(pb_bytes) > 32 else ''}")
        try:
            msg = PlcMessage()
            msg.ParseFromString(pb_bytes)
            type_name = MSG_TYPE_NAMES.get(msg.type, f"UNKNOWN({msg.type})")
            print(f"  type={msg.type} ({type_name})")

            if msg.HasField('subscribe'):
                print(f"  subscribe ACK: action={msg.subscribe.action} "
                      f"interval={msg.subscribe.interval_ms}")
            if msg.HasField('config_resp'):
                print(f"  config_resp.transport={msg.config_resp.transport}")
            if msg.HasField('update'):
                values = decode_var_values(msg.update)
                print(f"  update: seq={msg.update.sequence} "
                      f"ts={msg.update.timestamp} values={len(values)}")
                for var_id, val in list(values.items())[:5]:
                    print(f"    var[{var_id}] = {val}")
        except Exception as e:
            print(f"  parse error: {e}")

    return remaining


print(f"Connecting to {PLC_IP}:{DEFAULT_TCP_PORT}...")
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(3)
s.connect((PLC_IP, DEFAULT_TCP_PORT))
print("Connected!")

# Step 1: Send CONFIG_CMD to set TCP mode
print("\n=== Step 1: CONFIG_CMD (set TCP mode) ===")
cfg_msg = build_config(TRANSPORT_TCP)
send_msg(s, cfg_msg)

buf = recv_all(s, 2.0)
if buf:
    parse_and_print(buf)
else:
    print("No response!")

# Step 2: Subscribe to var_ids 1-10
print("\n=== Step 2: Subscribe to vars 1-10 ===")
sub_msg = build_subscribe(ACTION_SET, var_ids=list(range(1, 11)), interval_ms=100)
send_msg(s, sub_msg)

print("\nWaiting for ACK + data (5s)...")
buf = recv_all(s, 5.0)
if buf:
    parse_and_print(buf)
else:
    print("No data received!")

s.close()
print("\nDone.")
