"""
OPC UA Subscription Monitor Engine
Connects via asyncua, subscribes to gProtoTest variables,
tracks same metrics as PlcMonitorEngine for head-to-head comparison.
"""
import asyncio
import json
import math
import threading
import time
from collections import deque
from pathlib import Path
from typing import Callable

import asyncua


class OpcuaSubEngine:
    """OPC UA subscription monitor with stats identical to PlcMonitorEngine."""

    def __init__(self):
        self.url: str = ""
        self.connected = False

        # Variable info: node_id → {name, data_type}
        self.var_info: dict[str, dict] = {}
        self.name_to_nid: dict[str, str] = {}
        self.values: dict[str, any] = {}       # name → current value
        self.subscribed: set[str] = set()       # set of node_ids

        # Callback for live updates
        self._on_update: Callable | None = None

        # Background event loop for asyncua
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._client: asyncua.Client | None = None
        self._sub = None
        self._handles = []
        self._running = False

        # ── Stats (mirrors PlcMonitorEngine) ──
        self.stats = {
            "notifications": 0,
            "batches": 0,
            "dropped": 0,
        }
        self._stats_lock = threading.Lock()
        self._stats_start_time: float = 0.0
        self._last_notif_time: float = 0.0
        self._inter_batch_times: deque[float] = deque(maxlen=10000)
        self._batch_notif_counts: deque[int] = deque(maxlen=10000)
        self._current_batch_start: float = 0.0
        self._current_batch_count: int = 0
        self._BATCH_GAP_MS: float = 2.0  # group notifications within 2ms as one batch
        self._per_var_changes: dict[str, int] = {}   # name → change count
        self._per_var_prev: dict[str, any] = {}       # name → previous value
        self._per_var_notifs: dict[str, int] = {}     # name → notification count
        self._total_var_updates: int = 0

        # ── Benchmark state ──
        self._bench_running = False
        self._bench_start: float = 0.0
        self._bench_duration: float = 0.0
        self._bench_notifications: int = 0
        self._bench_batches: int = 0
        self._bench_var_changes: int = 0
        self._bench_drops: int = 0
        self._bench_inter_batch: list[float] = []
        self._bench_per_var_changes: dict[str, int] = {}
        self._bench_per_var_notifs: dict[str, int] = {}
        self._bench_prev_values: dict[str, any] = {}
        self._bench_done = False
        self._bench_result: dict | None = None
        self._bench_last_batch_time: float = 0.0
        self._bench_current_batch_count: int = 0
        self._bench_current_batch_start: float = 0.0

    # ── Connection ───────────────────────────────────────────────
    def connect(self, url: str) -> dict:
        """Connect to OPC UA server (asyncua in background thread)."""
        if self.connected:
            self.disconnect()

        self.url = url
        self._running = True
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

        # Wait for connection (up to 10s)
        for _ in range(100):
            if self.connected:
                return {"ok": True, "url": url}
            time.sleep(0.1)
        return {"ok": False, "error": "Connection timeout"}

    def _run_loop(self):
        """Background thread running asyncua event loop."""
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._async_connect())
        except Exception as e:
            print(f"[OPCUA] Connection error: {e}")
            self.connected = False

    async def _async_connect(self):
        """Async connection + keep-alive loop."""
        self._client = asyncua.Client(self.url)
        await self._client.connect()
        self.connected = True
        print(f"[OPCUA] Connected to {self.url}")

        try:
            # Keep the loop alive while running
            while self._running:
                await asyncio.sleep(0.1)
        finally:
            if self._sub:
                try:
                    await self._sub.delete()
                except Exception:
                    pass
            try:
                await self._client.disconnect()
            except Exception:
                pass
            self.connected = False
            print("[OPCUA] Disconnected")

    def disconnect(self) -> dict:
        """Disconnect from OPC UA server."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        self._sub = None
        self._handles = []
        self._client = None
        self._loop = None
        self._thread = None
        self.connected = False
        self.subscribed.clear()
        return {"ok": True}

    # ── Discovery ────────────────────────────────────────────────
    def discover_gprototest(self) -> list[dict]:
        """Discover gProtoTest variables via OPC UA browse."""
        if not self.connected or not self._loop:
            return []
        future = asyncio.run_coroutine_threadsafe(
            self._async_discover(), self._loop)
        try:
            return future.result(timeout=15)
        except Exception as e:
            print(f"[OPCUA] Discover error: {e}")
            return []

    async def _async_discover(self) -> list[dict]:
        """Browse gProtoTest tree recursively."""
        result = []
        prefixes = ["::AsGlobalPV:gProtoTest", "::gProtoTest"]
        for pfx in prefixes:
            try:
                root = self._client.get_node(f"ns=6;s={pfx}")
                children = await root.get_children()
                if children:
                    await self._browse_leaves(root, "gProtoTest", result)
                    break
            except Exception:
                continue
        return result

    async def _browse_leaves(self, node, prefix: str, out: list):
        """Recursively find leaf variables."""
        children = await node.get_children()
        for child in children:
            name = (await child.read_browse_name()).Name
            cls = await child.read_node_class()
            full_name = f"{prefix}.{name}"
            if cls == asyncua.ua.NodeClass.Variable:
                nid = child.nodeid.to_string()
                try:
                    val = await child.read_value()
                    dt = type(val).__name__
                except Exception:
                    dt = "?"
                out.append({"name": full_name, "node_id": nid, "data_type": dt})
            else:
                await self._browse_leaves(child, full_name, out)

    def discover_from_registry(self) -> list[dict]:
        """Generate OPC UA node IDs from PLC registry file."""
        registry_path = Path(__file__).parent.parent / "plc_var_registry.json"
        if not registry_path.exists():
            return []
        with open(registry_path) as f:
            raw = json.load(f)

        result = []
        for idx_str, info in raw.items():
            if isinstance(info, dict) and info["name"].startswith("gProtoTest."):
                name = info["name"]
                nid = f"ns=6;s=::AsGlobalPV:{name}"
                result.append({
                    "name": name,
                    "node_id": nid,
                    "data_type": info.get("type", "?"),
                })
        return result

    # ── Subscribe ────────────────────────────────────────────────
    def subscribe(self, node_ids: list[str], var_names: list[str],
                  interval_ms: int = 50) -> dict:
        """Subscribe to variables via asyncua subscription."""
        if not self.connected or not self._loop:
            return {"ok": False, "error": "Not connected"}

        # Store var info
        self.var_info.clear()
        self.name_to_nid.clear()
        for nid, name in zip(node_ids, var_names):
            self.var_info[nid] = {"name": name}
            self.name_to_nid[name] = nid

        future = asyncio.run_coroutine_threadsafe(
            self._async_subscribe(node_ids, interval_ms), self._loop)
        try:
            result = future.result(timeout=15)
            self.subscribed = set(node_ids)
            # Reset stats
            self.reset_stats()
            return {"ok": True, "subscribed": len(node_ids),
                    "interval_ms": interval_ms}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    async def _async_subscribe(self, node_ids: list[str], interval_ms: int):
        """Create asyncua subscription."""
        if self._sub:
            try:
                await self._sub.delete()
            except Exception:
                pass

        handler = self._NotifHandler(self)
        self._sub = await self._client.create_subscription(interval_ms, handler)
        nodes = [self._client.get_node(nid) for nid in node_ids]
        self._handles = await self._sub.subscribe_data_change(nodes)
        print(f"[OPCUA] Subscribed {len(nodes)} vars, interval={interval_ms}ms")

    class _NotifHandler:
        """asyncua datachange notification handler."""
        def __init__(self, engine: "OpcuaSubEngine"):
            self._engine = engine

        def datachange_notification(self, node, val, data):
            self._engine._on_notification(node.nodeid.to_string(), val)

    # ── Notification Processing ──────────────────────────────────
    def _on_notification(self, node_id: str, value):
        """Called from asyncua thread for each datachange."""
        py_now = time.perf_counter()
        info = self.var_info.get(node_id)
        if not info:
            return
        var_name = info["name"]

        # Update value cache
        self.values[var_name] = value

        with self._stats_lock:
            # First notification starts the clock
            if self.stats["notifications"] == 0:
                self._stats_start_time = py_now
                self._current_batch_start = py_now
                self._current_batch_count = 0

            self.stats["notifications"] += 1
            self._total_var_updates += 1
            self._per_var_notifs[var_name] = self._per_var_notifs.get(var_name, 0) + 1

            # Batch detection: group notifications within BATCH_GAP_MS
            if self._current_batch_count == 0:
                # New batch
                self._current_batch_start = py_now
                self._current_batch_count = 1
            else:
                gap_ms = (py_now - self._current_batch_start) * 1000
                if gap_ms > self._BATCH_GAP_MS * self._current_batch_count:
                    # Flush previous batch
                    self._flush_batch(py_now)
                    self._current_batch_start = py_now
                    self._current_batch_count = 1
                else:
                    self._current_batch_count += 1

            # Per-variable change tracking
            prev = self._per_var_prev.get(var_name)
            if prev is not None and prev != value:
                self._per_var_changes[var_name] = self._per_var_changes.get(var_name, 0) + 1
            self._per_var_prev[var_name] = value

        # Benchmark recording
        if self._bench_running:
            self._record_benchmark(var_name, value, py_now)

        # Notify callback
        if self._on_update:
            self._on_update(var_name, value)

    def _flush_batch(self, py_now: float):
        """Record a completed batch (publish cycle)."""
        self.stats["batches"] += 1
        self._batch_notif_counts.append(self._current_batch_count)
        if self._last_notif_time > 0:
            dt_ms = (py_now - self._last_notif_time) * 1000
            self._inter_batch_times.append(dt_ms)
        self._last_notif_time = py_now

    def set_on_update(self, callback):
        self._on_update = callback

    # ── Stats ────────────────────────────────────────────────────
    def reset_stats(self):
        with self._stats_lock:
            self.stats = {"notifications": 0, "batches": 0, "dropped": 0}
            self._stats_start_time = time.perf_counter()
            self._last_notif_time = 0.0
            self._inter_batch_times.clear()
            self._batch_notif_counts.clear()
            self._current_batch_start = 0.0
            self._current_batch_count = 0
            self._per_var_changes.clear()
            self._per_var_prev.clear()
            self._per_var_notifs.clear()
            self._total_var_updates = 0

    def get_detailed_stats(self) -> dict:
        """Return comprehensive stats (same structure as PlcMonitorEngine)."""
        with self._stats_lock:
            # Flush pending batch
            if self._current_batch_count > 0:
                self._flush_batch(time.perf_counter())
                self._current_batch_count = 0

            elapsed = time.perf_counter() - self._stats_start_time if self._stats_start_time else 0
            notifs = self.stats["notifications"]
            batches = self.stats["batches"]
            batch_rate = batches / elapsed if elapsed > 0 else 0
            notif_rate = notifs / elapsed if elapsed > 0 else 0

            # Inter-batch timing (= inter-packet equivalent)
            ibt = list(self._inter_batch_times)
            ibt_stats = self._calc_timing_stats(ibt) if ibt else {}

            # Per-variable change rates (top 30)
            per_var = []
            for name, cnt in sorted(self._per_var_changes.items(), key=lambda x: -x[1])[:30]:
                per_var.append({
                    "name": name,
                    "plc_type": self.var_info.get(
                        self.name_to_nid.get(name, ""), {}).get("data_type", "?"),
                    "changes": cnt,
                    "rate": round(cnt / elapsed, 1) if elapsed > 0 else 0,
                    "notifications": self._per_var_notifs.get(name, 0),
                })

            total_changes = sum(self._per_var_changes.values())
            n_subs = len(self.subscribed)

            return {
                "elapsed_s": round(elapsed, 1),
                "packets_received": batches,  # batches = packet equivalent
                "packet_rate": round(batch_rate, 1),
                "total_var_updates": self._total_var_updates,
                "var_update_rate": round(notif_rate, 1),
                "total_var_changes": total_changes,
                "var_change_rate": round(total_changes / elapsed, 1) if elapsed > 0 else 0,
                "dropped_packets": self.stats["dropped"],
                "drop_pct": 0,
                "bytes_received": 0,  # N/A for OPC UA
                "subscribed_count": n_subs,
                "inter_packet_ms": ibt_stats,   # inter-batch timing
                "plc_interval_ms": {},           # N/A (no PLC timestamp)
                "per_variable": per_var,
                "grade": self._compute_grade(batch_rate, self.stats["dropped"], ibt_stats),
            }

    @staticmethod
    def _calc_timing_stats(values: list[float]) -> dict:
        if not values:
            return {}
        n = len(values)
        s = sorted(values)
        avg = sum(s) / n
        variance = sum((x - avg) ** 2 for x in s) / n
        return {
            "count": n,
            "min": round(s[0], 3),
            "max": round(s[-1], 3),
            "avg": round(avg, 3),
            "median": round(s[n // 2], 3),
            "stddev": round(math.sqrt(variance), 3),
            "p95": round(s[int(n * 0.95)], 3) if n >= 20 else None,
            "p99": round(s[int(n * 0.99)], 3) if n >= 100 else None,
        }

    @staticmethod
    def _compute_grade(batch_rate: float, drops: int, ibt: dict) -> dict:
        grades = {}
        if batch_rate >= 90:
            grades["packet_rate"] = "EXCELLENT"
        elif batch_rate >= 50:
            grades["packet_rate"] = "GOOD"
        elif batch_rate >= 10:
            grades["packet_rate"] = "FAIR"
        else:
            grades["packet_rate"] = "POOR"

        if drops == 0:
            grades["integrity"] = "PERFECT"
        elif drops < 5:
            grades["integrity"] = "GOOD"
        elif drops < 50:
            grades["integrity"] = "FAIR"
        else:
            grades["integrity"] = "POOR"

        jitter = ibt.get("stddev", 999)
        if jitter < 2:
            grades["jitter"] = "EXCELLENT"
        elif jitter < 5:
            grades["jitter"] = "GOOD"
        elif jitter < 20:
            grades["jitter"] = "FAIR"
        else:
            grades["jitter"] = "POOR"

        order = {"EXCELLENT": 4, "PERFECT": 4, "GOOD": 3, "FAIR": 2, "POOR": 1}
        worst = min(order.get(g, 0) for g in grades.values())
        rev = {4: "EXCELLENT", 3: "GOOD", 2: "FAIR", 1: "POOR"}
        grades["overall"] = rev.get(worst, "POOR")
        return grades

    # ── Benchmark ────────────────────────────────────────────────
    def start_benchmark(self, duration_s: float = 10.0) -> dict:
        if self._bench_running:
            return {"ok": False, "error": "Benchmark already running"}
        if not self.connected or not self.subscribed:
            return {"ok": False, "error": "Not connected or no subscription"}

        self._bench_running = True
        self._bench_done = False
        self._bench_result = None
        self._bench_start = time.perf_counter()
        self._bench_duration = duration_s
        self._bench_notifications = 0
        self._bench_batches = 0
        self._bench_var_changes = 0
        self._bench_drops = 0
        self._bench_inter_batch = []
        self._bench_per_var_changes = {}
        self._bench_per_var_notifs = {}
        self._bench_prev_values = {}
        self._bench_last_batch_time = 0.0
        self._bench_current_batch_count = 0
        self._bench_current_batch_start = 0.0
        return {"ok": True, "duration_s": duration_s}

    def _record_benchmark(self, var_name: str, value, py_time: float):
        if not self._bench_running:
            return
        elapsed = py_time - self._bench_start
        if elapsed >= self._bench_duration:
            self._finalize_benchmark()
            return

        self._bench_notifications += 1
        self._bench_per_var_notifs[var_name] = self._bench_per_var_notifs.get(var_name, 0) + 1

        # Batch detection
        if self._bench_current_batch_count == 0:
            self._bench_current_batch_start = py_time
            self._bench_current_batch_count = 1
        else:
            gap_ms = (py_time - self._bench_current_batch_start) * 1000
            if gap_ms > self._BATCH_GAP_MS * self._bench_current_batch_count:
                # Flush batch
                self._bench_batches += 1
                if self._bench_last_batch_time > 0:
                    dt = (py_time - self._bench_last_batch_time) * 1000
                    self._bench_inter_batch.append(dt)
                self._bench_last_batch_time = py_time
                self._bench_current_batch_start = py_time
                self._bench_current_batch_count = 1
            else:
                self._bench_current_batch_count += 1

        # Per-variable changes
        prev = self._bench_prev_values.get(var_name)
        if prev is not None and prev != value:
            self._bench_var_changes += 1
            self._bench_per_var_changes[var_name] = \
                self._bench_per_var_changes.get(var_name, 0) + 1
        self._bench_prev_values[var_name] = value

    def _finalize_benchmark(self):
        self._bench_running = False
        elapsed = time.perf_counter() - self._bench_start
        batches = self._bench_batches
        batch_rate = batches / elapsed if elapsed > 0 else 0
        notif_rate = self._bench_notifications / elapsed if elapsed > 0 else 0

        ibt_stats = self._calc_timing_stats(self._bench_inter_batch) \
            if self._bench_inter_batch else {}

        per_var = []
        for name, cnt in sorted(self._bench_per_var_changes.items(), key=lambda x: -x[1]):
            per_var.append({
                "name": name,
                "plc_type": self.var_info.get(
                    self.name_to_nid.get(name, ""), {}).get("data_type", "?"),
                "changes": cnt,
                "rate": round(cnt / elapsed, 1) if elapsed > 0 else 0,
                "notifications": self._bench_per_var_notifs.get(name, 0),
            })

        n_subs = len(self.subscribed)
        self._bench_result = {
            "elapsed_s": round(elapsed, 2),
            "packets": batches,   # batches = packet equivalent
            "packet_rate": round(batch_rate, 1),
            "var_updates": self._bench_notifications,
            "var_update_rate": round(notif_rate, 1),
            "var_changes": self._bench_var_changes,
            "var_change_rate": round(self._bench_var_changes / elapsed, 1) if elapsed > 0 else 0,
            "dropped_packets": self._bench_drops,
            "drop_pct": 0,
            "subscribed_count": n_subs,
            "inter_packet_ms": ibt_stats,
            "plc_interval_ms": {},
            "per_variable": per_var,
            "grade": self._compute_grade(batch_rate, self._bench_drops, ibt_stats),
        }
        self._bench_done = True

    def get_benchmark_status(self) -> dict:
        if self._bench_done and self._bench_result:
            return {"status": "done", "result": self._bench_result}
        if self._bench_running:
            elapsed = time.perf_counter() - self._bench_start
            return {
                "status": "running",
                "elapsed_s": round(elapsed, 1),
                "duration_s": self._bench_duration,
                "notifications": self._bench_notifications,
            }
        return {"status": "idle"}

    # ── Helpers ──────────────────────────────────────────────────
    def get_all_values(self) -> dict:
        return dict(self.values)
