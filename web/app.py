"""FastAPI backend — REST + WebSocket for real-time updates."""
import asyncio
import json
import threading
import time
from pathlib import Path
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from web.opcua_engine import OpcuaEngine
from web.pvi_engine import PviEngine

app = FastAPI(title="Protocol Test Suite")
engine = OpcuaEngine()
pvi_engine = PviEngine()

# ── state ────────────────────────────────────────────────────────
ws_clients: list[WebSocket] = []
trace_active = False
trace_thread: threading.Thread | None = None
trace_nodes: list[dict] = []  # [{name, node_id}]
trace_interval_ms = 100
benchmark_stop = False
benchmark_running = False
pvi_monitor_running = False
pvi_monitor_stop = False

STATIC = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")


@app.get("/")
async def index():
    return FileResponse(str(STATIC / "index.html"))


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


def sync_broadcast(msg: dict):
    """Call broadcast from a sync thread."""
    loop = asyncio.new_event_loop()
    # We'll queue to the main loop instead
    pass  # handled differently — see below


# ── models ───────────────────────────────────────────────────────
class ConnectRequest(BaseModel):
    url: str = "opc.tcp://192.168.101.10:4840"

class BenchmarkConfig(BaseModel):
    node_ids: list[str]
    var_names: list[str]
    iterations: int = 100
    throughput_duration: int = 5
    detection_duration: int = 10
    plc_cycle_ms: float = 1.6
    cycle_probe_reads: int = 200
    single_read: bool = True
    batch_read: bool = True
    throughput: bool = True
    write_latency: bool = False
    round_trip: bool = False
    detection: bool = True
    cycle_probe: bool = True
    multi_rate: bool = False
    multi_rate_batch: int = 50
    multi_rate_duration: int = 10
    subscription: bool = False
    sub_duration: int = 10
    sub_interval_ms: int = 10
    sub_batch: int = 50
    sub_monitor: bool = False
    sub_monitor_duration: int = 10
    sub_monitor_interval: int = 10

class TraceConfig(BaseModel):
    nodes: list[dict]  # [{name, node_id}]
    interval_ms: int = 100

class PviConnectRequest(BaseModel):
    ip: str = "192.168.101.10"

class PviMonitorConfig(BaseModel):
    var_configs: list[dict]  # [{name: str, refresh_ms: int}]
    duration: int = 10
    plc_cycle_ms: float = 1.6


# ── REST endpoints ───────────────────────────────────────────────
@app.post("/api/connect")
async def connect(req: ConnectRequest):
    try:
        return engine.connect(req.url)
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.post("/api/disconnect")
async def disconnect():
    return engine.disconnect()


@app.get("/api/status")
async def status():
    return {"connected": engine.connected, "url": engine.url}


@app.get("/api/browse")
async def browse(node_id: str = None):
    return engine.browse(node_id)


@app.get("/api/discover")
async def discover():
    return engine.discover_opctest()


@app.post("/api/benchmark/start")
async def benchmark_start(config: BenchmarkConfig):
    global benchmark_running, benchmark_stop
    if benchmark_running:
        return {"ok": False, "error": "Benchmark already running"}
    benchmark_stop = False
    benchmark_running = True

    loop = asyncio.get_event_loop()

    def _run():
        global benchmark_running, benchmark_stop
        try:
            def log(msg):
                asyncio.run_coroutine_threadsafe(
                    broadcast({"type": "log", "msg": msg}), loop)

            def prog(pct):
                asyncio.run_coroutine_threadsafe(
                    broadcast({"type": "progress", "pct": pct}), loop)

            results = engine.run_benchmarks(
                config.model_dump(), log, prog, lambda: benchmark_stop)
            asyncio.run_coroutine_threadsafe(
                broadcast({"type": "benchmark_done", "results": results}), loop)
        except Exception as e:
            asyncio.run_coroutine_threadsafe(
                broadcast({"type": "error", "msg": str(e)}), loop)
        finally:
            benchmark_running = False

    threading.Thread(target=_run, daemon=True).start()
    return {"ok": True}


@app.post("/api/benchmark/stop")
async def benchmark_stop_api():
    global benchmark_stop
    benchmark_stop = True
    return {"ok": True}


@app.post("/api/trace/start")
async def trace_start(config: TraceConfig):
    global trace_active, trace_thread, trace_nodes, trace_interval_ms
    trace_active = True
    trace_nodes = config.nodes
    trace_interval_ms = config.interval_ms
    loop = asyncio.get_event_loop()

    def _trace():
        while trace_active:
            nids = [n["node_id"] for n in trace_nodes]
            vals = engine.trace_read(nids)
            ts = time.time() * 1000
            data = {"type": "trace", "ts": ts, "values": {}}
            for n in trace_nodes:
                data["values"][n["name"]] = vals.get(n["node_id"])
            asyncio.run_coroutine_threadsafe(broadcast(data), loop)
            time.sleep(trace_interval_ms / 1000)

    trace_thread = threading.Thread(target=_trace, daemon=True)
    trace_thread.start()
    return {"ok": True}


@app.post("/api/trace/stop")
async def trace_stop():
    global trace_active
    trace_active = False
    return {"ok": True}


@app.post("/api/read")
async def read_values(node_ids: list[str]):
    try:
        return {"values": engine.read_values(node_ids)}
    except Exception as e:
        return {"error": str(e)}


# ── PVI endpoints ────────────────────────────────────────────────
@app.post("/api/pvi/connect")
async def pvi_connect(req: PviConnectRequest):
    try:
        return pvi_engine.connect(req.ip)
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.post("/api/pvi/disconnect")
async def pvi_disconnect():
    return pvi_engine.disconnect()


@app.get("/api/pvi/status")
async def pvi_status():
    return {"connected": pvi_engine.connected, "ip": pvi_engine.ip}


@app.get("/api/pvi/tasks")
async def pvi_tasks():
    return pvi_engine.list_tasks()


@app.get("/api/pvi/variables")
async def pvi_variables():
    return pvi_engine.list_global_vars()


@app.post("/api/pvi/monitor/start")
async def pvi_monitor_start(config: PviMonitorConfig):
    global pvi_monitor_running, pvi_monitor_stop
    if pvi_monitor_running:
        return {"ok": False, "error": "PVI monitor already running"}
    if not pvi_engine.connected:
        return {"ok": False, "error": "PVI not connected"}
    pvi_monitor_stop = False
    pvi_monitor_running = True

    loop = asyncio.get_event_loop()

    def _run():
        global pvi_monitor_running, pvi_monitor_stop
        try:
            def log(msg):
                asyncio.run_coroutine_threadsafe(
                    broadcast({"type": "log", "msg": msg}), loop)

            def prog(pct):
                asyncio.run_coroutine_threadsafe(
                    broadcast({"type": "progress", "pct": pct}), loop)

            results = pvi_engine.run_pvi_monitor(
                config.var_configs, config.duration, config.plc_cycle_ms,
                log, prog, lambda: pvi_monitor_stop)
            asyncio.run_coroutine_threadsafe(
                broadcast({"type": "pvi_monitor_done", "results": results}), loop)
        except Exception as e:
            asyncio.run_coroutine_threadsafe(
                broadcast({"type": "error", "msg": f"PVI monitor error: {e}"}), loop)
        finally:
            pvi_monitor_running = False

    threading.Thread(target=_run, daemon=True).start()
    return {"ok": True}


@app.post("/api/pvi/monitor/stop")
async def pvi_monitor_stop_api():
    global pvi_monitor_stop
    pvi_monitor_stop = True
    return {"ok": True}


# ── WebSocket for real-time push ─────────────────────────────────
@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    ws_clients.append(ws)
    try:
        while True:
            # keep-alive; client can send commands too
            data = await ws.receive_text()
            msg = json.loads(data)
            if msg.get("type") == "ping":
                await ws.send_text(json.dumps({"type": "pong"}))
    except WebSocketDisconnect:
        if ws in ws_clients:
            ws_clients.remove(ws)
