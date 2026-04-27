"""OPC UA engine — connection, browsing, benchmarks, tracing."""
import time
import asyncio
import random
import statistics
import threading
from typing import Callable
from opcua import Client, ua


class OpcuaEngine:
    """Manages a single OPC UA connection and provides test/trace operations."""

    def __init__(self):
        self.client: Client | None = None
        self.url: str = ""
        self.connected = False
        self._lock = threading.Lock()

    # ── connection ───────────────────────────────────────────────
    def connect(self, url: str) -> dict:
        with self._lock:
            if self.connected:
                self.disconnect()
            self.client = Client(url)
            self.client.set_security_string("")
            self.client.connect()
            self.url = url
            self.connected = True
        return {"ok": True, "url": url}

    def disconnect(self) -> dict:
        with self._lock:
            if self.client:
                try:
                    self.client.disconnect()
                except Exception:
                    pass
            self.client = None
            self.connected = False
        return {"ok": True}

    # ── tree browsing (lazy) ─────────────────────────────────────
    def browse(self, node_id: str | None = None) -> list[dict]:
        """Browse children of a node. None = root Objects node."""
        if not self.connected:
            return []
        if node_id is None:
            root = self.client.get_root_node()
            objects = root.get_child(["0:Objects"])
            return self._children(objects)
        node = self.client.get_node(node_id)
        return self._children(node)

    def _children(self, node) -> list[dict]:
        out = []
        try:
            for child in node.get_children():
                cls = child.get_node_class()
                is_var = cls == ua.NodeClass.Variable
                item = {
                    "id": child.nodeid.to_string(),
                    "name": child.get_browse_name().Name,
                    "is_variable": is_var,
                    "has_children": not is_var,
                }
                if is_var:
                    try:
                        val = child.get_value()
                        item["value"] = str(val) if not isinstance(val, (list, tuple)) else f"Array[{len(val)}]"
                        item["data_type"] = type(val).__name__
                    except Exception:
                        item["value"] = "?"
                        item["data_type"] = "?"
                out.append(item)
        except Exception:
            pass
        return out

    def read_value(self, node_id: str):
        node = self.client.get_node(node_id)
        return node.get_value()

    def read_values(self, node_ids: list[str]) -> list:
        return [self.read_value(nid) for nid in node_ids]

    # ── auto-discover opctest vars  ──────────────────────────────
    def discover_opctest(self, count: int = 200) -> list[dict]:
        prefixes = ["::AsGlobalPV:", "::IOSimulat:", "::gMainSimo:"]
        for pfx in prefixes:
            test_nid = f"ns=6;s={pfx}opctest1"
            try:
                node = self.client.get_node(test_nid)
                node.get_value()
                out = []
                for i in range(1, count + 1):
                    nid = f"ns=6;s={pfx}opctest{i}"
                    out.append({"name": f"opctest{i}", "node_id": nid})
                return out
            except Exception:
                continue
        return []

    # ── benchmark tests ──────────────────────────────────────────
    def run_benchmarks(self, config: dict, log: Callable[[str], None],
                       progress: Callable[[int], None],
                       stop: Callable[[], bool]) -> dict:
        results = {}
        node_ids = config["node_ids"]
        var_names = config["var_names"]

        if config.get("single_read"):
            results["single_read"] = self._test_single_read(
                node_ids, var_names, config.get("iterations", 100), log, progress, stop)
        if stop():
            return results

        if config.get("batch_read"):
            results["batch_read"] = self._test_batch_read(
                node_ids, var_names, config.get("iterations", 100), log, progress, stop)
        if stop():
            return results

        if config.get("throughput"):
            results["throughput"] = self._test_throughput(
                node_ids, var_names, config.get("throughput_duration", 5), log, progress, stop)
        if stop():
            return results

        if config.get("write_latency"):
            results["write_latency"] = self._test_write_latency(
                node_ids, var_names, config.get("iterations", 100), log, progress, stop)
        if stop():
            return results

        if config.get("round_trip"):
            results["round_trip"] = self._test_round_trip(
                node_ids, var_names, config.get("iterations", 100), log, progress, stop)
        if stop():
            return results

        if config.get("detection"):
            results["detection"] = self._test_detection(
                node_ids, var_names, config.get("detection_duration", 10),
                config.get("plc_cycle_ms", 1.6), log, progress, stop)
        if stop():
            return results

        if config.get("cycle_probe"):
            results["cycle_probe"] = self._test_cycle_probe(
                node_ids, var_names, config.get("cycle_probe_reads", 200),
                config.get("plc_cycle_ms", 1.6), log, progress, stop)

        if config.get("multi_rate"):
            # Auto-discover opctest vars — no manual selection needed
            discovered = self.discover_opctest(200)
            if discovered:
                mr_nids = [d["node_id"] for d in discovered]
                mr_names = [d["name"] for d in discovered]
                log(f"  Multi-Rate: auto-discovered {len(discovered)} opctest vars")
            else:
                mr_nids = node_ids
                mr_names = var_names
                log(f"  Multi-Rate: discovery failed, using {len(mr_nids)} selected vars")
            results["multi_rate"] = self._test_multi_rate(
                mr_nids, mr_names,
                config.get("multi_rate_batch", 50),
                config.get("multi_rate_duration", 10),
                config.get("plc_cycle_ms", 1.6),
                config.get("multi_rate_tiers", [
                    {"count": 10, "interval_ms": 2},
                    {"count": 10, "interval_ms": 5},
                    {"count": 10, "interval_ms": 10},
                    {"count": 10, "interval_ms": 50},
                    {"count": 10, "interval_ms": 100},
                ]),
                log, progress, stop)

        if config.get("subscription"):
            # Auto-discover opctest vars — same as multi_rate
            discovered = self.discover_opctest(200)
            if discovered:
                sub_nids = [d["node_id"] for d in discovered]
                sub_names = [d["name"] for d in discovered]
                log(f"  Subscription: auto-discovered {len(discovered)} opctest vars")
            else:
                sub_nids = node_ids
                sub_names = var_names
                log(f"  Subscription: using {len(sub_nids)} selected vars")
            results["subscription"] = self._test_subscription(
                sub_nids, sub_names,
                config.get("sub_duration", 10),
                config.get("sub_interval_ms", 10),
                config.get("sub_batch", 50),
                config.get("plc_cycle_ms", 1.6),
                log, progress, stop)

        if config.get("sub_monitor"):
            # Auto-discover all opctest vars
            discovered = self.discover_opctest(200)
            if discovered:
                sm_nids = [d["node_id"] for d in discovered]
                sm_names = [d["name"] for d in discovered]
            else:
                sm_nids = node_ids
                sm_names = var_names
            results["sub_monitor"] = self._test_sub_monitor(
                sm_nids, sm_names,
                config.get("sub_monitor_duration", 10),
                config.get("sub_monitor_interval", 10),
                config.get("plc_cycle_ms", 1.6),
                log, progress, stop)

        return results

    # ── single read  ─────────────────────────────────────────────
    def _test_single_read(self, node_ids, var_names, iterations, log, progress, stop):
        log("\n" + "=" * 60)
        log("SINGLE READ LATENCY TEST")
        log("=" * 60)
        log(f"  Iterations per variable: {iterations}\n")
        results = {}
        for idx, (nid, name) in enumerate(zip(node_ids, var_names)):
            if stop():
                return results
            node = self.client.get_node(nid)
            latencies = []
            errors = 0
            for i in range(iterations):
                t0 = time.perf_counter()
                try:
                    node.get_value()
                except Exception:
                    errors += 1
                latencies.append((time.perf_counter() - t0) * 1000)
            s = sorted(latencies)
            n = len(s)
            results[name] = {
                "min_ms": round(s[0], 3),
                "max_ms": round(s[-1], 3),
                "avg_ms": round(statistics.mean(s), 3),
                "median_ms": round(statistics.median(s), 3),
                "stddev_ms": round(statistics.stdev(s), 3) if n > 1 else 0,
                "p95_ms": round(s[int(n * 0.95)], 3),
                "p99_ms": round(s[int(n * 0.99)], 3),
                "errors": errors,
                "samples": iterations,
            }
            r = results[name]
            log(f"  {name}:")
            log(f"    Min={r['min_ms']} Avg={r['avg_ms']} Med={r['median_ms']} "
                f"P95={r['p95_ms']} Max={r['max_ms']} ms  Errors={errors}/{iterations}")
            progress(int((idx + 1) / len(node_ids) * 15))
        return results

    # ── batch read  ──────────────────────────────────────────────
    def _test_batch_read(self, node_ids, var_names, iterations, log, progress, stop):
        log("\n" + "=" * 60)
        log("BATCH READ LATENCY TEST")
        log("=" * 60)
        nodes = [self.client.get_node(nid) for nid in node_ids]
        latencies = []
        errors = 0
        for i in range(iterations):
            if stop():
                break
            t0 = time.perf_counter()
            try:
                for node in nodes:
                    node.get_value()
            except Exception:
                errors += 1
            latencies.append((time.perf_counter() - t0) * 1000)
            if i % 10 == 0:
                progress(15 + int(i / iterations * 10))
        s = sorted(latencies)
        n = len(s)
        result = {
            "min_ms": round(s[0], 3),
            "max_ms": round(s[-1], 3),
            "avg_ms": round(statistics.mean(s), 3),
            "median_ms": round(statistics.median(s), 3),
            "stddev_ms": round(statistics.stdev(s), 3) if n > 1 else 0,
            "p95_ms": round(s[int(n * 0.95)], 3),
            "num_variables": len(nodes),
            "avg_per_var_ms": round(statistics.mean(s) / len(nodes), 3),
            "errors": errors,
            "samples": iterations,
        }
        log(f"  Batch ({len(nodes)} vars): Min={result['min_ms']} Avg={result['avg_ms']} "
            f"P95={result['p95_ms']} ms  PerVar={result['avg_per_var_ms']} ms")
        return result

    # ── throughput  ──────────────────────────────────────────────
    def _test_throughput(self, node_ids, var_names, duration_sec, log, progress, stop):
        log("\n" + "=" * 60)
        log("THROUGHPUT TEST")
        log("=" * 60)
        nodes = [self.client.get_node(nid) for nid in node_ids]
        total_reads = 0
        errors = 0
        start = time.perf_counter()
        while (time.perf_counter() - start) < duration_sec:
            if stop():
                break
            for node in nodes:
                try:
                    node.get_value()
                    total_reads += 1
                except Exception:
                    errors += 1
            elapsed = time.perf_counter() - start
            progress(25 + int(elapsed / duration_sec * 15))
        elapsed = time.perf_counter() - start
        result = {
            "total_reads": total_reads,
            "duration_sec": round(elapsed, 2),
            "reads_per_sec": round(total_reads / elapsed, 1) if elapsed > 0 else 0,
            "errors": errors,
        }
        log(f"  {total_reads} reads in {elapsed:.1f}s = {result['reads_per_sec']} reads/sec  Errors={errors}")
        return result

    # ── write latency  ───────────────────────────────────────────
    def _test_write_latency(self, node_ids, var_names, iterations, log, progress, stop):
        log("\n" + "=" * 60)
        log("WRITE LATENCY TEST")
        log("=" * 60)
        results = {}
        for idx, (nid, name) in enumerate(zip(node_ids, var_names)):
            if stop():
                return results
            node = self.client.get_node(nid)
            try:
                original = node.get_value()
                dv = node.get_data_value()
            except Exception:
                log(f"  {name}: SKIPPED (cannot read)")
                continue
            latencies = []
            errors = 0
            for i in range(iterations):
                val = i % 256
                t0 = time.perf_counter()
                try:
                    node.set_value(ua.DataValue(ua.Variant(val, dv.Value.VariantType)))
                except Exception:
                    errors += 1
                latencies.append((time.perf_counter() - t0) * 1000)
            try:
                node.set_value(ua.DataValue(ua.Variant(original, dv.Value.VariantType)))
            except Exception:
                pass
            if latencies:
                s = sorted(latencies)
                n = len(s)
                results[name] = {
                    "min_ms": round(s[0], 3), "max_ms": round(s[-1], 3),
                    "avg_ms": round(statistics.mean(s), 3),
                    "median_ms": round(statistics.median(s), 3),
                    "stddev_ms": round(statistics.stdev(s), 3) if n > 1 else 0,
                    "p95_ms": round(s[int(n * 0.95)], 3),
                    "errors": errors, "samples": iterations,
                }
                r = results[name]
                log(f"  {name}: Min={r['min_ms']} Avg={r['avg_ms']} P95={r['p95_ms']} ms  Errors={errors}")
            progress(40 + int((idx + 1) / len(node_ids) * 10))
        return results

    # ── round trip ───────────────────────────────────────────────
    def _test_round_trip(self, node_ids, var_names, iterations, log, progress, stop):
        log("\n" + "=" * 60)
        log("WRITE-READ ROUND-TRIP LATENCY TEST")
        log("=" * 60)
        results = {}
        for idx, (nid, name) in enumerate(zip(node_ids, var_names)):
            if stop():
                return results
            node = self.client.get_node(nid)
            try:
                original = node.get_value()
                dv = node.get_data_value()
            except Exception:
                log(f"  {name}: SKIPPED")
                continue
            rt_latencies = []
            mismatches = 0
            errors = 0
            for i in range(iterations):
                val = (i + 1) % 10000
                t0 = time.perf_counter()
                try:
                    node.set_value(ua.DataValue(ua.Variant(val, dv.Value.VariantType)))
                    readback = node.get_value()
                    t1 = time.perf_counter()
                    if readback != val:
                        mismatches += 1
                except Exception:
                    t1 = time.perf_counter()
                    errors += 1
                rt_latencies.append((t1 - t0) * 1000)
            try:
                node.set_value(ua.DataValue(ua.Variant(original, dv.Value.VariantType)))
            except Exception:
                pass
            if rt_latencies:
                s = sorted(rt_latencies)
                n = len(s)
                results[name] = {
                    "min_ms": round(s[0], 3), "max_ms": round(s[-1], 3),
                    "avg_ms": round(statistics.mean(s), 3),
                    "median_ms": round(statistics.median(s), 3),
                    "p95_ms": round(s[int(n * 0.95)], 3),
                    "mismatches": mismatches, "errors": errors, "samples": iterations,
                }
                r = results[name]
                log(f"  {name}: Avg={r['avg_ms']} P95={r['p95_ms']} ms  Mismatch={mismatches} Err={errors}")
            progress(50 + int((idx + 1) / len(node_ids) * 10))
        return results

    # ── detection capability  ────────────────────────────────────
    def _test_detection(self, node_ids, var_names, duration_sec, plc_cycle_ms,
                        log, progress, stop):
        total_vars = len(node_ids)
        log("\n" + "=" * 60)
        log("DETECTION CAPABILITY TEST")
        log("=" * 60)
        log(f"  Variables: {total_vars} | Duration: {duration_sec}s per phase\n")

        nodes = [self.client.get_node(nid) for nid in node_ids]

        # Phase 1: single var speed
        log("  --- PHASE 1: Single Var Max Speed ---")
        single_times = []
        n0 = nodes[0]
        start = time.perf_counter()
        while (time.perf_counter() - start) < duration_sec:
            if stop():
                return {}
            t0 = time.perf_counter()
            try:
                n0.get_value()
            except Exception:
                pass
            single_times.append((time.perf_counter() - t0) * 1000)
        single_total = time.perf_counter() - start
        single_rate = len(single_times) / single_total
        single_med = statistics.median(single_times)
        s_sorted = sorted(single_times)
        single_p95 = s_sorted[int(len(s_sorted) * 0.95)]

        log(f"    Reads: {len(single_times)} | Rate: {single_rate:.0f}/s | "
            f"Med: {single_med:.2f}ms | P95: {single_p95:.2f}ms")
        progress(40)

        # Phase 2: round-robin scan
        log(f"\n  --- PHASE 2: Round-Robin Scan ({total_vars} vars) ---")
        scan_times = []
        start = time.perf_counter()
        while (time.perf_counter() - start) < duration_sec:
            if stop():
                return {}
            t0 = time.perf_counter()
            for node in nodes:
                try:
                    node.get_value()
                except Exception:
                    pass
            scan_times.append((time.perf_counter() - t0) * 1000)
        scan_total = time.perf_counter() - start
        scan_rate = len(scan_times) / scan_total
        scan_med = statistics.median(scan_times)
        sc_sorted = sorted(scan_times)
        scan_p95 = sc_sorted[int(len(sc_sorted) * 0.95)]

        log(f"    Scans: {len(scan_times)} | Rate: {scan_rate:.1f}/s | "
            f"Med: {scan_med:.1f}ms | P95: {scan_p95:.1f}ms")
        progress(70)

        # Phase 3: detection table
        log(f"\n  --- Detection Table ---")
        log(f"  {'Event':>10s}  {'1 var':>8s}  {f'{total_vars} vars':>10s}  {'Verdict':>10s}")
        log(f"  {'-'*10}  {'-'*8}  {'-'*10}  {'-'*10}")
        test_durations = [1, 2, 3, 5, 10, 20, 50, 100]
        table_rows = []
        for evt in test_durations:
            s_pct = min(evt / single_med, 1.0) * 100
            m_pct = min(evt / scan_med, 1.0) * 100
            if m_pct >= 95:
                verdict = "YES"
            elif m_pct >= 50:
                verdict = "LIKELY"
            elif s_pct >= 95:
                verdict = "1var only"
            elif s_pct >= 50:
                verdict = "MAYBE"
            else:
                verdict = "NO"
            log(f"  {evt:>8d}ms  {s_pct:>7.0f}%  {m_pct:>9.0f}%  {verdict:>10s}")
            table_rows.append({"event_ms": evt, "single_pct": round(s_pct, 1),
                               "multi_pct": round(m_pct, 1), "verdict": verdict})

        # limits
        limits = {}
        for target in [2, 5, 10, 50]:
            limits[f"{target}ms"] = max(int(target / single_med), 1)
        log(f"\n  --- Practical Limits ---")
        for k, v in limits.items():
            log(f"    {k} event: max ~{v} vars")

        log(f"\n  BOTTOM LINE: {single_med:.2f}ms/read")
        log(f"    1 var: catch ≥{single_p95:.1f}ms | {total_vars} vars: catch ≥{scan_p95:.1f}ms")
        progress(85)

        return {
            "single_read_ms": round(single_med, 3),
            "single_p95_ms": round(single_p95, 3),
            "single_rate": round(single_rate),
            "scan_vars": total_vars,
            "scan_ms": round(scan_med, 2),
            "scan_p95_ms": round(scan_p95, 2),
            "scan_rate": round(scan_rate, 1),
            "table": table_rows,
            "limits": limits,
        }

    # ── cycle probe  ─────────────────────────────────────────────
    def _test_cycle_probe(self, node_ids, var_names, reads_per_var, plc_cycle_ms,
                          log, progress, stop):
        log("\n" + "=" * 60)
        log("CYCLE LATENCY PROBE")
        log("=" * 60)
        log(f"  PLC cycle: {plc_cycle_ms}ms | Vars: {len(node_ids)} | Reads/var: {reads_per_var}\n")
        UINT_MAX = 4294967296
        results = {}
        nodes = [self.client.get_node(nid) for nid in node_ids]

        for vi, (node, name) in enumerate(zip(nodes, var_names)):
            if stop():
                return results
            latencies = []
            prev = None
            for r in range(reads_per_var):
                try:
                    val = node.get_value()
                    if prev is not None:
                        delta = val - prev
                        if delta < 0:
                            delta += UINT_MAX
                        if delta > 0:
                            latencies.append(delta * plc_cycle_ms)
                    prev = val
                except Exception:
                    pass
            if latencies:
                s = sorted(latencies)
                n = len(s)
                results[name] = {
                    "min_ms": round(s[0], 3), "max_ms": round(s[-1], 3),
                    "avg_ms": round(statistics.mean(s), 3),
                    "median_ms": round(statistics.median(s), 3),
                    "p95_ms": round(s[int(n * 0.95)], 3),
                    "samples": len(latencies),
                }
                r = results[name]
                log(f"  {name}: Med={r['median_ms']}ms P95={r['p95_ms']}ms ({len(latencies)} samples)")
            progress(85 + int((vi + 1) / len(nodes) * 15))

        if results:
            meds = [v["median_ms"] for v in results.values()]
            overall_med = statistics.median(meds)
            cycles = overall_med / plc_cycle_ms
            if cycles <= 2:
                grade = "EXCELLENT"
            elif cycles <= 5:
                grade = "GOOD"
            elif cycles <= 10:
                grade = "FAIR"
            else:
                grade = "POOR"
            log(f"\n  Overall median latency: {overall_med:.1f}ms ({cycles:.1f} PLC cycles)")
            log(f"  Grade: {grade}")
            results["_summary"] = {
                "overall_median_ms": round(overall_med, 2),
                "plc_cycles": round(cycles, 1),
                "grade": grade,
            }
        return results

    # ── multi-rate sampling test ─────────────────────────────────
    def _test_multi_rate(self, node_ids, var_names, batch_size, duration_sec,
                         plc_cycle_ms, tiers, log, progress, stop):
        """
        Split variables into batches of batch_size.
        Within each batch, assign tiers of different sampling rates.
        Default tiers: 10 vars @ 2ms, 10 @ 5ms, 10 @ 10ms, 10 @ 50ms, 10 @ 100ms.
        Run each batch for duration_sec, then move to next batch.
        Track: samples collected, values seen, missed changes, data integrity.
        """
        UINT_MAX = 4294967296
        total_vars = len(node_ids)
        num_batches = (total_vars + batch_size - 1) // batch_size

        log("\n" + "=" * 60)
        log("MULTI-RATE SAMPLING TEST")
        log("=" * 60)
        log(f"  Total vars: {total_vars} | Batch size: {batch_size} | Batches: {num_batches}")
        log(f"  Duration per batch: {duration_sec}s | PLC cycle: {plc_cycle_ms}ms")
        log(f"  Tiers:")
        for t in tiers:
            log(f"    {t['count']} vars @ {t['interval_ms']}ms")
        log("")

        all_results = {}

        for batch_idx in range(num_batches):
            if stop():
                return all_results

            b_start = batch_idx * batch_size
            b_end = min(b_start + batch_size, total_vars)
            b_nids = node_ids[b_start:b_end]
            b_names = var_names[b_start:b_end]
            b_count = len(b_nids)

            log(f"  ━━━ Batch {batch_idx + 1}/{num_batches}: vars {b_start + 1}..{b_end} ━━━")

            # Assign tiers to vars in this batch
            tier_assignments = []  # [(name, node_id, interval_ms, tier_label)]
            var_idx = 0
            for t in tiers:
                cnt = min(t["count"], b_count - var_idx)
                for j in range(cnt):
                    if var_idx < b_count:
                        tier_assignments.append((
                            b_names[var_idx], b_nids[var_idx],
                            t["interval_ms"], f"{t['interval_ms']}ms"
                        ))
                        var_idx += 1
                if var_idx >= b_count:
                    break
            # Any remaining vars get the last tier's interval
            if var_idx < b_count and tiers:
                last_ms = tiers[-1]["interval_ms"]
                for j in range(var_idx, b_count):
                    tier_assignments.append((
                        b_names[j], b_nids[j], last_ms, f"{last_ms}ms"
                    ))

            # Prepare nodes and tracking per variable
            var_data = []
            for name, nid, interval_ms, label in tier_assignments:
                node = self.client.get_node(nid)
                var_data.append({
                    "name": name, "node": node, "interval_ms": interval_ms,
                    "label": label,
                    "next_read_time": 0.0,
                    "samples": [],        # list of (timestamp_ms, value)
                    "read_times": [],      # read latencies in ms
                    "total_reads": 0,
                    "errors": 0,
                    "changes": 0,
                    "prev_val": None,
                    "first_val": None,
                    "last_val": None,
                    "missed_cycles": 0,    # PLC cycles missed between reads
                    "max_gap_ms": 0.0,
                })

            # Read initial values
            for vd in var_data:
                try:
                    val = vd["node"].get_value()
                    vd["prev_val"] = val
                    vd["first_val"] = val
                except Exception:
                    pass

            # Main sampling loop
            start = time.perf_counter()
            while (time.perf_counter() - start) < duration_sec:
                if stop():
                    return all_results
                now = time.perf_counter()
                now_ms = (now - start) * 1000

                did_work = False
                for vd in var_data:
                    if now_ms >= vd["next_read_time"]:
                        t0 = time.perf_counter()
                        try:
                            val = vd["node"].get_value()
                            t1 = time.perf_counter()
                            read_ms = (t1 - t0) * 1000
                            vd["read_times"].append(read_ms)
                            vd["total_reads"] += 1
                            vd["last_val"] = val

                            # Track changes and missed PLC cycles
                            if vd["prev_val"] is not None and val != vd["prev_val"]:
                                vd["changes"] += 1
                                delta = val - vd["prev_val"]
                                if delta < 0:
                                    delta += UINT_MAX
                                # Each PLC cycle increments by 1, so delta = missed PLC cycles
                                if delta > 1:
                                    vd["missed_cycles"] += (delta - 1)

                            vd["prev_val"] = val
                            vd["samples"].append((round(now_ms, 2), val))

                        except Exception:
                            t1 = time.perf_counter()
                            vd["errors"] += 1

                        # Schedule next read
                        vd["next_read_time"] = now_ms + vd["interval_ms"]
                        did_work = True

                if not did_work:
                    # Sleep briefly if no work to do
                    time.sleep(0.0002)  # 200us

            elapsed = time.perf_counter() - start

            # Report per-variable results for this batch
            log(f"\n  {'Variable':<14s} {'Rate':>6s} {'Reads':>7s} {'Changes':>8s} "
                f"{'Missed':>7s} {'AvgRead':>8s} {'ValΔ':>8s} {'Integrity':>10s}")
            log(f"  {'-'*14} {'-'*6} {'-'*7} {'-'*8} {'-'*7} {'-'*8} {'-'*8} {'-'*10}")

            for vd in var_data:
                name_short = vd["name"]
                total_reads = vd["total_reads"]
                changes = vd["changes"]
                missed = vd["missed_cycles"]
                avg_read = statistics.mean(vd["read_times"]) if vd["read_times"] else 0

                # Value delta: how many PLC cycles passed
                val_delta = 0
                if vd["first_val"] is not None and vd["last_val"] is not None:
                    val_delta = vd["last_val"] - vd["first_val"]
                    if val_delta < 0:
                        val_delta += UINT_MAX

                # Expected reads at this rate
                expected = int(duration_sec * 1000 / vd["interval_ms"])
                # Integrity: did we get all expected changes without gaps?
                # Perfect = missed_cycles == 0
                if missed == 0 and total_reads > 0:
                    integrity = "PERFECT"
                elif missed <= val_delta * 0.01:
                    integrity = "GOOD"
                elif missed <= val_delta * 0.1:
                    integrity = "FAIR"
                else:
                    integrity = "GAPS"

                log(f"  {name_short:<14s} {vd['label']:>6s} {total_reads:>7d} {changes:>8d} "
                    f"{missed:>7d} {avg_read:>7.2f}ms {val_delta:>8d} {integrity:>10s}")

                all_results[name_short] = {
                    "batch": batch_idx + 1,
                    "tier_ms": vd["interval_ms"],
                    "total_reads": total_reads,
                    "expected_reads": expected,
                    "changes": changes,
                    "missed_cycles": missed,
                    "avg_read_ms": round(avg_read, 3),
                    "min_read_ms": round(min(vd["read_times"]), 3) if vd["read_times"] else 0,
                    "max_read_ms": round(max(vd["read_times"]), 3) if vd["read_times"] else 0,
                    "val_delta": val_delta,
                    "integrity": integrity,
                    "errors": vd["errors"],
                    "duration_sec": round(elapsed, 2),
                }

            # Batch summary
            batch_vars = [v for k, v in all_results.items() if v.get("batch") == batch_idx + 1]
            total_missed = sum(v["missed_cycles"] for v in batch_vars)
            total_reads_batch = sum(v["total_reads"] for v in batch_vars)
            perfect_count = sum(1 for v in batch_vars if v["integrity"] == "PERFECT")

            log(f"\n  Batch {batch_idx + 1} summary: {total_reads_batch} reads, "
                f"{total_missed} missed PLC cycles, "
                f"{perfect_count}/{len(batch_vars)} vars with PERFECT integrity")

            pct = int((batch_idx + 1) / num_batches * 95)
            progress(pct)

        # Overall summary
        log(f"\n{'#'*60}")
        log(f"  MULTI-RATE SUMMARY")
        log(f"{'#'*60}")

        # Group by tier
        tier_groups = {}
        for name, data in all_results.items():
            tier = data.get("tier_ms", 0)
            if tier not in tier_groups:
                tier_groups[tier] = []
            tier_groups[tier].append(data)

        log(f"\n  {'Tier':>8s} {'Vars':>6s} {'AvgReads':>10s} {'AvgMissed':>10s} "
            f"{'Perfect%':>9s} {'AvgReadMs':>10s}")
        log(f"  {'-'*8} {'-'*6} {'-'*10} {'-'*10} {'-'*9} {'-'*10}")

        summary_tiers = []
        for tier_ms in sorted(tier_groups.keys()):
            group = tier_groups[tier_ms]
            n = len(group)
            avg_reads = sum(d["total_reads"] for d in group) / n
            avg_missed = sum(d["missed_cycles"] for d in group) / n
            perfect_pct = sum(1 for d in group if d["integrity"] == "PERFECT") / n * 100
            avg_read_ms = sum(d["avg_read_ms"] for d in group) / n

            log(f"  {tier_ms:>6d}ms {n:>6d} {avg_reads:>10.0f} {avg_missed:>10.0f} "
                f"{perfect_pct:>8.0f}% {avg_read_ms:>9.2f}ms")

            summary_tiers.append({
                "tier_ms": tier_ms, "vars": n,
                "avg_reads": round(avg_reads),
                "avg_missed": round(avg_missed),
                "perfect_pct": round(perfect_pct, 1),
                "avg_read_ms": round(avg_read_ms, 3),
            })

        all_results["_summary"] = {"tiers": summary_tiers, "total_vars": total_vars}

        log(f"\n  CONCLUSION:")
        for st in summary_tiers:
            if st["perfect_pct"] >= 95:
                verdict = "✓ Reliable"
            elif st["perfect_pct"] >= 50:
                verdict = "~ Partial gaps"
            else:
                verdict = "✗ Too fast for this setup"
            log(f"    {st['tier_ms']}ms rate: {verdict} ({st['perfect_pct']}% perfect)")

        progress(100)
        return all_results

    # ── subscription test (asyncua) ──────────────────────────────
    def _test_subscription(self, node_ids, var_names, duration_sec,
                           interval_ms, batch_size, plc_cycle_ms,
                           log, progress, stop):
        """
        Use asyncua Subscriptions (server push) instead of polling.
        Creates monitored items and counts every change notification.
        Compares with polling to show the difference.
        """
        UINT_MAX = 4294967296

        log("\n" + "=" * 60)
        log("OPC UA SUBSCRIPTION TEST (asyncua)")
        log("=" * 60)
        log(f"  Variables: {len(node_ids)} | Batch: {batch_size}")
        log(f"  Duration per batch: {duration_sec}s")
        log(f"  Requested sampling interval: {interval_ms}ms")
        log(f"  PLC cycle: {plc_cycle_ms}ms")
        log("")

        total_vars = len(node_ids)
        num_batches = (total_vars + batch_size - 1) // batch_size
        all_results = {}

        for batch_idx in range(num_batches):
            if stop():
                return all_results

            b_start = batch_idx * batch_size
            b_end = min(b_start + batch_size, total_vars)
            b_nids = node_ids[b_start:b_end]
            b_names = var_names[b_start:b_end]

            log(f"  ━━━ Batch {batch_idx + 1}/{num_batches}: {b_names[0]}..{b_names[-1]} ━━━")

            # Run the async subscription in a dedicated event loop
            batch_result = self._run_async_subscription_batch(
                b_nids, b_names, duration_sec, interval_ms, plc_cycle_ms, log, stop)

            all_results.update(batch_result)

            log(f"  Batch {batch_idx + 1} done: "
                f"{sum(v['notifications'] for v in batch_result.values())} total notifications")

            pct = int((batch_idx + 1) / num_batches * 95)
            progress(pct)

        # Overall summary
        log(f"\n{'#' * 60}")
        log(f"  SUBSCRIPTION TEST SUMMARY")
        log(f"{'#' * 60}")
        log(f"\n  {'Variable':<14s} {'Notifs':>8s} {'Changes':>8s} {'Missed':>8s} "
            f"{'AvgGap':>8s} {'MinGap':>8s} {'MaxGap':>8s} {'Integrity':>10s}")
        log(f"  {'-'*14} {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*10}")

        summary_data = []
        for name in var_names:
            if name not in all_results:
                continue
            d = all_results[name]
            integrity = d.get("integrity", "?")
            log(f"  {name:<14s} {d['notifications']:>8d} {d['changes']:>8d} {d['missed']:>8d} "
                f"{d['avg_gap_ms']:>7.1f}ms {d['min_gap_ms']:>7.1f}ms {d['max_gap_ms']:>7.1f}ms "
                f"{integrity:>10s}")
            summary_data.append(d)

        total_notifs = sum(d["notifications"] for d in summary_data)
        total_changes = sum(d["changes"] for d in summary_data)
        total_missed = sum(d["missed"] for d in summary_data)
        avg_miss_pct = (total_missed / max(total_changes + total_missed, 1)) * 100

        perfect = sum(1 for d in summary_data if d["integrity"] == "PERFECT")

        log(f"\n  Total notifications: {total_notifs}")
        log(f"  Total value changes detected: {total_changes}")
        log(f"  Total missed PLC cycles: {total_missed}")
        log(f"  Miss rate: {avg_miss_pct:.1f}%")
        log(f"  Perfect integrity: {perfect}/{len(summary_data)} vars")

        # Compare with polling expectation
        plc_changes_10s = int(duration_sec * 1000 / plc_cycle_ms)
        poll_expected = int(duration_sec * 1000 / 1.4)  # ~1.4ms per poll
        log(f"\n  Comparison (per var, {duration_sec}s window):")
        log(f"    PLC changes:       ~{plc_changes_10s}")
        log(f"    Polling reads:     ~{min(poll_expected, plc_changes_10s)} (limited by 1.4ms/read)")
        avg_sub_notifs = total_notifs // max(len(summary_data), 1)
        log(f"    Subscription:      ~{avg_sub_notifs} notifications")
        if avg_sub_notifs > poll_expected * 0.5:
            log(f"    ✓ Subscription is significantly better than polling!")
        elif avg_sub_notifs > 10:
            log(f"    ~ Subscription works but server limits throughput")
        else:
            log(f"    ✗ Subscription not effective for this configuration")

        # Per-tier breakdown (matches PLC multi-rate groups)
        tier_defs = [
            ("~1.6ms (every cycle)", 1, 10),
            ("~5ms (every 3 cycles)", 11, 20),
            ("~50ms (every 31 cycles)", 21, 30),
            ("~100ms (every 63 cycles)", 31, 200),
        ]
        tier_summary = []
        log(f"\n  ── Per-Tier Breakdown ──")
        log(f"  {'Tier':<28s} {'Vars':>5s} {'AvgNotifs':>10s} {'AvgChanges':>11s} "
            f"{'AvgMissed':>10s} {'MissRate':>9s} {'Perfect':>8s}")
        log(f"  {'-'*28} {'-'*5} {'-'*10} {'-'*11} {'-'*10} {'-'*9} {'-'*8}")

        for label, first, last in tier_defs:
            tier_vars = [d for d in summary_data
                         if d.get("var_idx") is not None and first <= d["var_idx"] <= last]
            if not tier_vars:
                # Fallback: match by name
                tier_vars = []
                for d in summary_data:
                    name = d.get("name", "")
                    try:
                        num = int(name.replace("opctest", ""))
                        if first <= num <= last:
                            tier_vars.append(d)
                    except ValueError:
                        pass
            if not tier_vars:
                continue

            n = len(tier_vars)
            a_notif = sum(d["notifications"] for d in tier_vars) / n
            a_change = sum(d["changes"] for d in tier_vars) / n
            a_missed = sum(d["missed"] for d in tier_vars) / n
            total_ch = sum(d["changes"] + d["missed"] for d in tier_vars)
            total_mi = sum(d["missed"] for d in tier_vars)
            miss_pct = (total_mi / max(total_ch, 1)) * 100
            perf = sum(1 for d in tier_vars if d["integrity"] == "PERFECT")

            log(f"  {label:<28s} {n:>5d} {a_notif:>10.0f} {a_change:>11.0f} "
                f"{a_missed:>10.0f} {miss_pct:>8.1f}% {perf:>4d}/{n}")

            tier_summary.append({
                "label": label, "vars": n,
                "avg_notifs": round(a_notif),
                "avg_changes": round(a_change),
                "avg_missed": round(a_missed),
                "miss_pct": round(miss_pct, 1),
                "perfect": perf,
            })

        all_results["_summary"] = {
            "total_vars": len(summary_data),
            "total_notifications": total_notifs,
            "total_changes": total_changes,
            "total_missed": total_missed,
            "miss_pct": round(avg_miss_pct, 1),
            "perfect_count": perfect,
            "duration_sec": duration_sec,
            "interval_ms": interval_ms,
            "batch_size": batch_size,
            "avg_notifs_per_var": total_notifs // max(len(summary_data), 1),
            "tiers": tier_summary,
        }

        progress(100)
        return all_results

    def _run_async_subscription_batch(self, node_ids, var_names,
                                      duration_sec, interval_ms,
                                      plc_cycle_ms, log, stop):
        """Run asyncua subscription in a new event loop (called from sync thread)."""
        import asyncua

        UINT_MAX = 4294967296
        # Shared data for the handler
        var_tracking = {}
        for name, nid in zip(var_names, node_ids):
            var_tracking[nid] = {
                "name": name,
                "notifications": 0,
                "changes": 0,
                "missed": 0,
                "prev_val": None,
                "first_val": None,
                "last_val": None,
                "timestamps_ms": [],
                "gaps_ms": [],
                "last_ts": None,
            }

        class SubHandler:
            def datachange_notification(self, node, val, data):
                nid_str = node.nodeid.to_string()
                vd = var_tracking.get(nid_str)
                if not vd:
                    return
                now = time.perf_counter() * 1000
                vd["notifications"] += 1
                vd["last_val"] = val

                if vd["first_val"] is None:
                    vd["first_val"] = val

                if vd["prev_val"] is not None and val != vd["prev_val"]:
                    vd["changes"] += 1
                    delta = val - vd["prev_val"]
                    if delta < 0:
                        delta += UINT_MAX
                    if delta > 1:
                        vd["missed"] += (delta - 1)

                vd["prev_val"] = val

                if vd["last_ts"] is not None:
                    gap = now - vd["last_ts"]
                    vd["gaps_ms"].append(gap)
                vd["last_ts"] = now

        async def _run():
            client = asyncua.Client(self.url)
            await client.set_security_string("")
            await client.connect()
            log(f"    asyncua connected to {self.url}")

            try:
                handler = SubHandler()
                sub = await client.create_subscription(interval_ms, handler)
                log(f"    Subscription created (interval={interval_ms}ms)")

                # Subscribe in chunks to avoid overwhelming
                nodes = [client.get_node(nid) for nid in node_ids]
                handles = await sub.subscribe_data_change(nodes)
                log(f"    Monitoring {len(nodes)} variables...")

                # Wait for duration or stop signal
                start = time.perf_counter()
                while (time.perf_counter() - start) < duration_sec:
                    if stop():
                        break
                    await asyncio.sleep(0.1)

                elapsed = time.perf_counter() - start
                log(f"    Collection done ({elapsed:.1f}s)")

                await sub.delete()
            finally:
                await client.disconnect()

        # Run in a fresh event loop on this thread
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(_run())
        finally:
            loop.close()

        # Build results
        results = {}
        for nid, vd in var_tracking.items():
            gaps = vd["gaps_ms"]
            results[vd["name"]] = {
                "name": vd["name"],
                "notifications": vd["notifications"],
                "changes": vd["changes"],
                "missed": vd["missed"],
                "avg_gap_ms": round(statistics.mean(gaps), 2) if gaps else 0,
                "min_gap_ms": round(min(gaps), 2) if gaps else 0,
                "max_gap_ms": round(max(gaps), 2) if gaps else 0,
                "p95_gap_ms": round(sorted(gaps)[int(len(gaps) * 0.95)] if len(gaps) > 1 else (gaps[0] if gaps else 0), 2),
                "integrity": self._calc_integrity(vd),
            }
        return results

    @staticmethod
    def _calc_integrity(vd):
        if vd["notifications"] == 0:
            return "NO DATA"
        total = vd["changes"] + vd["missed"]
        if total == 0:
            return "STATIC"
        miss_rate = vd["missed"] / total
        if miss_rate == 0:
            return "PERFECT"
        elif miss_rate < 0.01:
            return "GOOD"
        elif miss_rate < 0.1:
            return "FAIR"
        else:
            return "GAPS"

    # ── subscription monitor (all-in-one) ────────────────────────
    def _test_sub_monitor(self, node_ids, var_names, duration_sec,
                          interval_ms, plc_cycle_ms, log, progress, stop):
        """
        Subscribe to ALL vars at once via asyncua for duration_sec.
        Report per PLC-tier group: detected changes vs missed.
        PLC tiers (from Main.st):
          opctest1..10   every cycle   (~1.6ms)
          opctest11..20  every 3 cycles (~5ms)
          opctest21..30  every 31 cycles (~50ms)
          opctest31..200 every 63 cycles (~100ms)
        """
        import asyncua

        UINT_MAX = 4294967296
        total_vars = len(node_ids)

        log("\n" + "=" * 60)
        log("SUBSCRIPTION MONITOR — all vars, single subscription")
        log("=" * 60)
        log(f"  Variables: {total_vars}")
        log(f"  Duration: {duration_sec}s")
        log(f"  Requested sampling interval: {interval_ms}ms")
        log(f"  PLC cycle: {plc_cycle_ms}ms")
        log("")

        # Tracking per variable
        var_tracking = {}
        for name, nid in zip(var_names, node_ids):
            var_tracking[nid] = {
                "name": name,
                "notifications": 0,
                "changes": 0,
                "missed": 0,
                "prev_val": None,
                "first_val": None,
                "last_val": None,
                "gaps_ms": [],
                "last_ts": None,
            }

        class SubHandler:
            def datachange_notification(self, node, val, data):
                nid_str = node.nodeid.to_string()
                vd = var_tracking.get(nid_str)
                if not vd:
                    return
                now = time.perf_counter() * 1000
                vd["notifications"] += 1
                vd["last_val"] = val
                if vd["first_val"] is None:
                    vd["first_val"] = val
                if vd["prev_val"] is not None and val != vd["prev_val"]:
                    vd["changes"] += 1
                    delta = val - vd["prev_val"]
                    if delta < 0:
                        delta += UINT_MAX
                    if delta > 1:
                        vd["missed"] += (delta - 1)
                vd["prev_val"] = val
                if vd["last_ts"] is not None:
                    vd["gaps_ms"].append(now - vd["last_ts"])
                vd["last_ts"] = now

        actual_duration = [0.0]

        async def _run():
            client = asyncua.Client(self.url)
            await client.set_security_string("")
            await client.connect()
            log(f"  Connected (asyncua)")

            try:
                handler = SubHandler()
                sub = await client.create_subscription(interval_ms, handler)
                log(f"  Subscription created (publish interval={interval_ms}ms)")

                nodes = [client.get_node(nid) for nid in node_ids]
                await sub.subscribe_data_change(nodes)
                log(f"  Monitoring {len(nodes)} vars (default queue/sampling)")
                log(f"  Waiting {duration_sec}s...")

                start = time.perf_counter()
                while (time.perf_counter() - start) < duration_sec:
                    if stop():
                        break
                    elapsed_pct = int((time.perf_counter() - start) / duration_sec * 90)
                    progress(min(elapsed_pct, 90))
                    await asyncio.sleep(0.2)

                actual_duration[0] = time.perf_counter() - start
                log(f"  Collection complete ({actual_duration[0]:.1f}s)")

                await sub.delete()
            finally:
                await client.disconnect()

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(_run())
        finally:
            loop.close()

        dur = actual_duration[0]

        # ── Per-variable results ──
        per_var = {}
        for nid, vd in var_tracking.items():
            name = vd["name"]
            gaps = vd["gaps_ms"]
            per_var[name] = {
                "name": name,
                "notifications": vd["notifications"],
                "changes": vd["changes"],
                "missed": vd["missed"],
                "avg_gap_ms": round(statistics.mean(gaps), 2) if gaps else 0,
                "min_gap_ms": round(min(gaps), 2) if gaps else 0,
                "max_gap_ms": round(max(gaps), 2) if gaps else 0,
                "integrity": self._calc_integrity(vd),
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
        log(f"  SUBSCRIPTION MONITOR REPORT")
        log(f"{'=' * 60}")
        log(f"  Duration: {dur:.1f}s | PLC cycles: ~{total_plc_cycles}")
        log(f"  Subscription interval: {interval_ms}ms")

        tiers_report = []
        for td in tier_defs:
            # Collect vars in this tier
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
            total_expected = expected_per_var * n
            detect_pct = (total_changes / max(total_changes + total_missed, 1)) * 100
            perfect = sum(1 for d in tier_vars if d["integrity"] == "PERFECT")

            # Verdict
            if detect_pct >= 99:
                verdict = "PASS"
            elif detect_pct >= 90:
                verdict = "MOSTLY OK"
            elif detect_pct >= 50:
                verdict = "PARTIAL"
            else:
                verdict = "FAIL"

            log(f"\n  ── {td['label']} (opctest{td['first']}..{td['last']}) ──")
            log(f"     Vars: {n} | Change every: {change_interval_ms:.1f}ms")
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

        # Overall
        grand_notifs = sum(t["notifications"] for t in tiers_report)
        grand_changes = sum(t["changes"] for t in tiers_report)
        grand_missed = sum(t["missed"] for t in tiers_report)
        grand_pct = (grand_changes / max(grand_changes + grand_missed, 1)) * 100

        log(f"\n{'─' * 60}")
        log(f"  OVERALL: {grand_notifs} notifications, "
            f"{grand_changes} changes, {grand_missed} missed")
        log(f"  Detection rate: {grand_pct:.1f}%")

        if grand_pct >= 99:
            log(f"  ✓ Subscription captures virtually all changes")
        elif grand_pct >= 90:
            log(f"  ~ Subscription catches most, fast tiers have gaps")
        else:
            log(f"  ✗ Significant gaps — fast-changing vars overwhelm the server")

        per_var["_summary"] = {
            "duration_sec": round(dur, 1),
            "total_vars": total_vars,
            "interval_ms": interval_ms,
            "plc_cycle_ms": plc_cycle_ms,
            "total_notifications": grand_notifs,
            "total_changes": grand_changes,
            "total_missed": grand_missed,
            "detect_pct": round(grand_pct, 1),
            "tiers": tiers_report,
        }

        progress(100)
        return per_var

    # ── live trace  ──────────────────────────────────────────────
    def trace_read(self, node_ids: list[str]) -> dict:
        """Read values for live tracing. Returns {node_id: value}."""
        out = {}
        for nid in node_ids:
            try:
                val = self.client.get_node(nid).get_value()
                out[nid] = val if not isinstance(val, (list, tuple)) else val[0]
            except Exception:
                out[nid] = None
        return out
