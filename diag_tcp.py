"""Direct TCP diagnostic: send CONFIG_CMD then subscribe, dump raw hex."""
import socket, struct, time, sys
sys.path.insert(0, '.')
from proto import plcmonitor_pb2 as pb

PLC_IP = "192.168.101.10"
TCP_PORT = 55000

def send_msg(sock, msg):
    data = msg.SerializeToString()
    frame = struct.pack("<I", len(data)) + data
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

def parse_messages(buf):
    """Parse length-delimited messages from buffer."""
    pos = 0
    msgs = []
    while pos + 4 <= len(buf):
        msg_len = struct.unpack_from("<I", buf, pos)[0]
        if msg_len > 65535:
            pos += 1
            continue
        if pos + 4 + msg_len > len(buf):
            break
        pb_bytes = buf[pos+4:pos+4+msg_len]
        msgs.append(pb_bytes)
        pos += 4 + msg_len
    return msgs, buf[pos:]

print(f"Connecting to {PLC_IP}:{TCP_PORT}...")
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(3)
s.connect((PLC_IP, TCP_PORT))
print("Connected!")

# Step 1: Send CONFIG_CMD to set TCP mode
print("\n=== Step 1: CONFIG_CMD (set TCP mode) ===")
cfg = pb.PlcMessage()
cfg.type = 5  # CONFIG_CMD
cfg.config_cmd.transport = 0  # TCP
send_msg(s, cfg)

# Wait for response
buf = recv_all(s, 2.0)
if buf:
    msgs, _ = parse_messages(buf)
    for i, pb_bytes in enumerate(msgs):
        print(f"\n[RX msg {i}] {len(pb_bytes)}B: {pb_bytes.hex(' ')}")
        try:
            msg = pb.PlcMessage()
            msg.ParseFromString(pb_bytes)
            print(f"  type={msg.type}")
            if msg.HasField('config_resp'):
                print(f"  config_resp.transport={msg.config_resp.transport}")
        except Exception as e:
            print(f"  parse error: {e}")
else:
    print("No response!")

# Step 2: Subscribe to var_ids 1-10
print("\n=== Step 2: Subscribe to vars 1-10 ===")
sub = pb.PlcMessage()
sub.type = 1  # SUBSCRIBE_CMD
sub.subscribe.action = 0  # SET
sub.subscribe.var_ids.extend(range(1, 11))
sub.subscribe.interval_ms = 100
send_msg(s, sub)

# Wait for ACK + data
print("\nWaiting for ACK + data (5s)...")
buf = recv_all(s, 5.0)
if buf:
    msgs, _ = parse_messages(buf)
    print(f"\nReceived {len(msgs)} messages")
    for i, pb_bytes in enumerate(msgs[:10]):  # Show first 10
        print(f"\n[RX msg {i}] {len(pb_bytes)}B: {pb_bytes[:32].hex(' ')}{'...' if len(pb_bytes)>32 else ''}")
        try:
            msg = pb.PlcMessage()
            msg.ParseFromString(pb_bytes)
            print(f"  type={msg.type}")
            if msg.HasField('subscribe'):
                print(f"  subscribe ACK: action={msg.subscribe.action} interval={msg.subscribe.interval_ms}")
            if msg.HasField('update'):
                print(f"  update: seq={msg.update.sequence} ts={msg.update.timestamp} values={len(msg.update.values)}")
                for v in msg.update.values[:5]:
                    w = v.WhichOneof('value')
                    print(f"    var[{v.var_id}] {w}={getattr(v, w) if w else None}")
        except Exception as e:
            print(f"  parse error: {e}")
else:
    print("No data received!")

s.close()
print("\nDone.")
