"""FastAPI backend — PLC Variable Monitor (binary protocol over TCP/UDP).

Supports multiple devices simultaneously via /api/devices/ endpoints.
The original /api/plc/ endpoints remain for backward compatibility
(they operate on the default "plc" device).
"""
import asyncio
import json
import os
import threading
import time
from pathlib import Path
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from web.plc_engine import PlcMonitorEngine
from web.device_manager import devices

app = FastAPI(title="PLC Variable Monitor")

# Register default device (backward compat: "plc")
registry_file = Path(__file__).parent.parent / "plc_var_registry.json"
devices.add("plc", registry_path=registry_file, label="Main PLC",
            description="Primary B&R PLC")
engine = devices.get("plc")  # shortcut for legacy /api/plc/ endpoints

# ── state ────────────────────────────────────────────────────────
ws_clients: list[WebSocket] = []
trace_active = False
trace_thread: threading.Thread | None = None

STATIC = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")


@app.get("/plc")
async def index():
    return FileResponse(str(STATIC / "plc_monitor.html"))


# ── broadcast to all websockets ──────────────────────────────────
async def broadcast(msg: dict):
    data = json.dumps(msg, default=str)
    dead = []
    for ws in ws_clients:
        try:
            await ws.send_text(data)
        except Exception:
            dead.append(ws)
    for ws in dead:
        ws_clients.remove(ws)


# ── models ───────────────────────────────────────────────────────
DEFAULT_PLC_IP = os.environ.get("PLC_IP", "127.0.0.1")

class ConnectRequest(BaseModel):
    ip: str = DEFAULT_PLC_IP
    transport: str = "tcp"  # "tcp" (default, firewall-friendly) or "udp"

class SubscribeRequest(BaseModel):
    var_names: list[str] = []
    var_ids: list[int] = []
    force: bool = False  # bypass the cycle-time-derived safety cap (testing only)

class IntervalRequest(BaseModel):
    interval_ms: int = 10

class TraceConfig(BaseModel):
    var_names: list[str]
    interval_ms: int = 50


# ── REST endpoints ───────────────────────────────────────────────
@app.post("/api/plc/connect")
async def connect(req: ConnectRequest):
    try:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, engine.connect, req.ip, req.transport)
    except Exception as e:
        return {"ok": False, "error": str(e)}


class DiscoverRequest(BaseModel):
    batch_size: int = 500
    batch_wait_s: float = 0.15

@app.post("/api/plc/discover")
async def discover(req: DiscoverRequest):
    """Probe the PLC to discover which variables actually exist in this config."""
    try:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, engine.discover_available, req.batch_size, req.batch_wait_s
        )
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.get("/api/plc/discovery_status")
async def discovery_status():
    return engine.get_discovery_status()


@app.post("/api/plc/disconnect")
async def disconnect():
    return engine.disconnect()


@app.get("/api/plc/status")
async def status():
    py_count = len(engine.registry)
    plc_count = engine.plc_registry_count
    health = engine.get_health()
    return {
        "connected": engine.connected,
        "ip": engine.plc_ip,
        "transport": "TCP" if engine.transport_mode == 0 else "UDP",
        "registry_size": py_count,
        "plc_registry_size": plc_count,
        "registry_in_sync": health["registry_in_sync"],
        "available_count": len(engine.available_vars),
        "discovery_done": engine._discovery_done,
        "subscribed": len(engine.subscribed),
        "health": health,
        "stats": engine.stats,
    }


@app.get("/api/plc/health")
async def health():
    return engine.get_health()


@app.get("/api/plc/browse")
async def browse(node_id: str = None):
    return engine.browse(node_id)


@app.get("/api/plc/search")
async def search(q: str = "", limit: int = 100):
    return engine.search(q, limit)


@app.get("/api/plc/defaults")
async def get_defaults(prefix: str = "gProtoTest"):
    prefixes = [p.strip() for p in prefix.split(",") if p.strip()]
    result = []
    for p in prefixes:
        result.extend(engine.get_default_vars(p))
    return result


@app.post("/api/plc/subscribe")
async def subscribe(req: SubscribeRequest):
    if req.var_names:
        return engine.subscribe(req.var_names, force=req.force)
    elif req.var_ids:
        return engine.subscribe_by_ids(req.var_ids, force=req.force)
    return {"ok": False, "error": "Provide var_names or var_ids"}


@app.get("/api/plc/limits")
async def plc_limits():
    """Return the current safe-subscription limit derived from the PLC cycle time."""
    return engine.get_subscription_limits()


class WriteVarRequest(BaseModel):
    var_name: str
    value: float | int | bool | str


@app.post("/api/plc/write")
async def write_var(req: WriteVarRequest):
    return engine.write_var(req.var_name, req.value)


@app.post("/api/plc/interval")
async def set_interval(req: IntervalRequest):
    return engine.set_interval(req.interval_ms)


@app.get("/api/plc/values")
async def get_values():
    return engine.get_all_values()


@app.get("/api/plc/detailed_stats")
async def detailed_stats():
    return engine.get_detailed_stats()


@app.get("/api/plc/profiler")
async def profiler():
    return engine.get_profiler_data()


@app.post("/api/plc/stats/reset")
async def reset_stats():
    engine.reset_stats()
    return {"ok": True}


class BenchmarkRequest(BaseModel):
    duration_s: float = 10.0


@app.post("/api/plc/benchmark/start")
async def benchmark_start(req: BenchmarkRequest):
    return engine.start_benchmark(req.duration_s)


@app.get("/api/plc/benchmark/status")
async def benchmark_status():
    return engine.get_benchmark_status()


class Benchmark2Request(BaseModel):
    duration_s: float = 10.0
    interval_ms: int = 1


@app.post("/api/plc/benchmark2/start")
async def benchmark2_start(req: Benchmark2Request):
    """Benchmark 2: subscribe ALL gProtoTest vars at fastest rate, then run benchmark."""
    # Collect all gProtoTest variable names
    all_gproto = [info["name"] for info in engine.registry.values()
                  if info.get("name", "").startswith("gProtoTest.")]
    if not all_gproto:
        return {"ok": False, "error": "No gProtoTest variables in registry"}

    # Subscribe to all of them
    sub_result = engine.subscribe(all_gproto)
    if not sub_result.get("ok"):
        return sub_result

    # Set fastest interval
    engine.set_interval(req.interval_ms)

    # Tell PLC to update ALL tiers every cycle (bypass MOD guards)
    engine.write_var("gProtoTest.Input.Commands.BenchAllFast", True)

    # Auto-clear BenchAllFast after benchmark duration
    def _clear_bench_flag():
        time.sleep(req.duration_s + 0.5)
        engine.write_var("gProtoTest.Input.Commands.BenchAllFast", False)
    threading.Thread(target=_clear_bench_flag, daemon=True).start()

    # Start the benchmark
    bench_result = engine.start_benchmark(req.duration_s)
    bench_result["subscribed"] = sub_result.get("subscribed", 0)
    bench_result["interval_ms"] = req.interval_ms
    return bench_result


class FullSubscribeTestRequest(BaseModel):
    duration_s: float = 10.0
    max_vars: int = 4500
    force: bool = False  # bypass the cycle-time-derived safety cap (testing only)


@app.post("/api/plc/fulltest/start")
async def fulltest_start(req: FullSubscribeTestRequest):
    """Subscribe to first N discovered variables, run benchmark for duration_s.

    Prefers vars from `engine.available_vars` (the set discovered to actually
    have a real PLC address) so that asking for, e.g., 50,000 subscriptions
    yields 50,000 *real* monitored vars rather than mostly phantom IDs whose
    pAddress is 0 and which the PLC silently skips during encoding.
    Falls back to the full registry only if discovery hasn't been run yet.
    """
    if not engine.connected:
        return {"ok": False, "error": "Not connected"}

    # Save current subscription
    pre_subs = set(engine.subscribed)

    # Pick candidates: prefer discovered/available vars (they have real
    # PLC addresses); otherwise fall back to the full registry.
    if engine._discovery_done and engine.available_vars:
        candidate_ids = sorted(engine.available_vars)
    else:
        candidate_ids = sorted(engine.registry.keys())
    cpu_ids = engine._get_cpu_var_ids()
    # CPU vars go first to ensure they're always included
    merged = sorted(set(cpu_ids) | set(candidate_ids))[:req.max_vars]

    # Cycle-time safety cap — refuse before we crash the PLC
    cap_err = engine._check_sub_size(len(merged), req.force)
    if cap_err is not None:
        return cap_err

    # Run everything in executor to avoid blocking the event loop
    loop = asyncio.get_event_loop()

    def _run():
        import time as _time

        # Subscribe to the test set.
        # Use the default chunk_size (5000) so 4500 fits in a single SET — that
        # way the PLC processes one command in one cycle and we avoid the
        # SET-then-ADD ACK race that triggers the cold-start instability.
        engine.subscribed = set(merged)
        engine._send_subscribe_chunked(merged)
        print(f"[FULLTEST] Subscribed to {len(merged)} vars, settling...")

        # Let PLC settle
        _time.sleep(2.0)

        # Reset stats before benchmark
        engine.reset_stats()

        # Start benchmark
        engine.start_benchmark(req.duration_s)
        print(f"[FULLTEST] Benchmark started for {req.duration_s}s")

        # Wait for benchmark to complete
        deadline = _time.perf_counter() + req.duration_s + 5.0
        while not engine._bench_done and _time.perf_counter() < deadline:
            _time.sleep(0.2)

        # Force finalize if timed out
        if not engine._bench_done and engine._bench_running:
            print("[FULLTEST] Benchmark timed out, force finalizing")
            engine._finalize_benchmark()

        result = engine._bench_result or {"error": "No packets received during test"}
        result["ok"] = True
        result["total_subscribed"] = len(merged)
        print(f"[FULLTEST] Benchmark done: {result.get('packet_rate', 0)} pkt/s")

        # Restore previous subscription
        if pre_subs:
            restore = sorted(pre_subs)
            engine.subscribed = set(restore)
            engine._send_subscribe_chunked(restore)
            print(f"[FULLTEST] Restored {len(restore)} previous subscriptions")
        else:
            engine._send_tcp_command(0x01, [])
            engine.subscribed = set()
            print("[FULLTEST] No previous subs to restore, cleared")

        _time.sleep(0.5)
        engine.reset_stats()

        return result

    result = await loop.run_in_executor(None, _run)
    return result


class StressTestRequest(BaseModel):
    levels: list[int] | None = None
    step_duration_s: float = 5.0
    settle_s: float = 1.0


@app.post("/api/plc/stress/start")
async def stress_start(req: StressTestRequest):
    """Start scaling stress test: progressively subscribe more vars."""
    if getattr(engine, '_stress_running', False):
        return {"ok": False, "error": "Stress test already running"}
    loop = asyncio.get_event_loop()

    def _run():
        return engine.run_stress_test(req.levels, req.step_duration_s, req.settle_s)

    result = await loop.run_in_executor(None, _run)
    return result


@app.get("/api/plc/stress/progress")
async def stress_progress():
    return engine.get_stress_progress()


# ── Churn ("Real Sim") test ─────────────────────────────────────
class ChurnTestRequest(BaseModel):
    duration_s: float = 300.0          # 5 minutes
    churn_size: int = 1000             # vars to swap each round
    churn_interval_s: float = 2.0      # how often to swap
    churn_pool_start: int = 10000      # start index in available_vars (skip the first N)
    baseline_prefix: str = "gProtoTest"  # always-on prefix
    force: bool = False                # bypass cycle-time safety cap


@app.post("/api/plc/churntest/start")
async def churntest_start(req: ChurnTestRequest):
    """Start a long-running real-world simulation test in a background thread.

    Returns immediately (test runs for duration_s). Poll /api/plc/churntest/status
    for live progress and the final result.
    """
    if not engine.connected:
        return {"ok": False, "error": "Not connected"}
    if getattr(engine, "_churn_running", False):
        return {"ok": False, "error": "Churn test already running"}

    def _run():
        try:
            engine.run_churn_test(
                duration_s=req.duration_s,
                churn_size=req.churn_size,
                churn_interval_s=req.churn_interval_s,
                churn_pool_start=req.churn_pool_start,
                baseline_prefix=req.baseline_prefix,
                force=req.force,
            )
        except Exception as e:
            engine._churn_running = False
            engine._churn_done = True
            engine._churn_result = {"ok": False, "error": f"Churn test crashed: {e}"}

    threading.Thread(target=_run, daemon=True).start()

    return {
        "ok": True,
        "started": True,
        "duration_s": req.duration_s,
        "churn_size": req.churn_size,
        "churn_interval_s": req.churn_interval_s,
        "churn_pool_start": req.churn_pool_start,
    }


@app.get("/api/plc/churntest/status")
async def churntest_status():
    return engine.get_churn_status()


@app.post("/api/plc/churntest/stop")
async def churntest_stop():
    return engine.stop_churn_test()


@app.post("/api/plc/trace/start")
async def trace_start(config: TraceConfig):
    global trace_active, trace_thread

    if trace_active:
        return {"ok": False, "error": "Trace already running"}

    # Subscribe to these variables
    result = engine.subscribe(config.var_names)

    # Set interval
    engine.set_interval(config.interval_ms)

    trace_active = True
    loop = asyncio.get_event_loop()

    def on_update(timestamp_ms, values):
        if trace_active:
            asyncio.run_coroutine_threadsafe(
                broadcast({
                    "type": "trace",
                    "ts": timestamp_ms,
                    "values": values,
                }),
                loop,
            )

    engine.set_on_update(on_update)
    return {"ok": True, "subscribed": result.get("subscribed", 0)}


@app.post("/api/plc/trace/stop")
async def trace_stop():
    global trace_active
    trace_active = False
    engine.set_on_update(None)
    return {"ok": True}


# ── WebSocket ────────────────────────────────────────────────────
@app.websocket("/ws/plc")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    ws_clients.append(ws)
    try:
        while True:
            data = await ws.receive_text()
            msg = json.loads(data)
            if msg.get("type") == "ping":
                await ws.send_text(json.dumps({"type": "pong"}))
    except WebSocketDisconnect:
        pass
    finally:
        if ws in ws_clients:
            ws_clients.remove(ws)


@app.websocket("/ws/device/{device_id}")
async def ws_device_endpoint(ws: WebSocket, device_id: str):
    """Per-device WebSocket for live variable updates."""
    eng = devices.get(device_id)
    if not eng:
        await ws.close(code=4004, reason=f"Device '{device_id}' not found")
        return
    await ws.accept()
    ws_clients.append(ws)
    try:
        while True:
            data = await ws.receive_text()
            msg = json.loads(data)
            if msg.get("type") == "ping":
                await ws.send_text(json.dumps({"type": "pong"}))
    except WebSocketDisconnect:
        pass
    finally:
        if ws in ws_clients:
            ws_clients.remove(ws)


# ══════════════════════════════════════════════════════════════════
# MULTI-DEVICE API — /api/devices/
#
# Allows connecting to multiple PLCs / embedded carts / other devices
# simultaneously. Each device has its own engine, registry, and state.
# ══════════════════════════════════════════════════════════════════

class AddDeviceRequest(BaseModel):
    device_id: str                  # Unique slug (e.g. "cart_1", "press_plc")
    label: str = ""                 # Human name (e.g. "Embedded Cart #1")
    description: str = ""
    registry_path: str = ""         # Path to registry JSON (optional)


class DeviceConnectRequest(BaseModel):
    ip: str
    transport: str = "tcp"


class DeviceSubscribeRequest(BaseModel):
    var_names: list[str] = []
    var_ids: list[int] = []
    force: bool = False


class DeviceWriteRequest(BaseModel):
    var_name: str
    value: float | int | bool | str


@app.get("/api/devices")
async def list_devices():
    """List all registered devices and their connection status."""
    return {"devices": devices.list_all()}


@app.post("/api/devices/add")
async def add_device(req: AddDeviceRequest):
    """Register a new device."""
    reg_path = Path(req.registry_path) if req.registry_path else None
    return devices.add(req.device_id, registry_path=reg_path,
                       label=req.label, description=req.description)


@app.post("/api/devices/{device_id}/remove")
async def remove_device(device_id: str):
    """Remove a device (disconnects first)."""
    return devices.remove(device_id)


@app.post("/api/devices/{device_id}/connect")
async def device_connect(device_id: str, req: DeviceConnectRequest):
    """Connect a specific device to its PLC/target."""
    eng, err = devices.get_or_error(device_id)
    if err:
        return err
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, eng.connect, req.ip, req.transport)


@app.post("/api/devices/{device_id}/disconnect")
async def device_disconnect(device_id: str):
    """Disconnect a specific device."""
    eng, err = devices.get_or_error(device_id)
    if err:
        return err
    return eng.disconnect()


@app.get("/api/devices/{device_id}/status")
async def device_status(device_id: str):
    """Get status of a specific device."""
    eng, err = devices.get_or_error(device_id)
    if err:
        return err
    health = eng.get_health()
    return {
        "device_id": device_id,
        "connected": eng.connected,
        "ip": eng.plc_ip,
        "transport": "TCP" if eng.transport_mode == 0 else "UDP",
        "registry_size": len(eng.registry),
        "subscribed": len(eng.subscribed),
        "health": health,
        "stats": eng.stats,
    }


@app.post("/api/devices/{device_id}/subscribe")
async def device_subscribe(device_id: str, req: DeviceSubscribeRequest):
    """Subscribe to variables on a specific device."""
    eng, err = devices.get_or_error(device_id)
    if err:
        return err
    if req.var_names:
        return eng.subscribe(req.var_names, force=req.force)
    elif req.var_ids:
        return eng.subscribe_by_ids(req.var_ids, force=req.force)
    return {"ok": False, "error": "Provide var_names or var_ids"}


@app.get("/api/devices/{device_id}/values")
async def device_values(device_id: str):
    """Get all current values from a specific device."""
    eng, err = devices.get_or_error(device_id)
    if err:
        return err
    return eng.get_all_values()


@app.get("/api/devices/{device_id}/browse")
async def device_browse(device_id: str, node_id: str = None):
    """Browse variable tree on a specific device."""
    eng, err = devices.get_or_error(device_id)
    if err:
        return err
    return eng.browse(node_id)


@app.get("/api/devices/{device_id}/search")
async def device_search(device_id: str, q: str = "", limit: int = 100):
    """Search variables on a specific device."""
    eng, err = devices.get_or_error(device_id)
    if err:
        return err
    return eng.search(q, limit)


@app.post("/api/devices/{device_id}/write")
async def device_write(device_id: str, req: DeviceWriteRequest):
    """Write a variable on a specific device."""
    eng, err = devices.get_or_error(device_id)
    if err:
        return err
    return eng.write_var(req.var_name, req.value)


@app.get("/api/devices/{device_id}/stats")
async def device_stats(device_id: str):
    """Get detailed stats for a specific device."""
    eng, err = devices.get_or_error(device_id)
    if err:
        return err
    return eng.get_detailed_stats()
