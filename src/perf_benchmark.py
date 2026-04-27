import time
import csv
import os
import random
import statistics
from datetime import datetime
from opcua import Client, ua
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QTableWidget,
    QTableWidgetItem, QSpinBox, QDoubleSpinBox, QFrame, QComboBox, QTextEdit, QFileDialog,
    QMessageBox, QHeaderView, QProgressBar, QCheckBox, QGroupBox, QSplitter,
    QToolButton, QSizePolicy
)
from PyQt5.QtCore import QTimer, Qt, QThread, pyqtSignal


class CollapsibleSection(QWidget):
    """A collapsible section widget with a toggle button and content area."""

    def __init__(self, title="", parent=None):
        super().__init__(parent)
        self._is_collapsed = False

        self.toggle_btn = QToolButton()
        self.toggle_btn.setStyleSheet("""
            QToolButton {
                border: none; color: #e0e0e0; font-weight: bold;
                font-size: 11pt; padding: 4px;
            }
            QToolButton:hover { color: #ffffff; }
        """)
        self.toggle_btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.toggle_btn.setArrowType(Qt.DownArrow)
        self.toggle_btn.setText(title)
        self.toggle_btn.setCheckable(True)
        self.toggle_btn.setChecked(False)
        self.toggle_btn.clicked.connect(self._toggle)

        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(6)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        main_layout.addWidget(self.toggle_btn, 0, Qt.AlignLeft)
        main_layout.addWidget(self.content)

    def _toggle(self, checked):
        self._is_collapsed = checked
        self.content.setVisible(not checked)
        self.toggle_btn.setArrowType(Qt.RightArrow if checked else Qt.DownArrow)

    def addWidget(self, widget):
        self.content_layout.addWidget(widget)

    def addLayout(self, layout):
        self.content_layout.addLayout(layout)


class BenchmarkWorker(QThread):
    """Worker thread to run benchmarks without blocking the UI."""
    progress = pyqtSignal(int)
    result = pyqtSignal(dict)
    log = pyqtSignal(str)
    finished_signal = pyqtSignal()

    def __init__(self, client, test_config):
        super().__init__()
        self.client = client
        self.test_config = test_config
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        results = {}
        try:
            if self.test_config.get("single_read"):
                results["single_read"] = self._test_single_read()
            if self._stop:
                return
            if self.test_config.get("batch_read"):
                results["batch_read"] = self._test_batch_read()
            if self._stop:
                return
            if self.test_config.get("throughput"):
                results["throughput"] = self._test_throughput()
            if self._stop:
                return
            if self.test_config.get("write_latency"):
                results["write_latency"] = self._test_write_latency()
            if self._stop:
                return
            if self.test_config.get("array_read"):
                results["array_read"] = self._test_array_read()
            if self._stop:
                return
            if self.test_config.get("plc_cpu"):
                results["plc_cpu"] = self._test_plc_cpu()
            if self._stop:
                return
            if self.test_config.get("round_trip"):
                results["round_trip"] = self._test_round_trip()
            if self._stop:
                return
            if self.test_config.get("change_detect"):
                results["change_detect"] = self._test_change_detection()
            if self._stop:
                return
            if self.test_config.get("array_scan"):
                results["array_scan"] = self._test_array_element_scan()
            if self._stop:
                return
            if self.test_config.get("cycle_probe"):
                results["cycle_probe"] = self._test_cycle_latency_probe()
        except Exception as e:
            self.log.emit(f"ERROR: Benchmark failed: {str(e)}")
        self.result.emit(results)
        self.finished_signal.emit()

    def _test_single_read(self):
        """Measure round-trip time for single variable reads."""
        node_ids = self.test_config["node_ids"]
        iterations = self.test_config.get("iterations", 100)
        var_names = self.test_config["var_names"]
        results = {}

        self.log.emit(f"\n{'='*60}")
        self.log.emit("SINGLE READ LATENCY TEST")
        self.log.emit(f"{'='*60}")
        self.log.emit(f"Iterations per variable: {iterations}")

        for idx, (name, node_id) in enumerate(zip(var_names, node_ids)):
            if self._stop:
                return results
            latencies = []
            errors = 0
            node = self.client.get_node(node_id)

            for i in range(iterations):
                if self._stop:
                    return results
                try:
                    start = time.perf_counter()
                    _ = node.get_value()
                    elapsed = (time.perf_counter() - start) * 1000  # ms
                    latencies.append(elapsed)
                except Exception:
                    errors += 1

                progress = int(((idx * iterations + i + 1) / (len(node_ids) * iterations)) * 33)
                self.progress.emit(progress)

            if latencies:
                stats = {
                    "min_ms": round(min(latencies), 3),
                    "max_ms": round(max(latencies), 3),
                    "avg_ms": round(statistics.mean(latencies), 3),
                    "median_ms": round(statistics.median(latencies), 3),
                    "stddev_ms": round(statistics.stdev(latencies), 3) if len(latencies) > 1 else 0,
                    "p95_ms": round(sorted(latencies)[int(len(latencies) * 0.95)], 3),
                    "p99_ms": round(sorted(latencies)[int(len(latencies) * 0.99)], 3),
                    "errors": errors,
                    "samples": len(latencies),
                    "raw": latencies,
                }
                results[name] = stats
                self.log.emit(f"\n  {name}:")
                self.log.emit(f"    Min: {stats['min_ms']} ms | Max: {stats['max_ms']} ms | "
                              f"Avg: {stats['avg_ms']} ms | Median: {stats['median_ms']} ms")
                self.log.emit(f"    StdDev: {stats['stddev_ms']} ms | P95: {stats['p95_ms']} ms | "
                              f"P99: {stats['p99_ms']} ms")
                self.log.emit(f"    Errors: {errors}/{iterations}")

        return results

    def _test_batch_read(self):
        """Measure time to read all variables in a single batch."""
        node_ids = self.test_config["node_ids"]
        iterations = self.test_config.get("iterations", 100)

        self.log.emit(f"\n{'='*60}")
        self.log.emit("BATCH READ LATENCY TEST")
        self.log.emit(f"{'='*60}")
        self.log.emit(f"Variables in batch: {len(node_ids)} | Iterations: {iterations}")

        nodes = [self.client.get_node(nid) for nid in node_ids]
        latencies = []
        errors = 0

        for i in range(iterations):
            if self._stop:
                break
            try:
                start = time.perf_counter()
                # Read all nodes in batch
                values = self.client.get_values(nodes)
                elapsed = (time.perf_counter() - start) * 1000
                latencies.append(elapsed)
            except Exception:
                # Fallback: read one by one if batch not supported
                try:
                    start = time.perf_counter()
                    for node in nodes:
                        node.get_value()
                    elapsed = (time.perf_counter() - start) * 1000
                    latencies.append(elapsed)
                except Exception:
                    errors += 1

            progress = 33 + int(((i + 1) / iterations) * 22)
            self.progress.emit(progress)

        stats = {}
        if latencies:
            stats = {
                "num_variables": len(node_ids),
                "min_ms": round(min(latencies), 3),
                "max_ms": round(max(latencies), 3),
                "avg_ms": round(statistics.mean(latencies), 3),
                "median_ms": round(statistics.median(latencies), 3),
                "stddev_ms": round(statistics.stdev(latencies), 3) if len(latencies) > 1 else 0,
                "p95_ms": round(sorted(latencies)[int(len(latencies) * 0.95)], 3),
                "avg_per_var_ms": round(statistics.mean(latencies) / len(node_ids), 3),
                "errors": errors,
                "samples": len(latencies),
                "raw": latencies,
            }
            self.log.emit(f"\n  Batch ({len(node_ids)} vars):")
            self.log.emit(f"    Min: {stats['min_ms']} ms | Max: {stats['max_ms']} ms | "
                          f"Avg: {stats['avg_ms']} ms")
            self.log.emit(f"    Avg per variable: {stats['avg_per_var_ms']} ms")
            self.log.emit(f"    P95: {stats['p95_ms']} ms | Errors: {errors}/{iterations}")

        return stats

    def _test_throughput(self):
        """Test maximum read throughput - how many reads/sec."""
        node_ids = self.test_config["node_ids"]
        duration_sec = self.test_config.get("throughput_duration", 5)

        self.log.emit(f"\n{'='*60}")
        self.log.emit("THROUGHPUT TEST")
        self.log.emit(f"{'='*60}")
        self.log.emit(f"Duration: {duration_sec}s | Variables: {len(node_ids)}")

        nodes = [self.client.get_node(nid) for nid in node_ids]
        read_count = 0
        errors = 0
        start_time = time.perf_counter()

        while (time.perf_counter() - start_time) < duration_sec:
            if self._stop:
                break
            for node in nodes:
                try:
                    _ = node.get_value()
                    read_count += 1
                except Exception:
                    errors += 1

            elapsed = time.perf_counter() - start_time
            progress = 55 + int((elapsed / duration_sec) * 22)
            self.progress.emit(min(progress, 77))

        total_time = time.perf_counter() - start_time
        reads_per_sec = read_count / total_time if total_time > 0 else 0

        stats = {
            "total_reads": read_count,
            "duration_sec": round(total_time, 2),
            "reads_per_sec": round(reads_per_sec, 1),
            "vars_per_sec": round(reads_per_sec, 1),
            "errors": errors,
        }

        self.log.emit(f"\n  Total reads: {read_count} in {stats['duration_sec']}s")
        self.log.emit(f"  Throughput: {stats['reads_per_sec']} reads/sec")
        self.log.emit(f"  Errors: {errors}")

        return stats

    def _test_write_latency(self):
        """Measure write round-trip time (only for writable variables)."""
        node_ids = self.test_config["node_ids"]
        var_names = self.test_config["var_names"]
        iterations = self.test_config.get("iterations", 50)

        self.log.emit(f"\n{'='*60}")
        self.log.emit("WRITE LATENCY TEST")
        self.log.emit(f"{'='*60}")

        results = {}
        for idx, (name, node_id) in enumerate(zip(var_names, node_ids)):
            if self._stop:
                return results
            node = self.client.get_node(node_id)

            # Check if writable
            try:
                access = node.get_attribute(ua.AttributeIds.AccessLevel).Value.Value
                if not (access & ua.AccessLevel.CurrentWrite):
                    self.log.emit(f"  {name}: SKIPPED (read-only)")
                    continue
            except Exception:
                self.log.emit(f"  {name}: SKIPPED (cannot check access level)")
                continue

            latencies = []
            errors = 0
            try:
                original_value = node.get_value()
            except Exception:
                continue

            for i in range(iterations):
                if self._stop:
                    return results
                try:
                    start = time.perf_counter()
                    node.set_value(ua.DataValue(ua.Variant(original_value)))
                    elapsed = (time.perf_counter() - start) * 1000
                    latencies.append(elapsed)
                except Exception:
                    errors += 1

                progress = 77 + int(((idx * iterations + i + 1) / (len(node_ids) * iterations)) * 10)
                self.progress.emit(min(progress, 87))

            if latencies:
                stats = {
                    "min_ms": round(min(latencies), 3),
                    "max_ms": round(max(latencies), 3),
                    "avg_ms": round(statistics.mean(latencies), 3),
                    "stddev_ms": round(statistics.stdev(latencies), 3) if len(latencies) > 1 else 0,
                    "errors": errors,
                    "samples": len(latencies),
                }
                results[name] = stats
                self.log.emit(f"\n  {name}:")
                self.log.emit(f"    Min: {stats['min_ms']} ms | Max: {stats['max_ms']} ms | "
                              f"Avg: {stats['avg_ms']} ms")

        return results

    def _test_array_read(self):
        """Measure latency for reading large array variables."""
        node_ids = self.test_config["node_ids"]
        var_names = self.test_config["var_names"]
        iterations = self.test_config.get("iterations", 100)

        self.log.emit(f"\n{'='*60}")
        self.log.emit("ARRAY READ LATENCY TEST")
        self.log.emit(f"{'='*60}")

        results = {}
        for idx, (name, node_id) in enumerate(zip(var_names, node_ids)):
            if self._stop:
                return results
            node = self.client.get_node(node_id)

            # Check if it's an array
            try:
                value = node.get_value()
                if not isinstance(value, (list, tuple)):
                    self.log.emit(f"  {name}: SKIPPED (not an array, type={type(value).__name__})")
                    continue
                array_len = len(value)
                elem_type = type(value[0]).__name__ if value else "unknown"
                self.log.emit(f"\n  {name}: Array[{array_len}] of {elem_type}")
            except Exception as e:
                self.log.emit(f"  {name}: SKIPPED (error reading: {e})")
                continue

            latencies = []
            sizes = []
            errors = 0

            for i in range(iterations):
                if self._stop:
                    return results
                try:
                    start = time.perf_counter()
                    val = node.get_value()
                    elapsed = (time.perf_counter() - start) * 1000
                    latencies.append(elapsed)
                    sizes.append(len(val) if isinstance(val, (list, tuple)) else 1)
                except Exception:
                    errors += 1

                progress = 77 + int(((idx * iterations + i + 1) / (len(node_ids) * iterations)) * 10)
                self.progress.emit(min(progress, 87))

            if latencies:
                avg_size = statistics.mean(sizes)
                stats = {
                    "array_length": array_len,
                    "element_type": elem_type,
                    "min_ms": round(min(latencies), 3),
                    "max_ms": round(max(latencies), 3),
                    "avg_ms": round(statistics.mean(latencies), 3),
                    "median_ms": round(statistics.median(latencies), 3),
                    "stddev_ms": round(statistics.stdev(latencies), 3) if len(latencies) > 1 else 0,
                    "p95_ms": round(sorted(latencies)[int(len(latencies) * 0.95)], 3),
                    "p99_ms": round(sorted(latencies)[int(len(latencies) * 0.99)], 3),
                    "throughput_elements_per_sec": round(avg_size / (statistics.mean(latencies) / 1000), 1),
                    "bytes_estimate": array_len * 4,  # 4 bytes per UDINT
                    "errors": errors,
                    "samples": len(latencies),
                    "raw": latencies,
                }
                results[name] = stats
                self.log.emit(f"    Min: {stats['min_ms']} ms | Max: {stats['max_ms']} ms | "
                              f"Avg: {stats['avg_ms']} ms | Median: {stats['median_ms']} ms")
                self.log.emit(f"    P95: {stats['p95_ms']} ms | P99: {stats['p99_ms']} ms | "
                              f"StdDev: {stats['stddev_ms']} ms")
                self.log.emit(f"    Array size: {array_len} elements ({stats['bytes_estimate']} bytes est.)")
                self.log.emit(f"    Throughput: ~{stats['throughput_elements_per_sec']} elements/sec")
                self.log.emit(f"    Errors: {errors}/{iterations}")

        return results

    def _test_round_trip(self):
        """Write a unique value to PLC, read it back, measure total round-trip time."""
        node_ids = self.test_config["node_ids"]
        var_names = self.test_config["var_names"]
        iterations = self.test_config.get("iterations", 100)

        self.log.emit(f"\n{'='*60}")
        self.log.emit("WRITE-READ ROUND-TRIP LATENCY TEST")
        self.log.emit(f"{'='*60}")
        self.log.emit(f"Iterations: {iterations}")
        self.log.emit("  (Write unique value → Read back → Confirm match → Measure time)")

        results = {}
        for idx, (name, node_id) in enumerate(zip(var_names, node_ids)):
            if self._stop:
                return results
            node = self.client.get_node(node_id)

            # Check if writable
            try:
                value = node.get_value()
                access = node.get_attribute(ua.AttributeIds.AccessLevel).Value.Value
                if not (access & ua.AccessLevel.CurrentWrite):
                    self.log.emit(f"  {name}: SKIPPED (read-only)")
                    continue
            except Exception as e:
                self.log.emit(f"  {name}: SKIPPED ({e})")
                continue

            original_value = value
            is_numeric = isinstance(value, (int, float))
            is_bool = isinstance(value, bool)

            if not is_numeric and not is_bool:
                self.log.emit(f"  {name}: SKIPPED (type={type(value).__name__}, need numeric/bool)")
                continue

            latencies = []
            write_times = []
            read_times = []
            errors = 0
            mismatches = 0

            self.log.emit(f"\n  {name} (type={type(value).__name__}, original={value}):")

            for i in range(iterations):
                if self._stop:
                    return results
                try:
                    # Generate a unique test value
                    if is_bool:
                        test_val = (i % 2 == 0)
                        variant_type = ua.VariantType.Boolean
                    elif isinstance(value, float):
                        test_val = float(i + 1) + 0.5
                        variant_type = ua.VariantType.Float
                    else:
                        test_val = i + 1
                        # Detect B&R integer types
                        variant_type = ua.VariantType.Int32
                        try:
                            dt = node.get_data_type()
                            dt_name = self.client.get_node(dt).get_display_name().Text.lower()
                            if 'uint' in dt_name or 'udint' in dt_name or 'usint' in dt_name:
                                variant_type = ua.VariantType.UInt32
                            elif 'int16' in dt_name or 'int' == dt_name:
                                variant_type = ua.VariantType.Int16
                            elif 'uint16' in dt_name:
                                variant_type = ua.VariantType.UInt16
                        except Exception:
                            pass

                    # WRITE
                    t0 = time.perf_counter()
                    node.set_value(ua.DataValue(ua.Variant(test_val, variant_type)))
                    t1 = time.perf_counter()

                    # READ BACK
                    read_val = node.get_value()
                    t2 = time.perf_counter()

                    write_ms = (t1 - t0) * 1000
                    read_ms = (t2 - t1) * 1000
                    total_ms = (t2 - t0) * 1000

                    write_times.append(write_ms)
                    read_times.append(read_ms)
                    latencies.append(total_ms)

                    # Check if value matches
                    if is_bool:
                        match = (read_val == test_val)
                    else:
                        match = (abs(float(read_val) - float(test_val)) < 0.01)
                    if not match:
                        mismatches += 1

                except Exception:
                    errors += 1

                progress_pct = self.test_config.get("_rt_progress_base", 0) + \
                    int(((idx * iterations + i + 1) / (max(len(node_ids), 1) * iterations)) *
                        self.test_config.get("_rt_progress_span", 10))
                self.progress.emit(min(progress_pct, 99))

            # Restore original value
            try:
                if is_bool:
                    node.set_value(ua.DataValue(ua.Variant(original_value, ua.VariantType.Boolean)))
                elif isinstance(original_value, float):
                    node.set_value(ua.DataValue(ua.Variant(original_value, ua.VariantType.Float)))
                else:
                    node.set_value(ua.DataValue(ua.Variant(original_value, variant_type)))
            except Exception:
                pass

            if latencies:
                stats = {
                    "min_ms": round(min(latencies), 3),
                    "max_ms": round(max(latencies), 3),
                    "avg_ms": round(statistics.mean(latencies), 3),
                    "median_ms": round(statistics.median(latencies), 3),
                    "stddev_ms": round(statistics.stdev(latencies), 3) if len(latencies) > 1 else 0,
                    "p95_ms": round(sorted(latencies)[int(len(latencies) * 0.95)], 3),
                    "p99_ms": round(sorted(latencies)[int(len(latencies) * 0.99)], 3),
                    "avg_write_ms": round(statistics.mean(write_times), 3),
                    "avg_read_ms": round(statistics.mean(read_times), 3),
                    "mismatches": mismatches,
                    "errors": errors,
                    "samples": len(latencies),
                }
                results[name] = stats
                self.log.emit(f"    Round-trip: Min={stats['min_ms']} | Avg={stats['avg_ms']} | "
                              f"Max={stats['max_ms']} | P95={stats['p95_ms']} ms")
                self.log.emit(f"    Write avg: {stats['avg_write_ms']} ms | "
                              f"Read avg: {stats['avg_read_ms']} ms")
                self.log.emit(f"    Mismatches: {mismatches} | Errors: {errors}/{iterations}")

        return results

    def _test_change_detection(self):
        """Measure real read speed and answer: 'If a value changes for Xms, will I catch it?'
        
        Tests 3 scenarios:
        1. Single variable polling speed (best case)
        2. Round-robin scan of ALL selected variables (realistic case)
        3. Calculates minimum detectable event duration for various monitoring configs
        """
        node_ids = self.test_config["node_ids"]
        var_names = self.test_config["var_names"]
        duration_sec = self.test_config.get("change_detect_duration", 10)
        total_vars = len(node_ids)

        self.log.emit(f"\n{'='*60}")
        self.log.emit("READ SPEED & DETECTION CAPABILITY")
        self.log.emit(f"{'='*60}")
        self.log.emit(f"  Variables: {total_vars} | Test duration: {duration_sec}s each phase")
        self.log.emit(f"  Question: If something changes for 2ms or 5ms, will I catch it?\n")

        results = {}
        nodes = [self.client.get_node(nid) for nid in node_ids]

        # ========== PHASE 1: Single variable max speed ==========
        self.log.emit(f"  --- PHASE 1: Single Variable Max Poll Speed ---")
        self.log.emit(f"  Reading first variable as fast as possible for {duration_sec}s...\n")

        single_read_times = []
        single_node = nodes[0]
        start = time.perf_counter()
        count = 0

        while (time.perf_counter() - start) < duration_sec:
            if self._stop:
                return results
            t0 = time.perf_counter()
            try:
                _ = single_node.get_value()
            except Exception:
                pass
            t1 = time.perf_counter()
            single_read_times.append((t1 - t0) * 1000)
            count += 1
            if count % 500 == 0:
                elapsed = time.perf_counter() - start
                self.progress.emit(int((elapsed / duration_sec) * 30))

        single_total = time.perf_counter() - start
        single_rate = count / single_total
        single_avg_ms = statistics.mean(single_read_times)
        single_med_ms = statistics.median(single_read_times)
        single_min_ms = min(single_read_times)
        single_max_ms = max(single_read_times)
        sorted_single = sorted(single_read_times)
        single_p95 = sorted_single[int(len(sorted_single) * 0.95)]
        single_p99 = sorted_single[int(len(sorted_single) * 0.99)]

        self.log.emit(f"  Single variable read speed:")
        self.log.emit(f"    Reads:    {count} in {single_total:.1f}s")
        self.log.emit(f"    Rate:     {single_rate:.0f} reads/sec")
        self.log.emit(f"    Per read: Min={single_min_ms:.2f} Avg={single_avg_ms:.2f} "
                      f"Med={single_med_ms:.2f} P95={single_p95:.2f} Max={single_max_ms:.2f} ms")

        # ========== PHASE 2: Round-robin scan of ALL variables ==========
        self.log.emit(f"\n  --- PHASE 2: Round-Robin Scan ({total_vars} variables) ---")
        self.log.emit(f"  Reading all {total_vars} vars in sequence, measuring full scan time...\n")

        scan_times = []  # time for one complete scan of all vars
        per_var_times = [[] for _ in range(total_vars)]
        start = time.perf_counter()
        scans = 0

        while (time.perf_counter() - start) < duration_sec:
            if self._stop:
                return results
            scan_start = time.perf_counter()
            for vi, node in enumerate(nodes):
                t0 = time.perf_counter()
                try:
                    _ = node.get_value()
                except Exception:
                    pass
                t1 = time.perf_counter()
                per_var_times[vi].append((t1 - t0) * 1000)
            scan_end = time.perf_counter()
            scan_times.append((scan_end - scan_start) * 1000)
            scans += 1
            if scans % 5 == 0:
                elapsed = time.perf_counter() - start
                self.progress.emit(30 + int((elapsed / duration_sec) * 40))

        scan_total = time.perf_counter() - start
        scan_avg_ms = statistics.mean(scan_times)
        scan_med_ms = statistics.median(scan_times)
        scan_min_ms = min(scan_times)
        scan_max_ms = max(scan_times)
        sorted_scans = sorted(scan_times)
        scan_p95 = sorted_scans[int(len(sorted_scans) * 0.95)]
        scan_rate = scans / scan_total
        total_reads_phase2 = scans * total_vars

        self.log.emit(f"  Full scan of {total_vars} variables:")
        self.log.emit(f"    Scans:      {scans} in {scan_total:.1f}s")
        self.log.emit(f"    Scan rate:  {scan_rate:.1f} scans/sec")
        self.log.emit(f"    Scan time:  Min={scan_min_ms:.1f} Avg={scan_avg_ms:.1f} "
                      f"Med={scan_med_ms:.1f} P95={scan_p95:.1f} Max={scan_max_ms:.1f} ms")
        self.log.emit(f"    Per-var avg: {scan_avg_ms / total_vars:.2f} ms/var in scan")
        self.log.emit(f"    Total reads: {total_reads_phase2}")

        # ========== PHASE 3: Detection capability report ==========
        self.log.emit(f"\n{'#'*60}")
        self.log.emit(f"  DETECTION CAPABILITY REPORT")
        self.log.emit(f"{'#'*60}")

        self.log.emit(f"\n  --- Your OPC UA Connection Speed ---")
        self.log.emit(f"    Single read:        {single_med_ms:.2f} ms (median)")
        self.log.emit(f"    Full scan ({total_vars} vars): {scan_med_ms:.1f} ms (median)")

        # "Will I catch it?" table
        self.log.emit(f"\n  --- Will I Catch a Short Event? ---")
        self.log.emit(f"  (Event = value changes for X ms then goes back)")
        self.log.emit(f"")
        self.log.emit(f"  {'Event Duration':>16s}  {'1 var':>10s}  {f'{total_vars} vars':>10s}  {'Verdict':>12s}")
        self.log.emit(f"  {'-'*16}  {'-'*10}  {'-'*10}  {'-'*12}")

        test_durations = [1, 2, 3, 5, 10, 20, 50, 100]
        for event_ms in test_durations:
            # For single var: probability of catching = event_duration / poll_interval
            # Poll interval = median read time (we read continuously)
            single_catch = min(event_ms / single_med_ms, 1.0) * 100
            # For N vars round-robin: we visit each var every scan_med_ms
            multi_catch = min(event_ms / scan_med_ms, 1.0) * 100

            if multi_catch >= 95:
                verdict = "YES"
            elif multi_catch >= 50:
                verdict = "LIKELY"
            elif single_catch >= 95:
                verdict = "1var only"
            elif single_catch >= 50:
                verdict = "MAYBE"
            else:
                verdict = "NO"

            self.log.emit(
                f"  {event_ms:>14d}ms  {single_catch:>9.0f}%  {multi_catch:>9.0f}%  {verdict:>12s}")

        # Minimum detectable event
        min_detect_single = single_p95  # need at least P95 read time to reliably detect
        min_detect_multi = scan_p95     # need at least P95 scan time

        self.log.emit(f"\n  --- Minimum Reliably Detectable Event ---")
        self.log.emit(f"    Monitoring 1 variable:      ≥ {min_detect_single:.1f} ms")
        self.log.emit(f"    Monitoring {total_vars:>3d} variables:   ≥ {min_detect_multi:.1f} ms")
        self.log.emit(f"    (P95 guarantee — 95% chance of catching)")

        # Recommendations based on numbers
        self.log.emit(f"\n  --- Recommendations ---")
        if scan_med_ms < 5:
            self.log.emit(f"    At {scan_med_ms:.0f}ms scan time, you can monitor {total_vars} vars")
            self.log.emit(f"    and catch any event lasting ≥5ms.")
        if scan_med_ms > 5 and scan_med_ms < 50:
            max_vars_5ms = max(int(5 / (single_med_ms)), 1)
            max_vars_10ms = max(int(10 / (single_med_ms)), 1)
            self.log.emit(f"    To catch 5ms events:  monitor max ~{max_vars_5ms} vars")
            self.log.emit(f"    To catch 10ms events: monitor max ~{max_vars_10ms} vars")
            self.log.emit(f"    To catch 2ms events:  monitor max ~{max(int(2 / single_med_ms), 1)} vars")
        if scan_med_ms >= 50:
            self.log.emit(f"    ⚠ {total_vars} vars is too many for fast detection.")
            max_vars_10ms = max(int(10 / (single_med_ms)), 1)
            self.log.emit(f"    Reduce to ~{max_vars_10ms} vars for 10ms detection.")

        self.log.emit(f"\n  --- Practical Limits ---")
        self.log.emit(f"    Max vars for  2ms detection: ~{max(int(2 / single_med_ms), 1)}")
        self.log.emit(f"    Max vars for  5ms detection: ~{max(int(5 / single_med_ms), 1)}")
        self.log.emit(f"    Max vars for 10ms detection: ~{max(int(10 / single_med_ms), 1)}")
        self.log.emit(f"    Max vars for 50ms detection: ~{max(int(50 / single_med_ms), 1)}")

        self.log.emit(f"\n  {'='*56}")
        self.log.emit(f"  BOTTOM LINE")
        self.log.emit(f"  {'='*56}")
        self.log.emit(f"    Your read speed: {single_med_ms:.2f} ms per variable")
        self.log.emit(f"    => 1 var: can catch ≥{single_p95:.1f}ms events (95% reliable)")
        self.log.emit(f"    => {total_vars} vars: can catch ≥{scan_p95:.1f}ms events (95% reliable)")
        self.log.emit(f"  {'='*56}")

        self.progress.emit(95)

        # Build results
        for idx, name in enumerate(var_names):
            short = name.split("/")[-1] if "/" in name else name
            avg = statistics.mean(per_var_times[idx]) if per_var_times[idx] else 0
            results[short] = {
                "duration_sec": round(scan_total, 2),
                "total_polls": scans,
                "polls_per_sec": round(scan_rate, 1),
                "total_changes": scans,
                "changes_per_sec": round(scan_rate, 1),
                "avg_read_ms": round(avg, 3),
                "is_array": False,
                "array_length": 1,
                "min_gap_ms": round(scan_min_ms, 3),
                "max_gap_ms": round(scan_max_ms, 3),
                "avg_gap_ms": round(scan_avg_ms, 3),
                "median_gap_ms": round(scan_med_ms, 3),
            }

        # Add summary entry
        results["_detection_summary_"] = {
            "single_read_ms": round(single_med_ms, 3),
            "single_read_p95_ms": round(single_p95, 3),
            "single_rate_per_sec": round(single_rate, 0),
            "scan_vars": total_vars,
            "scan_ms": round(scan_med_ms, 2),
            "scan_p95_ms": round(scan_p95, 2),
            "scan_rate_per_sec": round(scan_rate, 1),
            "min_detect_1var_ms": round(min_detect_single, 2),
            "min_detect_all_ms": round(min_detect_multi, 2),
        }

        return results

    def _test_array_element_scan(self):
        """Read each element of an array individually, measure per-element latency.
        
        This tests: for a 1000-element array, how long to read element[0], element[1], ... element[999]
        by reading the whole array and comparing elements, or reading individual indexed nodes.
        """
        node_ids = self.test_config["node_ids"]
        var_names = self.test_config["var_names"]
        iterations = self.test_config.get("array_scan_iterations", 10)

        self.log.emit(f"\n{'='*60}")
        self.log.emit("ARRAY ELEMENT SCAN TEST")
        self.log.emit(f"{'='*60}")
        self.log.emit(f"Iterations: {iterations}")
        self.log.emit("  (Read full array repeatedly, track per-element changes & timing)\n")

        results = {}
        for idx, (name, node_id) in enumerate(zip(var_names, node_ids)):
            if self._stop:
                return results
            node = self.client.get_node(node_id)

            try:
                value = node.get_value()
                if not isinstance(value, (list, tuple)):
                    self.log.emit(f"  {name}: SKIPPED (not an array)")
                    continue
                array_len = len(value)
                elem_type = type(value[0]).__name__ if value else "unknown"
                self.log.emit(f"  {name}: Array[{array_len}] of {elem_type}")
            except Exception as e:
                self.log.emit(f"  {name}: SKIPPED ({e})")
                continue

            read_latencies = []
            change_counts = [0] * array_len  # per-element change counter
            prev_values = list(value)

            for i in range(iterations):
                if self._stop:
                    return results
                try:
                    start = time.perf_counter()
                    current = node.get_value()
                    elapsed = (time.perf_counter() - start) * 1000
                    read_latencies.append(elapsed)

                    # Count which elements changed
                    for j in range(min(len(current), array_len)):
                        if current[j] != prev_values[j]:
                            change_counts[j] += 1
                    prev_values = list(current)

                except Exception:
                    pass

                progress_pct = self.test_config.get("_as_progress_base", 0) + \
                    int(((idx * iterations + i + 1) / (max(len(node_ids), 1) * iterations)) *
                        self.test_config.get("_as_progress_span", 10))
                self.progress.emit(min(progress_pct, 99))

            total_changes = sum(change_counts)
            elements_changed = sum(1 for c in change_counts if c > 0)

            stats = {
                "array_length": array_len,
                "element_type": elem_type,
                "iterations": len(read_latencies),
            }

            if read_latencies:
                stats.update({
                    "min_ms": round(min(read_latencies), 3),
                    "max_ms": round(max(read_latencies), 3),
                    "avg_ms": round(statistics.mean(read_latencies), 3),
                    "median_ms": round(statistics.median(read_latencies), 3),
                    "stddev_ms": round(statistics.stdev(read_latencies), 3) if len(read_latencies) > 1 else 0,
                    "p95_ms": round(sorted(read_latencies)[int(len(read_latencies) * 0.95)], 3),
                    "us_per_element": round((statistics.mean(read_latencies) / array_len) * 1000, 3),
                    "total_element_changes": total_changes,
                    "elements_that_changed": elements_changed,
                    "pct_elements_changed": round(elements_changed / array_len * 100, 1),
                    "avg_changes_per_element": round(total_changes / max(elements_changed, 1), 2),
                })

                self.log.emit(f"    Full array read: Min={stats['min_ms']} | Avg={stats['avg_ms']} | "
                              f"Max={stats['max_ms']} | P95={stats['p95_ms']} ms")
                self.log.emit(f"    Per element: ~{stats['us_per_element']} us/element")
                self.log.emit(f"    Elements changed: {elements_changed}/{array_len} "
                              f"({stats['pct_elements_changed']}%)")
                self.log.emit(f"    Total element changes: {total_changes} across {len(read_latencies)} reads")

                # Show top-10 most-changing elements
                if elements_changed > 0:
                    indexed = [(j, c) for j, c in enumerate(change_counts) if c > 0]
                    indexed.sort(key=lambda x: x[1], reverse=True)
                    top = indexed[:10]
                    self.log.emit(f"    Top changing elements: " +
                                  ", ".join(f"[{j}]={c}x" for j, c in top))

                stats["change_counts"] = change_counts

            results[name] = stats

        return results

    def _test_cycle_latency_probe(self):
        """Measure real PLC-to-Python latency using cycling counters.
        
        Works with both:
        - Individual scalar variables (opctest1..opctest200): reads each var consecutively
        - Array variables (VitalyOpcArray[1000]): picks random elements
        
        The PLC increments each value by 1 each cycle (e.g. 1.6ms).
        If we read value=100 then value=103, delta=3 → 3×1.6ms = 4.8ms real latency.
        """
        node_ids = self.test_config["node_ids"]
        var_names = self.test_config["var_names"]
        num_reads = self.test_config.get("cycle_probe_reads", 200)
        plc_cycle_ms = self.test_config.get("plc_cycle_ms", 1.6)

        self.log.emit(f"\n{'='*60}")
        self.log.emit("CYCLE LATENCY PROBE")
        self.log.emit(f"{'='*60}")
        self.log.emit(f"  PLC cycle time: {plc_cycle_ms} ms")
        self.log.emit(f"  Variables: {len(node_ids)} | Reads per variable: {num_reads}")
        self.log.emit(f"  Method: Read value → Read again ASAP → delta × cycle_time = latency")
        self.log.emit(f"")

        # Detect mode: if the first variable is an array, use array mode
        # Otherwise treat all selected variables as individual scalars
        first_node = self.client.get_node(node_ids[0])
        try:
            first_val = first_node.get_value()
        except Exception as e:
            self.log.emit(f"  Cannot read first variable: {e}")
            return {}

        is_array_mode = isinstance(first_val, (list, tuple))

        if is_array_mode:
            return self._cycle_probe_array(node_ids[0], var_names[0], first_val,
                                           num_reads, plc_cycle_ms)
        else:
            return self._cycle_probe_scalars(node_ids, var_names, num_reads, plc_cycle_ms)

    def _cycle_probe_scalars(self, node_ids, var_names, num_reads, plc_cycle_ms):
        """Cycle probe for individual scalar variables (opctest1..opctest200)."""
        total_vars = len(node_ids)
        self.log.emit(f"  MODE: Scalar variables ({total_vars} vars)")
        self.log.emit(f"  Reading each variable {num_reads} times as fast as possible\n")

        all_latencies_ms = []
        per_var = {}  # {name: stats}

        for vi, (name, node_id) in enumerate(zip(var_names, node_ids)):
            if self._stop:
                break

            node = self.client.get_node(node_id)
            short_name = name.split("/")[-1] if "/" in name else name

            values = []
            timestamps = []
            deltas = []
            derived_latencies = []

            # First read - baseline
            try:
                prev_val = node.get_value()
                prev_time = time.perf_counter()
                values.append(prev_val)
                timestamps.append(prev_time)
            except Exception as e:
                self.log.emit(f"  {short_name}: ERROR reading ({e})")
                continue

            # Tight loop reads
            for r in range(num_reads):
                if self._stop:
                    break
                try:
                    cur_val = node.get_value()
                    cur_time = time.perf_counter()

                    val_delta = cur_val - prev_val
                    values.append(cur_val)
                    timestamps.append(cur_time)

                    if val_delta != 0:
                        if val_delta < 0:
                            # UDINT wrap at 4294967295
                            val_delta = val_delta + 4294967296
                        derived_ms = val_delta * plc_cycle_ms
                        deltas.append(val_delta)
                        derived_latencies.append(derived_ms)
                        all_latencies_ms.append(derived_ms)

                    prev_val = cur_val
                    prev_time = cur_time
                except Exception:
                    pass

                # Progress
                pct = int(((vi * num_reads + r + 1) / (total_vars * num_reads)) * 100)
                self.progress.emit(min(pct, 99))

            # Per-variable results
            total_wall_ms = (timestamps[-1] - timestamps[0]) * 1000 if len(timestamps) > 1 else 0
            reads_with_change = len(deltas)
            reads_no_change = num_reads - reads_with_change

            if derived_latencies:
                avg_lat = statistics.mean(derived_latencies)
                med_lat = statistics.median(derived_latencies)
                min_lat = min(derived_latencies)
                max_lat = max(derived_latencies)
                avg_delta = statistics.mean(deltas)

                per_var[short_name] = {
                    "reads": num_reads,
                    "reads_with_change": reads_with_change,
                    "reads_same": reads_no_change,
                    "value_start": values[0],
                    "value_end": values[-1],
                    "wall_ms": round(total_wall_ms, 2),
                    "avg_val_delta": round(avg_delta, 2),
                    "min_latency_ms": round(min_lat, 2),
                    "avg_latency_ms": round(avg_lat, 2),
                    "median_latency_ms": round(med_lat, 2),
                    "max_latency_ms": round(max_lat, 2),
                }

                # Log every var (compact format)
                self.log.emit(
                    f"  {short_name:>12s}  val:{values[0]:>10d}→{values[-1]:<10d}  "
                    f"changes:{reads_with_change:>4d}/{num_reads}  "
                    f"avgΔ:{avg_delta:.1f}  "
                    f"lat: {min_lat:.1f}/{avg_lat:.1f}/{med_lat:.1f}/{max_lat:.1f} ms "
                    f"(min/avg/med/max)")
            else:
                per_var[short_name] = {
                    "reads": num_reads,
                    "reads_with_change": 0,
                    "reads_same": num_reads,
                    "value_start": values[0] if values else 0,
                    "value_end": values[-1] if values else 0,
                    "wall_ms": round(total_wall_ms, 2),
                }
                self.log.emit(f"  {short_name:>12s}  NO CHANGES in {num_reads} reads "
                              f"({total_wall_ms:.0f}ms wall time)")

        # ===== GRAND SUMMARY =====
        self.log.emit(f"\n{'='*60}")
        self.log.emit(f"  SUMMARY: {total_vars} scalar variables, PLC cycle={plc_cycle_ms}ms")
        self.log.emit(f"{'='*60}")

        # Summary table
        self.log.emit(f"\n  {'Variable':>12s}  {'Changes':>8s}  {'Same':>6s}  "
                      f"{'AvgΔ':>6s}  {'Min':>7s}  {'Avg':>7s}  {'Med':>7s}  {'Max':>7s}  {'Wall':>8s}")
        self.log.emit(f"  {'-'*12}  {'-'*8}  {'-'*6}  "
                      f"{'-'*6}  {'-'*7}  {'-'*7}  {'-'*7}  {'-'*7}  {'-'*8}")

        for vname in per_var:
            p = per_var[vname]
            if p["reads_with_change"] > 0:
                self.log.emit(
                    f"  {vname:>12s}  {p['reads_with_change']:8d}  {p['reads_same']:6d}  "
                    f"{p['avg_val_delta']:6.1f}  {p['min_latency_ms']:6.1f}ms "
                    f"{p['avg_latency_ms']:6.1f}ms {p['median_latency_ms']:6.1f}ms "
                    f"{p['max_latency_ms']:6.1f}ms  {p['wall_ms']:7.0f}ms")
            else:
                self.log.emit(
                    f"  {vname:>12s}  {'NONE':>8s}  {p['reads_same']:6d}  "
                    f"{'N/A':>6s}  {'N/A':>7s}  {'N/A':>7s}  {'N/A':>7s}  "
                    f"{'N/A':>7s}  {p['wall_ms']:7.0f}ms")

        results = {"_summary_": {}}
        if all_latencies_ms:
            sorted_lat = sorted(all_latencies_ms)
            n = len(sorted_lat)
            p95_idx = min(int(n * 0.95), n - 1)
            p99_idx = min(int(n * 0.99), n - 1)
            p50_idx = min(int(n * 0.50), n - 1)
            p10_idx = min(int(n * 0.10), n - 1)
            p25_idx = min(int(n * 0.25), n - 1)
            p75_idx = min(int(n * 0.75), n - 1)
            overall_min = min(all_latencies_ms)
            overall_avg = statistics.mean(all_latencies_ms)
            overall_med = statistics.median(all_latencies_ms)
            overall_p95 = sorted_lat[p95_idx]
            overall_p99 = sorted_lat[p99_idx]
            overall_max = max(all_latencies_ms)
            overall_std = statistics.stdev(all_latencies_ms) if n > 1 else 0

            vars_with_changes = sum(1 for v in per_var.values() if v["reads_with_change"] > 0)
            vars_no_changes = total_vars - vars_with_changes
            total_reads = total_vars * num_reads
            total_wall_ms = sum(v.get("wall_ms", 0) for v in per_var.values())

            # Collect per-var medians for distribution analysis
            per_var_medians = [v["median_latency_ms"] for v in per_var.values() 
                               if v.get("reads_with_change", 0) > 0]

            # ===== NETWORK PERFORMANCE REPORT =====
            self.log.emit(f"\n{'#'*60}")
            self.log.emit(f"  NETWORK PERFORMANCE REPORT")
            self.log.emit(f"{'#'*60}")

            self.log.emit(f"\n  --- Test Configuration ---")
            self.log.emit(f"    Variables tested:      {total_vars}")
            self.log.emit(f"    Samples per variable:  {num_reads}")
            self.log.emit(f"    Total OPC UA reads:    {total_reads}")
            self.log.emit(f"    PLC cycle time:        {plc_cycle_ms} ms")
            self.log.emit(f"    Total test duration:   {total_wall_ms:.0f} ms ({total_wall_ms/1000:.1f} s)")

            self.log.emit(f"\n  --- Variable Status ---")
            self.log.emit(f"    Active (value changing):   {vars_with_changes}/{total_vars}")
            self.log.emit(f"    Inactive (no changes):     {vars_no_changes}/{total_vars}")
            self.log.emit(f"    Change events collected:   {n}")
            self.log.emit(f"    Avg reads per change:      {total_reads / max(n, 1):.1f}")

            self.log.emit(f"\n  --- Derived Latency Distribution ---")
            self.log.emit(f"    (latency = value_delta × {plc_cycle_ms}ms PLC cycle)")
            self.log.emit(f"")
            self.log.emit(f"    Minimum:     {overall_min:8.2f} ms")
            self.log.emit(f"    P10:         {sorted_lat[p10_idx]:8.2f} ms")
            self.log.emit(f"    P25:         {sorted_lat[p25_idx]:8.2f} ms")
            self.log.emit(f"    Median(P50): {overall_med:8.2f} ms")
            self.log.emit(f"    Average:     {overall_avg:8.2f} ms")
            self.log.emit(f"    P75:         {sorted_lat[p75_idx]:8.2f} ms")
            self.log.emit(f"    P95:         {overall_p95:8.2f} ms")
            self.log.emit(f"    P99:         {overall_p99:8.2f} ms")
            self.log.emit(f"    Maximum:     {overall_max:8.2f} ms")
            self.log.emit(f"    Std Dev:     {overall_std:8.2f} ms")

            # Histogram - bucket latencies
            bucket_size = plc_cycle_ms  # each bucket = 1 PLC cycle
            max_bucket = int(overall_max / bucket_size) + 1
            max_bucket = min(max_bucket, 30)  # cap at 30 buckets for display
            buckets = [0] * (max_bucket + 1)
            for lat in all_latencies_ms:
                bi = min(int(lat / bucket_size), max_bucket)
                buckets[bi] += 1

            self.log.emit(f"\n  --- Latency Histogram (bucket = {bucket_size}ms = 1 PLC cycle) ---")
            max_count = max(buckets) if buckets else 1
            bar_width = 40
            for bi, count in enumerate(buckets):
                if count == 0:
                    continue
                bar_len = int((count / max_count) * bar_width)
                pct = (count / n) * 100
                lo = bi * bucket_size
                hi = (bi + 1) * bucket_size
                bar = '█' * bar_len
                self.log.emit(f"    {lo:6.1f}-{hi:5.1f}ms │{bar:<{bar_width}s}│ {count:5d} ({pct:5.1f}%)")

            # Per-variable median distribution
            if per_var_medians:
                self.log.emit(f"\n  --- Per-Variable Median Latency ---")
                var_med_min = min(per_var_medians)
                var_med_max = max(per_var_medians)
                var_med_avg = statistics.mean(per_var_medians)
                self.log.emit(f"    Best variable:    {var_med_min:.2f} ms median")
                self.log.emit(f"    Worst variable:   {var_med_max:.2f} ms median")
                self.log.emit(f"    Average across:   {var_med_avg:.2f} ms median")
                if len(per_var_medians) > 1:
                    var_med_std = statistics.stdev(per_var_medians)
                    self.log.emit(f"    Spread (stddev):  {var_med_std:.2f} ms")

            # Throughput
            if total_wall_ms > 0:
                reads_per_sec = (total_reads / total_wall_ms) * 1000
                self.log.emit(f"\n  --- OPC UA Throughput ---")
                self.log.emit(f"    Read speed:       {reads_per_sec:.0f} reads/sec")
                self.log.emit(f"    Avg read time:    {total_wall_ms / total_reads:.2f} ms/read")

            # Verdict
            self.log.emit(f"\n  {'='*56}")
            self.log.emit(f"  VERDICT")
            self.log.emit(f"  {'='*56}")
            self.log.emit(f"    OPC UA network latency:  {overall_med:.1f} ms (median)")
            self.log.emit(f"    In PLC cycles:           {overall_med / plc_cycle_ms:.1f} cycles")
            self.log.emit(f"    Best case:               {overall_min:.1f} ms ({overall_min / plc_cycle_ms:.1f} cycles)")
            self.log.emit(f"    Worst case:              {overall_max:.1f} ms ({overall_max / plc_cycle_ms:.1f} cycles)")

            if overall_med <= plc_cycle_ms * 2:
                grade = "EXCELLENT"
                desc = "Sub-2-cycle latency, suitable for real-time monitoring"
            elif overall_med <= plc_cycle_ms * 5:
                grade = "GOOD"
                desc = "Acceptable for most monitoring and recording tasks"
            elif overall_med <= plc_cycle_ms * 10:
                grade = "FAIR"
                desc = "Some lag, might miss fast transients"
            else:
                grade = "POOR"
                desc = "High latency, not suitable for fast variable tracking"
            self.log.emit(f"    Grade:                   {grade}")
            self.log.emit(f"    Assessment:              {desc}")
            self.log.emit(f"  {'='*56}")

            results["_summary_"] = {
                "num_vars": total_vars,
                "vars_active": vars_with_changes,
                "reads_per_var": num_reads,
                "plc_cycle_ms": plc_cycle_ms,
                "total_samples": n,
                "total_reads": total_reads,
                "total_wall_ms": round(total_wall_ms, 2),
                "min_ms": round(overall_min, 2),
                "avg_ms": round(overall_avg, 2),
                "median_ms": round(overall_med, 2),
                "p95_ms": round(overall_p95, 2),
                "p99_ms": round(overall_p99, 2),
                "max_ms": round(overall_max, 2),
                "stddev_ms": round(overall_std, 2),
                "grade": grade,
                "per_var": per_var,
            }
        else:
            self.log.emit(f"\n  No changes detected on any variable. Is the PLC running?")

        self.progress.emit(100)
        return results

    def _cycle_probe_array(self, node_id, name, first_val, num_reads, plc_cycle_ms):
        """Cycle probe for array variables (picks random elements)."""
        num_probes = self.test_config.get("cycle_probe_count", 10)
        array_len = len(first_val)
        if array_len < num_probes:
            num_probes = array_len

        self.log.emit(f"  MODE: Array variable — {name}: Array[{array_len}]")
        self.log.emit(f"  Picking {num_probes} random indices, {num_reads} reads each\n")

        node = self.client.get_node(node_id)
        probe_indices = sorted(random.sample(range(array_len), num_probes))
        self.log.emit(f"  Probe indices: {probe_indices}\n")

        all_latencies_ms = []
        per_probe = {}

        for pi, elem_idx in enumerate(probe_indices):
            if self._stop:
                break

            values = []
            timestamps = []
            deltas = []
            derived_latencies = []

            try:
                arr = node.get_value()
                prev_val = arr[elem_idx]
                prev_time = time.perf_counter()
                values.append(prev_val)
                timestamps.append(prev_time)
            except Exception as e:
                self.log.emit(f"    [{elem_idx}] Error: {e}")
                continue

            for r in range(num_reads):
                if self._stop:
                    break
                try:
                    arr = node.get_value()
                    cur_val = arr[elem_idx]
                    cur_time = time.perf_counter()

                    val_delta = cur_val - prev_val
                    values.append(cur_val)
                    timestamps.append(cur_time)

                    if val_delta != 0:
                        if val_delta < 0:
                            val_delta = val_delta + 4294967296
                        derived_ms = val_delta * plc_cycle_ms
                        deltas.append(val_delta)
                        derived_latencies.append(derived_ms)
                        all_latencies_ms.append(derived_ms)

                    prev_val = cur_val
                    prev_time = cur_time
                except Exception:
                    pass

                pct = int(((pi * num_reads + r + 1) / (num_probes * num_reads)) * 100)
                self.progress.emit(min(pct, 99))

            total_wall_ms = (timestamps[-1] - timestamps[0]) * 1000 if len(timestamps) > 1 else 0
            reads_with_change = len(deltas)
            reads_no_change = num_reads - reads_with_change

            if derived_latencies:
                avg_lat = statistics.mean(derived_latencies)
                med_lat = statistics.median(derived_latencies)
                min_lat = min(derived_latencies)
                max_lat = max(derived_latencies)
                avg_delta = statistics.mean(deltas)

                self.log.emit(
                    f"  [{elem_idx:4d}]  val:{values[0]:>10d}→{values[-1]:<10d}  "
                    f"changes:{reads_with_change:>4d}/{num_reads}  "
                    f"avgΔ:{avg_delta:.1f}  "
                    f"lat: {min_lat:.1f}/{avg_lat:.1f}/{med_lat:.1f}/{max_lat:.1f} ms")

                per_probe[elem_idx] = {
                    "reads": num_reads,
                    "reads_with_change": reads_with_change,
                    "reads_same": reads_no_change,
                    "value_start": values[0],
                    "value_end": values[-1],
                    "wall_ms": round(total_wall_ms, 2),
                    "avg_val_delta": round(avg_delta, 2),
                    "min_latency_ms": round(min_lat, 2),
                    "avg_latency_ms": round(avg_lat, 2),
                    "median_latency_ms": round(med_lat, 2),
                    "max_latency_ms": round(max_lat, 2),
                }
            else:
                self.log.emit(f"  [{elem_idx:4d}]  NO CHANGES in {num_reads} reads")
                per_probe[elem_idx] = {
                    "reads": num_reads, "reads_with_change": 0, "reads_same": num_reads,
                    "value_start": values[0] if values else 0,
                    "value_end": values[-1] if values else 0,
                    "wall_ms": round(total_wall_ms, 2),
                }

        # Summary
        results = {}
        if all_latencies_ms:
            sorted_lat = sorted(all_latencies_ms)
            p95_idx = min(int(len(sorted_lat) * 0.95), len(sorted_lat) - 1)
            p99_idx = min(int(len(sorted_lat) * 0.99), len(sorted_lat) - 1)

            self.log.emit(f"\n{'='*60}")
            self.log.emit(f"  SUMMARY: {name} — Array[{array_len}], "
                          f"{num_probes} probes × {num_reads} reads")
            self.log.emit(f"{'='*60}")
            self.log.emit(f"    Min:    {min(all_latencies_ms):.1f} ms")
            self.log.emit(f"    Avg:    {statistics.mean(all_latencies_ms):.1f} ms")
            self.log.emit(f"    Median: {statistics.median(all_latencies_ms):.1f} ms")
            self.log.emit(f"    P95:    {sorted_lat[p95_idx]:.1f} ms")
            self.log.emit(f"    P99:    {sorted_lat[p99_idx]:.1f} ms")
            self.log.emit(f"    Max:    {max(all_latencies_ms):.1f} ms")
            self.log.emit(f"    => OPC UA read latency ≈ {statistics.median(all_latencies_ms):.1f} ms (median)")

            results[name] = {
                "array_length": array_len,
                "probes": num_probes,
                "reads_per_probe": num_reads,
                "plc_cycle_ms": plc_cycle_ms,
                "total_samples": len(all_latencies_ms),
                "min_ms": round(min(all_latencies_ms), 2),
                "avg_ms": round(statistics.mean(all_latencies_ms), 2),
                "median_ms": round(statistics.median(all_latencies_ms), 2),
                "p95_ms": round(sorted_lat[p95_idx], 2),
                "p99_ms": round(sorted_lat[p99_idx], 2),
                "max_ms": round(max(all_latencies_ms), 2),
                "stddev_ms": round(statistics.stdev(all_latencies_ms), 2) if len(all_latencies_ms) > 1 else 0,
                "per_probe": per_probe,
            }

        self.progress.emit(100)
        return results

    def _test_plc_cpu(self):
        """Read B&R PLC CPU/drive load via OPC UA - AxesCPULoad program variables."""
        self.log.emit(f"\n{'='*60}")
        self.log.emit("B&R PLC CPU / DRIVE LOAD")
        self.log.emit(f"{'='*60}")

        results = {"found_nodes": [], "readings": [], "drive_loads": []}

        # B&R AxesCPULoad task names (as they appear in Cpu.sw)
        # The program AxesCPULoadExt is mapped as task "AxesCPULo1" 
        # The program AxesCPULoad is mapped as task "AxesCPULoa"
        task_names = ["AxesCPULo1", "AxesCPULoa", "AxesCPULoadExt", "AxesCPULoad"]

        # FB internal vars to read
        fb_vars = [
            ("fbCPULoadDrive._MaxLoad", "Max CPU Load (raw)"),
            ("fbCPULoadDrive._AvgLoad", "Avg CPU Load (raw)"),
            ("fbCPULoadDrive.DriveName", "Current Drive Name"),
            ("fbCPULoadDrive.Ready", "FB Ready"),
            ("fbCPULoadDrive.Busy", "FB Busy"),
            ("fbCPULoadDrive.Error", "FB Error"),
            ("fbCPULoadDrive.ScaleMax", "Scale Max"),
            ("Counter", "Drive Counter"),
            ("MAX_COUNTER", "Max Counter"),
        ]

        # Enable flags for different configurations
        enable_flags = [
            "EnableRecordTamarDrives",
            "EnableRecordBarakDrives",
            "EnableRecordAyalaDrives",
            "EnableRecordShaniDrives",
            "EnableRecordAradDrives",
            "EnableRecordHilaDrives",
            "EnableRecordNegevSingleDrives",
            "EnableRecordNegevLineDrives",
            "EnableRecordWHSDrives",
            "EnableRecordEilatDrives",
        ]

        self.log.emit("\n  --- Searching for AxesCPULoad program variables ---")
        found_task = None

        for task_name in task_names:
            if self._stop:
                return results
            self.log.emit(f"\n  Trying task: {task_name}")
            for var_path, desc in fb_vars:
                node_path = f"ns=6;s=::{task_name}:{var_path}"
                try:
                    node = self.client.get_node(node_path)
                    value = node.get_value()
                    results["readings"].append({
                        "name": f"{task_name}/{var_path}",
                        "value": str(value),
                        "node_id": node_path,
                        "description": desc
                    })
                    self.log.emit(f"    {desc}: {var_path} = {value}")
                    found_task = task_name
                except Exception:
                    pass

            # Try reading enable flags
            for flag in enable_flags:
                node_path = f"ns=6;s=::{task_name}:{flag}"
                try:
                    node = self.client.get_node(node_path)
                    value = node.get_value()
                    results["readings"].append({
                        "name": f"{task_name}/{flag}",
                        "value": str(value),
                        "node_id": node_path,
                        "description": f"Enable flag: {flag}"
                    })
                    self.log.emit(f"    {flag} = {value}")
                    found_task = task_name
                except Exception:
                    pass

            if found_task:
                self.log.emit(f"\n  Found AxesCPULoad task: {found_task}")
                break

        # If user wants to enable and monitor drive CPU load recording
        enable_config = self.test_config.get("enable_cpu_config")
        if enable_config and found_task:
            self.log.emit(f"\n  --- Enabling CPU load recording: {enable_config} ---")
            flag_path = f"ns=6;s=::{found_task}:{enable_config}"
            try:
                node = self.client.get_node(flag_path)
                node.set_value(ua.DataValue(ua.Variant(True, ua.VariantType.Boolean)))
                self.log.emit(f"  Enabled {enable_config}")

                # Now monitor _MaxLoad over time as the FB cycles through drives
                self.log.emit(f"\n  --- Monitoring drive CPU loads (waiting for FB cycle) ---")
                max_load_path = f"ns=6;s=::{found_task}:fbCPULoadDrive._MaxLoad"
                drive_name_path = f"ns=6;s=::{found_task}:fbCPULoadDrive.DriveName"
                counter_path = f"ns=6;s=::{found_task}:Counter"
                scale_path = f"ns=6;s=::{found_task}:fbCPULoadDrive.ScaleMax"

                max_load_node = self.client.get_node(max_load_path)
                drive_name_node = self.client.get_node(drive_name_path)
                counter_node = self.client.get_node(counter_path)

                try:
                    scale_node = self.client.get_node(scale_path)
                    scale_max = scale_node.get_value()
                    if not scale_max or scale_max == 0:
                        scale_max = 40000
                except Exception:
                    scale_max = 40000

                seen_drives = {}
                last_counter = -1
                samples = 0
                max_samples = self.test_config.get("cpu_monitor_samples", 60)

                while samples < max_samples and not self._stop:
                    try:
                        counter = counter_node.get_value()
                        if counter != last_counter:
                            last_counter = counter
                            drive_name = drive_name_node.get_value()
                            max_load_raw = max_load_node.get_value()
                            load_pct = (max_load_raw * 100) / scale_max if scale_max else 0

                            if drive_name and drive_name.strip():
                                drive_key = drive_name.strip()
                                seen_drives[drive_key] = {
                                    "drive": drive_key,
                                    "max_load_raw": max_load_raw,
                                    "max_load_pct": round(load_pct, 2),
                                    "scale_max": scale_max,
                                    "counter_idx": counter,
                                    "timestamp": datetime.now().isoformat()
                                }
                                self.log.emit(f"    [{counter:2d}] {drive_key:20s} -> "
                                              f"Max Load: {load_pct:.1f}% (raw: {max_load_raw})")

                        samples += 1
                        time.sleep(0.3)
                        self.progress.emit(87 + int((samples / max_samples) * 13))
                    except Exception as e:
                        self.log.emit(f"    Sample error: {e}")
                        samples += 1
                        time.sleep(0.3)

                results["drive_loads"] = list(seen_drives.values())

                if seen_drives:
                    self.log.emit(f"\n  --- Drive CPU Load Summary ---")
                    self.log.emit(f"  {'Drive':<20s} {'Max Load %':>12s} {'Raw':>10s}")
                    self.log.emit(f"  {'-'*20} {'-'*12} {'-'*10}")
                    for d in sorted(seen_drives.values(), key=lambda x: x["max_load_pct"], reverse=True):
                        self.log.emit(f"  {d['drive']:<20s} {d['max_load_pct']:>11.1f}% {d['max_load_raw']:>10d}")

                # Disable recording when done
                try:
                    node.set_value(ua.DataValue(ua.Variant(False, ua.VariantType.Boolean)))
                    self.log.emit(f"\n  Disabled {enable_config}")
                except Exception:
                    pass

            except Exception as e:
                self.log.emit(f"  Error enabling CPU load recording: {e}")

        # Also try custom CPU node if provided
        cpu_node_id = self.test_config.get("cpu_node_id")
        if cpu_node_id:
            self.log.emit(f"\n  --- Custom CPU node: {cpu_node_id} ---")
            try:
                node = self.client.get_node(cpu_node_id)
                samples = []
                for i in range(20):
                    if self._stop:
                        break
                    try:
                        val = node.get_value()
                        samples.append({"time": datetime.now().isoformat(), "value": val})
                        self.log.emit(f"    Sample {i+1}: {val}")
                        time.sleep(0.5)
                    except Exception as e:
                        self.log.emit(f"    Sample {i+1}: Error - {e}")
                    self.progress.emit(87 + int((i / 20) * 13))
                results["cpu_samples"] = samples
            except Exception as e:
                self.log.emit(f"  Error reading custom CPU node: {e}")

        if not results["readings"] and not results["drive_loads"] and not found_task:
            self.log.emit("\n  No AxesCPULoad variables found via OPC UA.")
            self.log.emit("  Possible reasons:")
            self.log.emit("    - AxesCPULoad task is not running on this configuration")
            self.log.emit("    - OPC UA variable publishing not enabled for this program")
            self.log.emit("    - Task name differs from expected (AxesCPULo1/AxesCPULoa)")
            self.log.emit("  TIP: Browse the OPC UA tree to find the correct task name")

        self.progress.emit(100)
        return results


class PerformanceBenchmark(QWidget):
    """Performance Benchmark tab for measuring OPC UA communication performance."""

    def __init__(self, parent=None, client=None):
        super().__init__(parent)
        self.client = client
        self.selected_vars = {}  # {name: node_id}
        self.last_results = None
        self.worker = None
        self.init_ui()

    def init_ui(self):
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        # Main horizontal splitter: left (config+results) | right (log)
        self.main_splitter = QSplitter(Qt.Horizontal)
        self.main_splitter.setStyleSheet("""
            QSplitter::handle { background: #2a3a5a; width: 3px; }
        """)
        outer_layout.addWidget(self.main_splitter)

        # ==================== LEFT PANEL ====================
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(6, 6, 3, 6)
        left_layout.setSpacing(4)

        # Vertical splitter for left side sections
        self.left_splitter = QSplitter(Qt.Vertical)
        self.left_splitter.setStyleSheet("""
            QSplitter::handle { background: #2a3a5a; height: 3px; }
        """)

        # --- Section: Test Configuration (collapsible) ---
        config_section = CollapsibleSection("Test Configuration")

        dir_row = QHBoxLayout()
        dir_label = QLabel("Directory:")
        dir_label.setStyleSheet("color: #e0e0e0;")
        self.dir_combo = QComboBox()
        self.dir_combo.setStyleSheet("""
            QComboBox {
                border: 1px solid #2a3a5a; border-radius: 6px; padding: 6px;
                background: #16213e; color: #e0e0e0;
            }
            QComboBox QAbstractItemView {
                background: #16213e; border: 1px solid #2a3a5a;
                selection-background-color: #0f3460; color: #e0e0e0;
            }
        """)
        self.dir_combo.currentIndexChanged.connect(self.directory_changed)
        dir_row.addWidget(dir_label)
        dir_row.addWidget(self.dir_combo, 1)
        config_section.addLayout(dir_row)

        self.var_table = QTableWidget()
        self.var_table.setColumnCount(3)
        self.var_table.setHorizontalHeaderLabels(["Select", "Variable", "Node ID"])
        self.var_table.setStyleSheet("""
            QTableWidget {
                background: #16213e; border: 1px solid #2a3a5a;
                border-radius: 6px; color: #e0e0e0; gridline-color: #2a3a5a;
            }
            QHeaderView::section {
                background: #0f3460; color: #f0f0f0; border: none;
                border-right: 1px solid #2a3a5a; border-bottom: 1px solid #2a3a5a; padding: 4px;
            }
        """)
        header = self.var_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        self.var_table.setColumnWidth(0, 50)
        config_section.addWidget(self.var_table)

        sel_row = QHBoxLayout()
        self.select_all_btn = QPushButton("Select All")
        self.select_all_btn.clicked.connect(lambda: self._toggle_all(True))
        self.deselect_all_btn = QPushButton("Deselect All")
        self.deselect_all_btn.clicked.connect(lambda: self._toggle_all(False))
        for btn in [self.select_all_btn, self.deselect_all_btn]:
            btn.setStyleSheet("padding: 4px 10px;")
        sel_row.addWidget(self.select_all_btn)
        sel_row.addWidget(self.deselect_all_btn)
        sel_row.addStretch()
        config_section.addLayout(sel_row)

        self.left_splitter.addWidget(config_section)

        # --- Section: Test Parameters (collapsible) ---
        params_section = CollapsibleSection("Test Parameters")

        params_row = QHBoxLayout()
        iter_label = QLabel("Iterations:")
        iter_label.setStyleSheet("color: #e0e0e0;")
        self.iter_spin = QSpinBox()
        self.iter_spin.setRange(10, 10000)
        self.iter_spin.setValue(100)
        self.iter_spin.setStyleSheet("background: #16213e; color: #e0e0e0; border: 1px solid #2a3a5a; border-radius: 6px; padding: 4px;")
        dur_label = QLabel("Throughput (s):")
        dur_label.setStyleSheet("color: #e0e0e0;")
        self.dur_spin = QSpinBox()
        self.dur_spin.setRange(1, 60)
        self.dur_spin.setValue(5)
        self.dur_spin.setStyleSheet("background: #16213e; color: #e0e0e0; border: 1px solid #2a3a5a; border-radius: 6px; padding: 4px;")
        params_row.addWidget(iter_label)
        params_row.addWidget(self.iter_spin)
        params_row.addSpacing(10)
        params_row.addWidget(dur_label)
        params_row.addWidget(self.dur_spin)
        params_row.addStretch()
        params_section.addLayout(params_row)

        tests_row = QHBoxLayout()
        self.chk_single = QCheckBox("Single Read")
        self.chk_single.setChecked(True)
        self.chk_batch = QCheckBox("Batch Read")
        self.chk_batch.setChecked(True)
        self.chk_throughput = QCheckBox("Throughput")
        self.chk_throughput.setChecked(True)
        self.chk_array = QCheckBox("Array Read")
        self.chk_array.setChecked(True)
        self.chk_write = QCheckBox("Write")
        self.chk_write.setChecked(False)
        self.chk_cpu = QCheckBox("PLC CPU")
        self.chk_cpu.setChecked(False)
        self.chk_roundtrip = QCheckBox("Round-Trip")
        self.chk_roundtrip.setChecked(True)
        self.chk_change_detect = QCheckBox("Detection Capability")
        self.chk_change_detect.setChecked(True)
        self.chk_array_scan = QCheckBox("Array Scan")
        self.chk_array_scan.setChecked(False)
        self.chk_cycle_probe = QCheckBox("Cycle Probe")
        self.chk_cycle_probe.setChecked(True)
        for chk in [self.chk_single, self.chk_batch, self.chk_throughput, self.chk_array,
                     self.chk_write, self.chk_cpu, self.chk_roundtrip, self.chk_change_detect,
                     self.chk_array_scan, self.chk_cycle_probe]:
            chk.setStyleSheet("color: #e0e0e0;")
            tests_row.addWidget(chk)
        tests_row.addStretch()
        params_section.addLayout(tests_row)

        # Detection capability duration
        cd_row = QHBoxLayout()
        cd_label = QLabel("Detection Test (s):")
        cd_label.setStyleSheet("color: #e0e0e0;")
        self.change_dur_spin = QSpinBox()
        self.change_dur_spin.setRange(1, 120)
        self.change_dur_spin.setValue(10)
        self.change_dur_spin.setToolTip("Duration per phase of detection capability test")
        self.change_dur_spin.setStyleSheet("background: #16213e; color: #e0e0e0; border: 1px solid #2a3a5a; border-radius: 6px; padding: 4px;")
        arr_scan_label = QLabel("Array Scan Iters:")
        arr_scan_label.setStyleSheet("color: #e0e0e0;")
        self.array_scan_spin = QSpinBox()
        self.array_scan_spin.setRange(1, 1000)
        self.array_scan_spin.setValue(50)
        self.array_scan_spin.setToolTip("Number of full array read iterations for element scan")
        self.array_scan_spin.setStyleSheet("background: #16213e; color: #e0e0e0; border: 1px solid #2a3a5a; border-radius: 6px; padding: 4px;")
        cd_row.addWidget(cd_label)
        cd_row.addWidget(self.change_dur_spin)
        cd_row.addSpacing(10)
        cd_row.addWidget(arr_scan_label)
        cd_row.addWidget(self.array_scan_spin)
        cd_row.addStretch()
        params_section.addLayout(cd_row)

        # Cycle probe parameters
        cp_row = QHBoxLayout()
        cp_probes_label = QLabel("Probes:")
        cp_probes_label.setStyleSheet("color: #e0e0e0;")
        self.cycle_probe_count_spin = QSpinBox()
        self.cycle_probe_count_spin.setRange(1, 100)
        self.cycle_probe_count_spin.setValue(10)
        self.cycle_probe_count_spin.setToolTip("Number of random array elements to probe")
        self.cycle_probe_count_spin.setStyleSheet("background: #16213e; color: #e0e0e0; border: 1px solid #2a3a5a; border-radius: 6px; padding: 4px;")
        cp_reads_label = QLabel("Samples/var:")
        cp_reads_label.setStyleSheet("color: #e0e0e0;")
        self.cycle_probe_reads_spin = QSpinBox()
        self.cycle_probe_reads_spin.setRange(10, 50000)
        self.cycle_probe_reads_spin.setValue(200)
        self.cycle_probe_reads_spin.setToolTip("Number of consecutive reads per variable (more = better statistics)")
        self.cycle_probe_reads_spin.setStyleSheet("background: #16213e; color: #e0e0e0; border: 1px solid #2a3a5a; border-radius: 6px; padding: 4px;")
        cp_cycle_label = QLabel("PLC Cycle (ms):")
        cp_cycle_label.setStyleSheet("color: #e0e0e0;")
        self.plc_cycle_spin = QDoubleSpinBox()
        self.plc_cycle_spin.setRange(0.1, 100.0)
        self.plc_cycle_spin.setValue(1.6)
        self.plc_cycle_spin.setSingleStep(0.1)
        self.plc_cycle_spin.setDecimals(1)
        self.plc_cycle_spin.setToolTip("PLC task cycle time in ms (value increments once per cycle)")
        self.plc_cycle_spin.setStyleSheet("background: #16213e; color: #e0e0e0; border: 1px solid #2a3a5a; border-radius: 6px; padding: 4px;")
        cp_row.addWidget(cp_probes_label)
        cp_row.addWidget(self.cycle_probe_count_spin)
        cp_row.addSpacing(10)
        cp_row.addWidget(cp_reads_label)
        cp_row.addWidget(self.cycle_probe_reads_spin)
        cp_row.addSpacing(10)
        cp_row.addWidget(cp_cycle_label)
        cp_row.addWidget(self.plc_cycle_spin)
        cp_row.addStretch()
        params_section.addLayout(cp_row)

        self.left_splitter.addWidget(params_section)

        # --- Section: B&R CPU Config (collapsible) ---
        cpu_section = CollapsibleSection("B&R CPU / Drive Load")

        cpu_row = QHBoxLayout()
        cpu_label = QLabel("CPU Node ID:")
        cpu_label.setStyleSheet("color: #e0e0e0;")
        self.cpu_node_input = QComboBox()
        self.cpu_node_input.setEditable(True)
        self.cpu_node_input.addItems(["", "ns=6;s=::AsGlobalPV:CPU.Usage", "ns=6;s=::_sysvar:CPU"])
        self.cpu_node_input.setStyleSheet("""
            QComboBox {
                border: 1px solid #2a3a5a; border-radius: 6px; padding: 6px;
                background: #16213e; color: #e0e0e0;
            }
            QComboBox QAbstractItemView { background: #16213e; border: 1px solid #2a3a5a; color: #e0e0e0; }
        """)
        cpu_row.addWidget(cpu_label)
        cpu_row.addWidget(self.cpu_node_input, 1)
        cpu_section.addLayout(cpu_row)

        bnr_row = QHBoxLayout()
        bnr_label = QLabel("Config:")
        bnr_label.setStyleSheet("color: #e0e0e0;")
        self.bnr_config_combo = QComboBox()
        self.bnr_config_combo.addItems([
            "(Don't enable - just read current state)",
            "EnableRecordHilaDrives", "EnableRecordTamarDrives",
            "EnableRecordBarakDrives", "EnableRecordAyalaDrives",
            "EnableRecordShaniDrives", "EnableRecordAradDrives",
            "EnableRecordNegevSingleDrives", "EnableRecordNegevLineDrives",
            "EnableRecordWHSDrives", "EnableRecordEilatDrives",
        ])
        self.bnr_config_combo.setStyleSheet("""
            QComboBox {
                border: 1px solid #2a3a5a; border-radius: 6px; padding: 6px;
                background: #16213e; color: #e0e0e0;
            }
            QComboBox QAbstractItemView { background: #16213e; border: 1px solid #2a3a5a; color: #e0e0e0; }
        """)
        bnr_row.addWidget(bnr_label)
        bnr_row.addWidget(self.bnr_config_combo, 1)
        cpu_section.addLayout(bnr_row)

        cpu_samples_row = QHBoxLayout()
        cpu_samp_label = QLabel("Samples:")
        cpu_samp_label.setStyleSheet("color: #e0e0e0;")
        self.cpu_samples_spin = QSpinBox()
        self.cpu_samples_spin.setRange(10, 300)
        self.cpu_samples_spin.setValue(60)
        self.cpu_samples_spin.setToolTip("Number of samples when monitoring drive CPU loads (0.3s each)")
        self.cpu_samples_spin.setStyleSheet("background: #16213e; color: #e0e0e0; border: 1px solid #2a3a5a; border-radius: 6px; padding: 4px;")
        cpu_samples_row.addWidget(cpu_samp_label)
        cpu_samples_row.addWidget(self.cpu_samples_spin)
        cpu_samples_row.addStretch()
        cpu_section.addLayout(cpu_samples_row)

        self.left_splitter.addWidget(cpu_section)

        # --- Controls bar (always visible) ---
        ctrl_widget = QWidget()
        ctrl_layout = QHBoxLayout(ctrl_widget)
        ctrl_layout.setContentsMargins(0, 4, 0, 4)
        self.run_btn = QPushButton("Run Benchmark")
        self.run_btn.setStyleSheet("""
            QPushButton {
                background-color: #0f3460; color: #e0e0e0; border: none;
                padding: 8px 20px; border-radius: 8px; font-size: 11pt; font-weight: bold;
            }
            QPushButton:hover { background-color: #e94560; color: #ffffff; }
            QPushButton:pressed { background-color: #c73650; }
            QPushButton:disabled { background-color: #1a1a2e; color: #555; }
        """)
        self.run_btn.clicked.connect(self.run_benchmark)
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setEnabled(False)
        self.stop_btn.setStyleSheet("""
            QPushButton {
                background-color: #e94560; color: #ffffff; border: none;
                padding: 8px 20px; border-radius: 8px; font-size: 11pt; font-weight: bold;
            }
            QPushButton:hover { background-color: #ff6b81; }
            QPushButton:disabled { background-color: #1a1a2e; color: #555; }
        """)
        self.stop_btn.clicked.connect(self.stop_benchmark)
        self.progress_bar = QProgressBar()
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #2a3a5a; border-radius: 8px; text-align: center;
                background: #16213e; color: #e0e0e0; height: 22px;
            }
            QProgressBar::chunk { background-color: #e94560; border-radius: 7px; }
        """)
        ctrl_layout.addWidget(self.run_btn)
        ctrl_layout.addWidget(self.stop_btn)
        ctrl_layout.addWidget(self.progress_bar, 1)
        self.left_splitter.addWidget(ctrl_widget)

        # --- Section: Results Table (collapsible, in splitter) ---
        results_section = CollapsibleSection("Results")
        self.results_table = QTableWidget()
        self.results_table.setStyleSheet("""
            QTableWidget {
                background: #16213e; border: 1px solid #2a3a5a;
                border-radius: 6px; color: #e0e0e0; gridline-color: #2a3a5a;
            }
            QTableWidget::item { color: #f0f0f0; padding: 4px; }
            QTableWidget::item:selected { background: #0f3460; color: #fff; }
            QHeaderView::section {
                background: #0f3460; color: #f0f0f0; border: none;
                border-right: 1px solid #2a3a5a; border-bottom: 1px solid #2a3a5a; padding: 4px;
            }
        """)
        self.results_table.setAlternatingRowColors(True)
        results_section.addWidget(self.results_table)

        export_row = QHBoxLayout()
        self.export_btn = QPushButton("Export Results to CSV")
        self.export_btn.setStyleSheet("""
            QPushButton {
                background-color: #0f3460; color: #e0e0e0; border: none;
                padding: 6px 14px; border-radius: 8px;
            }
            QPushButton:hover { background-color: #e94560; color: #ffffff; }
        """)
        self.export_btn.clicked.connect(self.export_csv)
        export_row.addStretch()
        export_row.addWidget(self.export_btn)
        results_section.addLayout(export_row)

        self.left_splitter.addWidget(results_section)

        left_layout.addWidget(self.left_splitter)
        self.main_splitter.addWidget(left_widget)

        # ==================== RIGHT PANEL (Log) ====================
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(3, 6, 6, 6)
        right_layout.setSpacing(4)

        log_label = QLabel("Benchmark Log")
        log_label.setStyleSheet("font-weight: bold; font-size: 11pt; color: #e0e0e0;")
        right_layout.addWidget(log_label)

        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setStyleSheet("""
            QTextEdit {
                background: #0d1117; border: 1px solid #2a3a5a;
                border-radius: 8px; color: #4fc3f7;
                font-family: Consolas, monospace; font-size: 10pt;
            }
        """)
        right_layout.addWidget(self.log_output)

        clear_btn = QPushButton("Clear Log")
        clear_btn.setStyleSheet("padding: 4px 10px;")
        clear_btn.clicked.connect(self.log_output.clear)
        clear_row = QHBoxLayout()
        clear_row.addStretch()
        clear_row.addWidget(clear_btn)
        right_layout.addLayout(clear_row)

        self.main_splitter.addWidget(right_widget)

        # Set initial splitter sizes (70% left, 30% right)
        self.main_splitter.setSizes([700, 300])

    def _toggle_all(self, checked):
        for row in range(self.var_table.rowCount()):
            widget = self.var_table.cellWidget(row, 0)
            if widget:
                cb = widget.findChild(QCheckBox)
                if cb:
                    cb.setChecked(checked)

    def add_variable(self, full_path, node_id):
        """Add a variable to the benchmark table. Returns True if added, False if duplicate."""
        # Check for duplicates
        for row in range(self.var_table.rowCount()):
            existing_nid = self.var_table.item(row, 2)
            if existing_nid and existing_nid.text() == node_id:
                return False
        
        row = self.var_table.rowCount()
        self.var_table.insertRow(row)

        cb = QCheckBox()
        cb.setChecked(True)
        cb_widget = QWidget()
        cb_layout = QHBoxLayout(cb_widget)
        cb_layout.addWidget(cb)
        cb_layout.setAlignment(Qt.AlignCenter)
        cb_layout.setContentsMargins(0, 0, 0, 0)
        self.var_table.setCellWidget(row, 0, cb_widget)

        self.var_table.setItem(row, 1, QTableWidgetItem(full_path))
        self.var_table.setItem(row, 2, QTableWidgetItem(node_id))
        return True

    def update_directory_list(self, directories):
        self.dir_combo.clear()
        for path, node_id in directories.items():
            self.dir_combo.addItem(path, node_id)

    def directory_changed(self):
        self.var_table.setRowCount(0)
        index = self.dir_combo.currentIndex()
        if index < 0 or not self.client:
            return
        try:
            node_id = self.dir_combo.itemData(index)
            node = self.client.get_node(node_id)
            children = node.get_children()
            current_dir = self.dir_combo.currentText()

            for child in children:
                try:
                    if child.get_node_class() == ua.NodeClass.Variable:
                        display_name = child.get_display_name().Text
                        full_path = f"{current_dir}/{display_name}"
                        nid = child.nodeid.to_string()
                        row = self.var_table.rowCount()
                        self.var_table.insertRow(row)

                        # Checkbox
                        cb = QCheckBox()
                        cb.setChecked(True)
                        cb_widget = QWidget()
                        cb_layout = QHBoxLayout(cb_widget)
                        cb_layout.addWidget(cb)
                        cb_layout.setAlignment(Qt.AlignCenter)
                        cb_layout.setContentsMargins(0, 0, 0, 0)
                        self.var_table.setCellWidget(row, 0, cb_widget)

                        self.var_table.setItem(row, 1, QTableWidgetItem(full_path))
                        self.var_table.setItem(row, 2, QTableWidgetItem(nid))
                except Exception:
                    pass
        except Exception as e:
            self.log_output.append(f"Error loading variables: {e}")

    def _get_selected_vars(self):
        names = []
        node_ids = []
        for row in range(self.var_table.rowCount()):
            widget = self.var_table.cellWidget(row, 0)
            if widget:
                cb = widget.findChild(QCheckBox)
                if cb and cb.isChecked():
                    name = self.var_table.item(row, 1).text()
                    nid = self.var_table.item(row, 2).text()
                    names.append(name)
                    node_ids.append(nid)
        return names, node_ids

    def run_benchmark(self):
        if not self.client:
            QMessageBox.warning(self, "Not Connected", "Please connect to the OPC UA server first.")
            return

        var_names, node_ids = self._get_selected_vars()
        if not node_ids:
            QMessageBox.warning(self, "No Variables", "Please select at least one variable to benchmark.")
            return

        self.log_output.clear()
        self.progress_bar.setValue(0)
        self.run_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)

        cpu_node = self.cpu_node_input.currentText().strip()
        bnr_config = self.bnr_config_combo.currentText()
        enable_config = bnr_config if bnr_config and not bnr_config.startswith("(") else None

        config = {
            "node_ids": node_ids,
            "var_names": var_names,
            "iterations": self.iter_spin.value(),
            "throughput_duration": self.dur_spin.value(),
            "single_read": self.chk_single.isChecked(),
            "batch_read": self.chk_batch.isChecked(),
            "throughput": self.chk_throughput.isChecked(),
            "array_read": self.chk_array.isChecked(),
            "write_latency": self.chk_write.isChecked(),
            "plc_cpu": self.chk_cpu.isChecked(),
            "round_trip": self.chk_roundtrip.isChecked(),
            "change_detect": self.chk_change_detect.isChecked(),
            "array_scan": self.chk_array_scan.isChecked(),
            "cycle_probe": self.chk_cycle_probe.isChecked(),
            "cycle_probe_count": self.cycle_probe_count_spin.value(),
            "cycle_probe_reads": self.cycle_probe_reads_spin.value(),
            "plc_cycle_ms": self.plc_cycle_spin.value(),
            "change_detect_duration": self.change_dur_spin.value(),
            "array_scan_iterations": self.array_scan_spin.value(),
            "cpu_node_id": cpu_node if cpu_node else None,
            "enable_cpu_config": enable_config,
            "cpu_monitor_samples": self.cpu_samples_spin.value(),
            # Progress bar segments for new tests
            "_rt_progress_base": 87,
            "_rt_progress_span": 4,
            "_cd_progress_base": 91,
            "_cd_progress_span": 5,
            "_as_progress_base": 96,
            "_as_progress_span": 4,
        }

        self.worker = BenchmarkWorker(self.client, config)
        self.worker.progress.connect(self.progress_bar.setValue)
        self.worker.log.connect(self.log_output.append)
        self.worker.result.connect(self._display_results)
        self.worker.finished_signal.connect(self._benchmark_done)
        self.worker.start()

        self.log_output.append(f"Benchmark started at {datetime.now().strftime('%H:%M:%S')}")
        self.log_output.append(f"Selected {len(node_ids)} variables, {self.iter_spin.value()} iterations")

    def stop_benchmark(self):
        if self.worker:
            self.worker.stop()
            self.log_output.append("\nBenchmark stopped by user.")

    def _benchmark_done(self):
        self.run_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.progress_bar.setValue(100)
        self.log_output.append(f"\nBenchmark finished at {datetime.now().strftime('%H:%M:%S')}")

    def _display_results(self, results):
        self.last_results = results
        rows = []

        # Single read results
        if "single_read" in results:
            for name, stats in results["single_read"].items():
                rows.append({
                    "Test": "Single Read",
                    "Variable": name,
                    "Min (ms)": stats["min_ms"],
                    "Avg (ms)": stats["avg_ms"],
                    "Max (ms)": stats["max_ms"],
                    "Median (ms)": stats["median_ms"],
                    "StdDev (ms)": stats["stddev_ms"],
                    "P95 (ms)": stats["p95_ms"],
                    "P99 (ms)": stats["p99_ms"],
                    "Errors": stats["errors"],
                    "Samples": stats["samples"],
                })

        # Batch read
        if "batch_read" in results and results["batch_read"]:
            s = results["batch_read"]
            rows.append({
                "Test": "Batch Read",
                "Variable": f"All ({s.get('num_variables', '?')} vars)",
                "Min (ms)": s.get("min_ms", ""),
                "Avg (ms)": s.get("avg_ms", ""),
                "Max (ms)": s.get("max_ms", ""),
                "Median (ms)": s.get("median_ms", ""),
                "StdDev (ms)": s.get("stddev_ms", ""),
                "P95 (ms)": s.get("p95_ms", ""),
                "P99 (ms)": "",
                "Errors": s.get("errors", ""),
                "Samples": s.get("samples", ""),
            })
            rows.append({
                "Test": "Batch (per var)",
                "Variable": f"Avg per variable",
                "Min (ms)": "",
                "Avg (ms)": s.get("avg_per_var_ms", ""),
                "Max (ms)": "",
                "Median (ms)": "",
                "StdDev (ms)": "",
                "P95 (ms)": "",
                "P99 (ms)": "",
                "Errors": "",
                "Samples": "",
            })

        # Throughput
        if "throughput" in results and results["throughput"]:
            t = results["throughput"]
            rows.append({
                "Test": "Throughput",
                "Variable": f"{t.get('total_reads', 0)} reads in {t.get('duration_sec', 0)}s",
                "Min (ms)": "",
                "Avg (ms)": "",
                "Max (ms)": "",
                "Median (ms)": "",
                "StdDev (ms)": "",
                "P95 (ms)": "",
                "P99 (ms)": "",
                "Errors": t.get("errors", ""),
                "Samples": f"{t.get('reads_per_sec', 0)} reads/s",
            })

        # Array read results
        if "array_read" in results:
            for name, stats in results["array_read"].items():
                rows.append({
                    "Test": "Array Read",
                    "Variable": f"{name} [{stats['array_length']}x{stats['element_type']}]",
                    "Min (ms)": stats["min_ms"],
                    "Avg (ms)": stats["avg_ms"],
                    "Max (ms)": stats["max_ms"],
                    "Median (ms)": stats["median_ms"],
                    "StdDev (ms)": stats["stddev_ms"],
                    "P95 (ms)": stats["p95_ms"],
                    "P99 (ms)": stats["p99_ms"],
                    "Errors": stats["errors"],
                    "Samples": f"{stats['samples']} (~{stats['throughput_elements_per_sec']} elem/s)",
                })

        # Write latency
        if "write_latency" in results:
            for name, stats in results["write_latency"].items():
                rows.append({
                    "Test": "Write",
                    "Variable": name,
                    "Min (ms)": stats["min_ms"],
                    "Avg (ms)": stats["avg_ms"],
                    "Max (ms)": stats["max_ms"],
                    "Median (ms)": "",
                    "StdDev (ms)": stats["stddev_ms"],
                    "P95 (ms)": "",
                    "P99 (ms)": "",
                    "Errors": stats["errors"],
                    "Samples": stats["samples"],
                })

        # PLC CPU readings
        if "plc_cpu" in results:
            cpu = results["plc_cpu"]
            for reading in cpu.get("readings", []):
                rows.append({
                    "Test": "PLC Info",
                    "Variable": reading["name"],
                    "Min (ms)": "",
                    "Avg (ms)": reading["value"],
                    "Max (ms)": "",
                    "Median (ms)": "",
                    "StdDev (ms)": "",
                    "P95 (ms)": "",
                    "P99 (ms)": "",
                    "Errors": "",
                    "Samples": reading.get("node_id", ""),
                })
            for dl in cpu.get("drive_loads", []):
                rows.append({
                    "Test": "Drive CPU",
                    "Variable": dl["drive"],
                    "Min (ms)": "",
                    "Avg (ms)": f"{dl['max_load_pct']}%",
                    "Max (ms)": str(dl["max_load_raw"]),
                    "Median (ms)": "",
                    "StdDev (ms)": "",
                    "P95 (ms)": "",
                    "P99 (ms)": f"scale:{dl['scale_max']}",
                    "Errors": "",
                    "Samples": f"idx:{dl['counter_idx']}",
                })

        # Round-trip results
        if "round_trip" in results:
            for name, stats in results["round_trip"].items():
                rows.append({
                    "Test": "Round-Trip",
                    "Variable": name,
                    "Min (ms)": stats["min_ms"],
                    "Avg (ms)": stats["avg_ms"],
                    "Max (ms)": stats["max_ms"],
                    "Median (ms)": stats["median_ms"],
                    "StdDev (ms)": stats["stddev_ms"],
                    "P95 (ms)": stats["p95_ms"],
                    "P99 (ms)": stats["p99_ms"],
                    "Errors": f"{stats['errors']}e/{stats['mismatches']}m",
                    "Samples": f"{stats['samples']} (W:{stats['avg_write_ms']} R:{stats['avg_read_ms']})",
                })

        # Detection Capability results
        if "change_detect" in results:
            for name, stats in results["change_detect"].items():
                if name == "_detection_summary_":
                    rows.append({
                        "Test": "Detection",
                        "Variable": "SUMMARY",
                        "Min (ms)": f"{stats['single_read_ms']} ms/read",
                        "Avg (ms)": f"{stats['scan_ms']} ms/scan",
                        "Max (ms)": f"{stats['scan_vars']} vars",
                        "Median (ms)": "",
                        "StdDev (ms)": "",
                        "P95 (ms)": f"1var: {stats['min_detect_1var_ms']}ms",
                        "P99 (ms)": f"all: {stats['min_detect_all_ms']}ms",
                        "Errors": "",
                        "Samples": f"{stats['single_rate_per_sec']:.0f} reads/s",
                    })
                else:
                    rows.append({
                        "Test": "Detection",
                        "Variable": name,
                        "Min (ms)": stats.get("min_gap_ms", ""),
                        "Avg (ms)": stats.get("avg_gap_ms", ""),
                        "Max (ms)": stats.get("max_gap_ms", ""),
                        "Median (ms)": stats.get("median_gap_ms", ""),
                        "StdDev (ms)": "",
                        "P95 (ms)": f"{stats.get('polls_per_sec', '')} scans/s",
                        "P99 (ms)": f"{stats.get('avg_read_ms', '')} ms/read",
                        "Errors": "",
                        "Samples": f"{stats.get('total_polls', '')} scans",
                    })

        # Array scan results
        if "array_scan" in results:
            for name, stats in results["array_scan"].items():
                if stats.get("avg_ms") is not None:
                    rows.append({
                        "Test": "Array Scan",
                        "Variable": f"{name} [{stats['array_length']}x{stats.get('element_type','')}]",
                        "Min (ms)": stats.get("min_ms", ""),
                        "Avg (ms)": stats.get("avg_ms", ""),
                        "Max (ms)": stats.get("max_ms", ""),
                        "Median (ms)": stats.get("median_ms", ""),
                        "StdDev (ms)": stats.get("stddev_ms", ""),
                        "P95 (ms)": stats.get("p95_ms", ""),
                        "P99 (ms)": f"{stats.get('us_per_element', '')} us/elem",
                        "Errors": f"{stats.get('elements_that_changed', 0)}/{stats['array_length']} changed",
                        "Samples": f"{stats.get('iterations', '')} ({stats.get('pct_elements_changed', 0)}% active)",
                    })

        # Cycle Latency Probe results
        if "cycle_probe" in results:
            for key, stats in results["cycle_probe"].items():
                if stats.get("total_samples", 0) > 0:
                    label = key
                    if key == "_summary_":
                        label = f"{stats.get('vars_active', '?')}/{stats.get('num_vars', '?')} vars"
                    elif stats.get("array_length"):
                        label = f"{key} [{stats['array_length']}]"
                    rows.append({
                        "Test": "Cycle Probe",
                        "Variable": f"{label} ×{stats.get('reads_per_probe', stats.get('reads_per_var', '?'))}r",
                        "Min (ms)": stats["min_ms"],
                        "Avg (ms)": stats["avg_ms"],
                        "Max (ms)": stats["max_ms"],
                        "Median (ms)": stats["median_ms"],
                        "StdDev (ms)": stats["stddev_ms"],
                        "P95 (ms)": stats["p95_ms"],
                        "P99 (ms)": stats["p99_ms"],
                        "Errors": f"cycle={stats.get('plc_cycle_ms', '?')}ms",
                        "Samples": f"{stats['total_samples']} changes",
                    })

        if not rows:
            return

        headers = list(rows[0].keys())
        self.results_table.setColumnCount(len(headers))
        self.results_table.setHorizontalHeaderLabels(headers)
        self.results_table.setRowCount(len(rows))

        for r, row_data in enumerate(rows):
            for c, header in enumerate(headers):
                item = QTableWidgetItem(str(row_data.get(header, "")))
                item.setForeground(Qt.white)
                self.results_table.setItem(r, c, item)

        self.results_table.resizeColumnsToContents()

    def export_csv(self):
        if not self.last_results:
            QMessageBox.warning(self, "No Data", "Run a benchmark first.")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export Benchmark Results", 
            f"benchmark_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            "CSV Files (*.csv)"
        )
        if not file_path:
            return

        try:
            with open(file_path, "w", newline="") as f:
                # Write summary
                writer = csv.writer(f)
                writer.writerow(["OPC UA Performance Benchmark Results"])
                writer.writerow([f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"])
                writer.writerow([])

                # Write results table
                headers = []
                for c in range(self.results_table.columnCount()):
                    headers.append(self.results_table.horizontalHeaderItem(c).text())
                writer.writerow(headers)

                for r in range(self.results_table.rowCount()):
                    row = []
                    for c in range(self.results_table.columnCount()):
                        item = self.results_table.item(r, c)
                        row.append(item.text() if item else "")
                    writer.writerow(row)

                # Write raw latency data if available
                if "single_read" in self.last_results:
                    writer.writerow([])
                    writer.writerow(["Raw Single Read Latencies (ms)"])
                    for name, stats in self.last_results["single_read"].items():
                        writer.writerow([name] + stats.get("raw", []))

                if "batch_read" in self.last_results and "raw" in self.last_results["batch_read"]:
                    writer.writerow([])
                    writer.writerow(["Raw Batch Read Latencies (ms)"])
                    writer.writerow(["Batch"] + self.last_results["batch_read"]["raw"])

            QMessageBox.information(self, "Exported", f"Results saved to {file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Export failed: {e}")
