"""
plc_proto.connection — High-level PLC connection client.

Provides ``PlcConnection``, a ready-to-use client for communicating with
a B&R PLC running the VarMonLib protobuf server. Handles TCP connection,
transport configuration, subscription management, and message reception
with background threads.

Usage:
    from plc_proto import PlcConnection, TRANSPORT_TCP, ACTION_SET

    conn = PlcConnection()
    conn.connect("192.168.101.10")
    conn.subscribe([0, 1, 2, 3], interval_ms=10)

    # Receive updates via callback
    conn.on_update = lambda seq, ts, values: print(values)

    # Or poll values
    print(conn.values)

    conn.disconnect()
"""

import socket
import struct
import threading
import time
from typing import Any, Callable, Optional

from . import _pb2 as pb
from .constants import (
    DEFAULT_TCP_PORT, DEFAULT_UDP_PORT,
    MSG_VAR_UPDATE, MSG_SUBSCRIBE_CMD, MSG_HEARTBEAT,
    MSG_CONFIG_CMD, MSG_CONFIG_RESPONSE, MSG_WRITE_VAR_RESP,
    ACTION_SET, ACTION_ADD, ACTION_REMOVE,
    TRANSPORT_TCP, TRANSPORT_UDP, TRANSPORT_NAMES,
)
from .framing import frame_message, read_framed_messages
from .messages import build_subscribe, build_config, build_write_var, build_heartbeat
from .types import decode_var_values, encode_value


class PlcConnection:
    """Manages a protobuf connection to a B&R PLC VarMonLib server.

    This class handles:
    - TCP connection (commands + data stream)
    - Optional UDP fallback for variable updates
    - Transport mode configuration (TCP or UDP for data)
    - Subscription management (SET, ADD, REMOVE with chunked sending)
    - Background message reception and decoding
    - Value caching and change callbacks

    Thread safety: All public methods are safe to call from any thread.
    Background receiver threads are started automatically on connect.

    Attributes:
        values: Dict[int, Any] — Current cached variable values (var_id → value).
        connected: bool — True when TCP connection is established.
        transport_mode: int — Current transport mode (TRANSPORT_TCP or TRANSPORT_UDP).
        subscribed: Set[int] — Currently subscribed variable IDs.
        on_update: Optional callback(sequence, timestamp, {var_id: value}).
        on_disconnect: Optional callback(reason: str).
        on_heartbeat: Optional callback(sub_count: int, registry_count: int).
    """

    def __init__(self, tcp_port: int = DEFAULT_TCP_PORT,
                 udp_port: int = DEFAULT_UDP_PORT):
        self.tcp_port = tcp_port
        self.udp_port = udp_port

        # Public state
        self.connected = False
        self.transport_mode = TRANSPORT_TCP
        self.values: dict[int, Any] = {}
        self.subscribed: set[int] = set()

        # Callbacks
        self.on_update: Optional[Callable[[int, int, dict[int, Any]], None]] = None
        self.on_disconnect: Optional[Callable[[str], None]] = None
        self.on_heartbeat: Optional[Callable[[int, int], None]] = None

        # Stats
        self.packets_received: int = 0
        self.bytes_received: int = 0
        self.last_seq: int = 0
        self.last_timestamp: int = 0

        # Internal
        self._plc_ip: str = ""
        self._tcp_sock: Optional[socket.socket] = None
        self._udp_sock: Optional[socket.socket] = None
        self._rx_thread: Optional[threading.Thread] = None
        self._udp_thread: Optional[threading.Thread] = None
        self._running = False
        self._lock = threading.Lock()

    def connect(self, plc_ip: str, transport: str = "tcp",
                timeout: float = 3.0) -> dict:
        """Connect to PLC.

        Args:
            plc_ip: PLC IP address.
            transport: Preferred transport for variable updates — "tcp" or "udp".
            timeout: TCP connection timeout in seconds.

        Returns:
            Dict with "ok" bool and connection details or error message.
        """
        with self._lock:
            if self.connected:
                self.disconnect()

            self._plc_ip = plc_ip
            self.transport_mode = TRANSPORT_TCP if transport.lower() == "tcp" else TRANSPORT_UDP

            # TCP connection
            try:
                self._tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self._tcp_sock.settimeout(timeout)
                self._tcp_sock.connect((plc_ip, self.tcp_port))
                self._tcp_sock.settimeout(1.0)
            except Exception as e:
                self._tcp_sock = None
                return {"ok": False, "error": f"TCP connect failed: {e}"}

            self.connected = True
            self._running = True

            # Start TCP receiver
            self._rx_thread = threading.Thread(
                target=self._tcp_receive_loop, daemon=True)
            self._rx_thread.start()

            # Send transport config
            self._send_raw(build_config(self.transport_mode))

            # Open UDP listener as fallback
            try:
                self._udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                self._udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                self._udp_sock.bind(("0.0.0.0", self.udp_port))
                self._udp_sock.settimeout(1.0)
                self._udp_thread = threading.Thread(
                    target=self._udp_receive_loop, daemon=True)
                self._udp_thread.start()
            except Exception:
                self._udp_sock = None

            mode = TRANSPORT_NAMES[self.transport_mode]
            return {"ok": True, "ip": plc_ip, "transport": mode}

    def disconnect(self) -> dict:
        """Disconnect from PLC."""
        with self._lock:
            self._running = False
            for sock in (self._tcp_sock, self._udp_sock):
                if sock:
                    try:
                        sock.close()
                    except Exception:
                        pass
            self._tcp_sock = None
            self._udp_sock = None
            self.connected = False
            self.subscribed.clear()
        return {"ok": True}

    def subscribe(self, var_ids: list[int], action: int = ACTION_SET,
                  interval_ms: int | None = None,
                  chunk_size: int = 5000) -> dict:
        """Subscribe to variables.

        Args:
            var_ids: List of variable registry indices.
            action: ACTION_SET (replace), ACTION_ADD, or ACTION_REMOVE.
            interval_ms: Desired update interval in ms.
            chunk_size: Max var_ids per TCP message (chunked for large sets).

        Returns:
            Dict with "ok" bool and subscription count.
        """
        if not self.connected:
            return {"ok": False, "error": "Not connected"}

        if action == ACTION_SET:
            self.subscribed = set(var_ids)
        elif action == ACTION_ADD:
            self.subscribed.update(var_ids)
        elif action == ACTION_REMOVE:
            self.subscribed -= set(var_ids)

        self._send_subscribe_chunked(var_ids, action, interval_ms, chunk_size)
        return {"ok": True, "subscribed": len(self.subscribed)}

    def write_var(self, var_id: int, plc_type: str, value: Any) -> dict:
        """Write a value to a PLC variable.

        Args:
            var_id: Variable registry index.
            plc_type: PLC type name (e.g. "REAL", "BOOL").
            value: Python value to write.

        Returns:
            Dict with "ok" bool.
        """
        if not self.connected:
            return {"ok": False, "error": "Not connected"}
        try:
            val_bytes = encode_value(plc_type, value)
        except ValueError as e:
            return {"ok": False, "error": str(e)}

        msg = build_write_var(var_id, val_bytes)
        try:
            self._send_raw(msg)
            return {"ok": True, "var_id": var_id}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def set_interval(self, interval_ms: int) -> dict:
        """Set the PLC send interval.

        Args:
            interval_ms: Update interval in milliseconds (1-10000).
        """
        interval_ms = max(1, min(10000, interval_ms))
        msg = build_subscribe(action=ACTION_SET, interval_ms=interval_ms)
        self._send_raw(msg)
        return {"ok": True, "interval_ms": interval_ms}

    def reset_stats(self):
        """Reset packet counters."""
        self.packets_received = 0
        self.bytes_received = 0
        self.last_seq = 0
        self.last_timestamp = 0

    # ── Internal: send ──────────────────────────────────────────

    def _send_raw(self, msg: pb.PlcMessage):
        """Serialize and send a PlcMessage over TCP with length framing."""
        if not self._tcp_sock:
            return
        data = frame_message(msg.SerializeToString())
        try:
            self._tcp_sock.sendall(data)
        except Exception as e:
            self.connected = False
            self._tcp_sock = None
            if self.on_disconnect:
                self.on_disconnect(f"TCP send error: {e}")

    def _send_subscribe_chunked(self, var_ids: list[int], action: int,
                                interval_ms: int | None,
                                chunk_size: int):
        """Send subscription in chunks to avoid exceeding PLC buffer."""
        if len(var_ids) <= chunk_size:
            msg = build_subscribe(action, var_ids, interval_ms)
            self._send_raw(msg)
            return

        for i in range(0, len(var_ids), chunk_size):
            chunk = var_ids[i:i + chunk_size]
            chunk_action = action if i == 0 else ACTION_ADD
            if i > 0:
                time.sleep(0.05)  # Let PLC process previous chunk
            msg = build_subscribe(chunk_action, chunk,
                                  interval_ms if i == 0 else None)
            self._send_raw(msg)

    # ── Internal: receive ───────────────────────────────────────

    def _tcp_receive_loop(self):
        """Background thread: receive length-delimited messages from PLC."""
        buf = b""
        while self._running:
            try:
                chunk = self._tcp_sock.recv(65536)
                if not chunk:
                    self.connected = False
                    if self.on_disconnect:
                        self.on_disconnect("PLC closed connection")
                    break
                buf += chunk
                buf = self._process_tcp_buffer(buf)
            except socket.timeout:
                continue
            except OSError as e:
                self.connected = False
                if self.on_disconnect:
                    self.on_disconnect(f"TCP error: {e}")
                break

    def _udp_receive_loop(self):
        """Background thread: receive protobuf VarUpdatePacket via UDP."""
        while self._running:
            try:
                data, _ = self._udp_sock.recvfrom(1500)
                if data and len(data) >= 2:
                    self._decode_udp_packet(data)
            except socket.timeout:
                continue
            except OSError:
                break

    def _process_tcp_buffer(self, buf: bytes) -> bytes:
        """Process complete messages from TCP buffer."""
        messages, remaining = read_framed_messages(buf)

        for pb_bytes in messages:
            try:
                msg = pb.PlcMessage()
                msg.ParseFromString(pb_bytes)
                self._handle_message(msg, len(pb_bytes))
            except Exception:
                pass  # Skip malformed messages

        return remaining

    def _handle_message(self, msg: pb.PlcMessage, byte_count: int):
        """Route a decoded PlcMessage to the appropriate handler."""
        if msg.type == MSG_VAR_UPDATE and msg.HasField("update"):
            self._handle_update(msg.update, byte_count)
        elif msg.type == MSG_HEARTBEAT and msg.HasField("update"):
            sub_count = msg.update.sequence
            reg_count = msg.update.timestamp
            if self.on_heartbeat:
                self.on_heartbeat(sub_count, reg_count)
        elif msg.type == MSG_CONFIG_RESPONSE and msg.HasField("config_resp"):
            self.transport_mode = msg.config_resp.transport

    def _handle_update(self, update, byte_count: int):
        """Process a VarUpdatePacket."""
        values = decode_var_values(update)

        self.packets_received += 1
        self.bytes_received += byte_count
        self.last_seq = update.sequence
        self.last_timestamp = update.timestamp

        # Cache values
        self.values.update(values)

        # Notify callback
        if values and self.on_update:
            self.on_update(update.sequence, update.timestamp, values)

    def _decode_udp_packet(self, data: bytes):
        """Decode a raw protobuf VarUpdatePacket from UDP."""
        try:
            update = pb.VarUpdatePacket()
            update.ParseFromString(data)
            if update.sequence == 0 and len(update.values) == 0:
                return
            self._handle_update(update, len(data))
        except Exception:
            pass
