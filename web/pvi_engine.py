"""PVI engine — B&R PVI (ANSL) connection, variable monitoring with per-var refresh times.

Architecture:
- Pure doEvents() loop for everything (start/stop unlinks all objects on exit!)
- All PVI object creation happens on the PVI thread via command queue
"""
import queue
import threading
import time
import statistics
from typing import Callable, Any


class PviEngine:
    """Manages a PVI connection to a B&R PLC and monitors variables."""

    def __init__(self):
        self.connected = False
        self.ip = ""
        self._pvi_conn = None
        self._line = None
        self._device = None
        self._cpu = None
        self._pvi_thread: threading.Thread | None = None
        self._pvi_running = False
        self._lock = threading.Lock()
        self._error: str | None = None
        self._cmd_queue: queue.Queue = queue.Queue()
        # tracking for monitor test
        self._tracking: dict[str, dict] = {}
        self._monitor_active = False

    def _exec_on_pvi_thread(self, fn, timeout=30):
        """Schedule fn on PVI thread, wait for result."""
        result_event = threading.Event()
        result_holder = [None, None]  # [result, exception]

        def _wrapper():
            try:
                result_holder[0] = fn()
            except Exception as e:
                result_holder[1] = e
            result_event.set()

        self._cmd_queue.put(_wrapper)
        result_event.wait(timeout=timeout)
        if result_holder[1]:
            raise result_holder[1]
        return result_holder[0]

    # ── connection ───────────────────────────────────────────────
    def connect(self, ip: str) -> dict:
        """Connect to PLC via PVI ANSL over TCP/IP using pure doEvents loop."""
        if self.connected:
            self.disconnect()

        try:
            from pvi import Connection, Line, Device, Cpu
        except ImportError as e:
            return {"ok": False, "error": f"pvipy not installed: {e}"}

        self._error = None
        self.ip = ip
        ready_event = threading.Event()
        connect_result = {"ok": False, "error": "Timeout waiting for PVI connection"}

        def _pvi_thread():
            nonlocal connect_result
            try:
                self._pvi_conn = Connection()
                self._line = Line(self._pvi_conn.root, 'LNANSL', CD='LNANSL')
                self._device = Device(self._line, 'TCP', CD='/IF=TcpIp')
                self._cpu = Cpu(self._device, 'plc', CD=f'/IP={ip}')

                def cpu_error_changed(error: int):
                    nonlocal connect_result
                    if error == 0:
                        self.connected = True
                        connect_result = {"ok": True, "ip": ip}
                        ready_event.set()
                    else:
                        self._error = f"PVI CPU error: {error}"
                        connect_result = {"ok": False, "error": self._error}
                        ready_event.set()

                self._cpu.errorChanged = cpu_error_changed
                self._pvi_running = True

                # Pure doEvents loop — no start/stop (start() unlinks objects on exit)
                while self._pvi_running:
                    # Process queued commands
                    while not self._cmd_queue.empty():
                        try:
                            cmd = self._cmd_queue.get_nowait()
                            cmd()
                        except queue.Empty:
                            break
                    self._pvi_conn.doEvents()

            except Exception as e:
                connect_result = {"ok": False, "error": str(e)}
                ready_event.set()

        self._pvi_thread = threading.Thread(target=_pvi_thread, daemon=True)
        self._pvi_thread.start()

        ready_event.wait(timeout=12)
        if not self.connected:
            if connect_result.get("error") == "Timeout waiting for PVI connection":
                self._pvi_running = False
        return connect_result

    def disconnect(self) -> dict:
        """Disconnect PVI and clean up."""
        self._pvi_running = False
        self._monitor_active = False
        if self._pvi_thread:
            self._pvi_thread.join(timeout=5)
        self._pvi_conn = None
        self._line = None
        self._device = None
        self._cpu = None
        self.connected = False
        return {"ok": True}

    # ── list tasks & variables ───────────────────────────────────
    def list_tasks(self) -> list[str]:
        if not self.connected or not self._cpu:
            return []
        try:
            return self._exec_on_pvi_thread(lambda: self._cpu.tasks)
        except Exception:
            return []

    def list_global_vars(self) -> list[str]:
        if not self.connected or not self._cpu:
            return []
        try:
            return self._exec_on_pvi_thread(lambda: self._cpu.variables)
        except Exception:
            return []

    # ── monitor test ─────────────────────────────────────────────
    def run_pvi_monitor(self, var_configs: list[dict], duration_sec: int,
                        plc_cycle_ms: float,
                        log: Callable[[str], None],
                        progress: Callable[[int], None],
                        stop: Callable[[], bool]) -> dict:
        """
        Monitor variables via PVI with per-variable refresh times.
        Variables are created on the PVI thread via command queue.
        """
        from pvi import Variable

        UINT_MAX = 4294967296
        total_vars = len(var_configs)

        log("\n" + "=" * 60)
        log("PVI MONITOR — per-variable refresh times")
        log("=" * 60)
        log(f"  Variables: {total_vars}")
        log(f"  Duration: {duration_sec}s")
        log(f"  PLC cycle: {plc_cycle_ms}ms")

        rf_groups = {}
        for vc in var_configs:
            rf = vc["refresh_ms"]
            rf_groups.setdefault(rf, []).append(vc["name"])
        for rf, names in sorted(rf_groups.items()):
            log(f"  RF={rf}ms: {len(names)} vars ({names[0]}..{names[-1]})")
        log("")

        # Init tracking
        self._tracking.clear()
        for vc in var_configs:
            self._tracking[vc["name"]] = {
                "name": vc["name"],
                "refresh_ms": vc["refresh_ms"],
                "notifications": 0,
                "changes": 0,
                "missed": 0,
                "prev_val": None,
                "first_val": None,
                "last_val": None,
                "gaps_ms": [],
                "last_ts": None,
            }

        # Create PVI variables ON the PVI thread in batches
        BATCH_SIZE = 10
        EVENTS_PER_BATCH = 50  # doEvents() calls between batches
        WARMUP_SEC = 1.0       # let PVI settle after creation

        log(f"  Creating {total_vars} PVI variable objects (batches of {BATCH_SIZE})...")
        created_vars = []

        def _create_batch(batch_configs):
            """Create one batch of variables, with doEvents() pumping between."""
            batch_created = []
            for vc in batch_configs:
                name = vc["name"]
                rf = vc["refresh_ms"]
                try:
                    pvi_var = Variable(self._cpu, name, RF=rf)

                    def make_callback(var_name):
                        def on_value_changed(value):
                            vd = self._tracking.get(var_name)
                            if not vd or not self._monitor_active:
                                return
                            now = time.perf_counter() * 1000
                            vd["notifications"] += 1
                            vd["last_val"] = value
                            if vd["first_val"] is None:
                                vd["first_val"] = value
                            if vd["prev_val"] is not None and value != vd["prev_val"]:
                                vd["changes"] += 1
                                try:
                                    delta = int(value) - int(vd["prev_val"])
                                    if delta < 0:
                                        delta += UINT_MAX
                                    if delta > 1:
                                        vd["missed"] += (delta - 1)
                                except (ValueError, TypeError):
                                    pass
                            vd["prev_val"] = value
                            if vd["last_ts"] is not None:
                                vd["gaps_ms"].append(now - vd["last_ts"])
                            vd["last_ts"] = now
                        return on_value_changed

                    pvi_var.valueChanged = make_callback(name)
                    batch_created.append(pvi_var)
                except Exception as e:
                    log(f"  ERROR creating {name}: {e}")
            # Pump events so PVI can process link replies
            for _ in range(EVENTS_PER_BATCH):
                self._pvi_conn.doEvents()
            return batch_created

        # Create in batches
        for i in range(0, total_vars, BATCH_SIZE):
            batch = var_configs[i:i + BATCH_SIZE]
            result = self._exec_on_pvi_thread(
                lambda b=batch: _create_batch(b), timeout=15)
            created_vars.extend(result)

        log(f"  Created {len(created_vars)} variables")

        # Warm-up: let PVI settle so all vars get initial values
        self._monitor_active = True  # enable callbacks during warm-up
        log(f"  Warm-up ({WARMUP_SEC}s) — letting PVI settle...")
        time.sleep(WARMUP_SEC)
        linked = sum(1 for vd in self._tracking.values() if vd["notifications"] > 0)
        log(f"  After warm-up: {linked}/{total_vars} vars have received data")

        # Reset counters so warm-up data doesn't pollute measurements
        for vd in self._tracking.values():
            vd["notifications"] = 0
            vd["changes"] = 0
            vd["missed"] = 0
            vd["first_val"] = None
            vd["last_val"] = vd["prev_val"]  # keep last known value for delta calc
            vd["gaps_ms"] = []
            vd["last_ts"] = None

        log(f"  Measuring for {duration_sec}s...")

        self._monitor_active = True
        start_t = time.perf_counter()
        while (time.perf_counter() - start_t) < duration_sec:
            if stop():
                break
            elapsed_pct = int((time.perf_counter() - start_t) / duration_sec * 90)
            progress(min(elapsed_pct, 90))
            time.sleep(0.1)

        self._monitor_active = False
        dur = time.perf_counter() - start_t

        # Cleanup PVI variables on PVI thread
        log(f"  Collection complete ({dur:.1f}s). Cleaning up...")

        def _kill_all_vars():
            for v in created_vars:
                try:
                    v.kill()
                except Exception:
                    pass

        self._exec_on_pvi_thread(_kill_all_vars, timeout=15)

        # ── Per-variable results ──
        per_var = {}
        for name, vd in self._tracking.items():
            gaps = vd["gaps_ms"]
            per_var[name] = {
                "name": name,
                "refresh_ms": vd["refresh_ms"],
                "notifications": vd["notifications"],
                "changes": vd["changes"],
                "missed": vd["missed"],
                "avg_gap_ms": round(statistics.mean(gaps), 2) if gaps else 0,
                "min_gap_ms": round(min(gaps), 2) if gaps else 0,
                "max_gap_ms": round(max(gaps), 2) if gaps else 0,
            }

        # ── PLC tier definitions ──
        tier_defs = [
            {"label": "~1.6ms (every cycle)", "first": 1, "last": 10,
             "cycles_per_change": 1},
            {"label": "~5ms (every 3 cycles)", "first": 11, "last": 20,
             "cycles_per_change": 3},
            {"label": "~50ms (every 31 cycles)", "first": 21, "last": 30,
             "cycles_per_change": 31},
            {"label": "~100ms (every 63 cycles)", "first": 31, "last": 200,
             "cycles_per_change": 63},
        ]

        total_plc_cycles = int(dur * 1000 / plc_cycle_ms)

        log(f"\n{'=' * 60}")
        log(f"  PVI MONITOR REPORT")
        log(f"{'=' * 60}")
        log(f"  Duration: {dur:.1f}s | PLC cycles: ~{total_plc_cycles}")

        tiers_report = []
        for td in tier_defs:
            tier_vars = []
            for name, data in per_var.items():
                try:
                    num = int(name.replace("opctest", ""))
                    if td["first"] <= num <= td["last"]:
                        tier_vars.append(data)
                except ValueError:
                    pass

            if not tier_vars:
                continue

            n = len(tier_vars)
            expected_per_var = total_plc_cycles // td["cycles_per_change"]
            change_interval_ms = plc_cycle_ms * td["cycles_per_change"]

            total_notifs = sum(d["notifications"] for d in tier_vars)
            total_changes = sum(d["changes"] for d in tier_vars)
            total_missed = sum(d["missed"] for d in tier_vars)
            detect_pct = (total_changes / max(total_changes + total_missed, 1)) * 100
            perfect = sum(1 for d in tier_vars if d["missed"] == 0)

            if detect_pct >= 99:
                verdict = "PASS"
            elif detect_pct >= 90:
                verdict = "MOSTLY OK"
            elif detect_pct >= 50:
                verdict = "PARTIAL"
            else:
                verdict = "FAIL"

            log(f"\n  ── {td['label']} (opctest{td['first']}..{td['last']}) ──")
            log(f"     Vars: {n} | Refresh: various | Change every: {change_interval_ms:.1f}ms")
            log(f"     Expected changes/var: ~{expected_per_var}")
            log(f"     Notifications: {total_notifs} | Changes detected: {total_changes}")
            log(f"     Missed PLC increments: {total_missed}")
            log(f"     Detection: {detect_pct:.1f}% | Perfect: {perfect}/{n}")
            log(f"     Verdict: {verdict}")

            tiers_report.append({
                "label": td["label"],
                "first": td["first"],
                "last": td["last"],
                "vars": n,
                "change_ms": round(change_interval_ms, 1),
                "expected": expected_per_var,
                "notifications": total_notifs,
                "changes": total_changes,
                "missed": total_missed,
                "detect_pct": round(detect_pct, 1),
                "perfect": perfect,
                "verdict": verdict,
            })

        grand_notifs = sum(t["notifications"] for t in tiers_report)
        grand_changes = sum(t["changes"] for t in tiers_report)
        grand_missed = sum(t["missed"] for t in tiers_report)
        grand_pct = (grand_changes / max(grand_changes + grand_missed, 1)) * 100

        log(f"\n{'─' * 60}")
        log(f"  OVERALL: {grand_notifs} notifications, "
            f"{grand_changes} changes, {grand_missed} missed")
        log(f"  Detection rate: {grand_pct:.1f}%")

        per_var["_summary"] = {
            "duration_sec": round(dur, 1),
            "total_vars": total_vars,
            "plc_cycle_ms": plc_cycle_ms,
            "total_notifications": grand_notifs,
            "total_changes": grand_changes,
            "total_missed": grand_missed,
            "detect_pct": round(grand_pct, 1),
            "tiers": tiers_report,
        }

        progress(100)
        return per_var
