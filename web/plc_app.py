"""FastAPI backend — PLC Variable Monitor (binary protocol over TCP/UDP)."""
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

app = FastAPI(title="PLC Variable Monitor")
engine = PlcMonitorEngine()

# Load variable registry at startup
registry_file = Path(__file__).parent.parent / "plc_var_registry.json"
if registry_file.exists():
    engine.load_registry(registry_file)

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

class SubscribeRequest(BaseModel):
    var_names: list[str] = []
    var_ids: list[int] = []

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
        return await loop.run_in_executor(None, engine.connect, req.ip)
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
    return {
        "connected": engine.connected,
        "ip": engine.plc_ip,
        "registry_size": len(engine.registry),
        "available_count": len(engine.available_vars),
        "discovery_done": engine._discovery_done,
        "subscribed": len(engine.subscribed),
        "stats": engine.stats,
    }


@app.get("/api/plc/browse")
async def browse(node_id: str = None):
    return engine.browse(node_id)


@app.get("/api/plc/search")
async def search(q: str = "", limit: int = 100):
    return engine.search(q, limit)


@app.get("/api/plc/defaults")
async def get_defaults(prefix: str = "gProtoTest"):
    return engine.get_default_vars(prefix)


@app.post("/api/plc/subscribe")
async def subscribe(req: SubscribeRequest):
    if req.var_names:
        return engine.subscribe(req.var_names)
    elif req.var_ids:
        return engine.subscribe_by_ids(req.var_ids)
    return {"ok": False, "error": "Provide var_names or var_ids"}


@app.post("/api/plc/interval")
async def set_interval(req: IntervalRequest):
    return engine.set_interval(req.interval_ms)


@app.get("/api/plc/values")
async def get_values():
    return engine.get_all_values()


@app.get("/api/plc/detailed_stats")
async def detailed_stats():
    return engine.get_detailed_stats()


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
