"""
Example: Connect to a PLC and monitor variables using plc_proto.

This demonstrates how to use the plc_proto package to:
1. Connect to a B&R PLC running VarMonLib
2. Subscribe to variables by registry index
3. Receive real-time variable updates via callback
4. Write a variable value
5. Disconnect cleanly

Prerequisites:
    pip install protobuf>=5.29
    PLC running VarMonLib on port 55000
"""

import time
import sys
from pathlib import Path

# If plc_proto is not installed as a package, add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from plc_proto import PlcConnection, TRANSPORT_TCP, ACTION_SET


def on_update(sequence: int, timestamp_us: int, values: dict[int, any]):
    """Called from background thread on every received VarUpdatePacket."""
    ts_ms = timestamp_us / 1000.0
    print(f"  [#{sequence}] ts={ts_ms:.1f}ms  {len(values)} vars changed:")
    for var_id, value in list(values.items())[:5]:
        print(f"    var[{var_id}] = {value}")
    if len(values) > 5:
        print(f"    ... and {len(values) - 5} more")


def on_disconnect(reason: str):
    """Called when connection drops."""
    print(f"\n[DISCONNECTED] {reason}")


def main():
    plc_ip = sys.argv[1] if len(sys.argv) > 1 else "192.168.101.10"
    print(f"PLC Protobuf Monitor Example")
    print(f"{'=' * 40}")
    print(f"Target: {plc_ip}")

    # Create connection
    conn = PlcConnection()
    conn.on_update = on_update
    conn.on_disconnect = on_disconnect

    # Connect
    print(f"\nConnecting...")
    result = conn.connect(plc_ip, transport="tcp")
    if not result["ok"]:
        print(f"Failed: {result['error']}")
        return

    print(f"Connected! Transport: {result['transport']}")

    # Subscribe to variables 0-9
    print(f"\nSubscribing to variables 0-9 at 10ms interval...")
    sub_result = conn.subscribe(list(range(10)), action=ACTION_SET, interval_ms=10)
    print(f"Subscribed: {sub_result}")

    # Receive updates for 5 seconds
    print(f"\nReceiving updates for 5 seconds...")
    time.sleep(5)

    # Print stats
    print(f"\nStats:")
    print(f"  Packets received: {conn.packets_received}")
    print(f"  Bytes received:   {conn.bytes_received}")
    print(f"  Last sequence:    {conn.last_seq}")
    print(f"  Cached values:    {len(conn.values)}")

    # Write a variable (example - uncomment if you have a writable var)
    # result = conn.write_var(var_id=5, plc_type="REAL", value=42.0)
    # print(f"\nWrite result: {result}")

    # Disconnect
    print(f"\nDisconnecting...")
    conn.disconnect()
    print("Done.")


if __name__ == "__main__":
    main()
