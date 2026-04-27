"""FastAPI backend — OPC UA Subscription Monitor."""
import asyncio
import json
import threading
from pathlib import Path
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from web.opcua_sub_engine import OpcuaSubEngine

app = FastAPI(title="OPC UA Subscription Monitor")
engine = OpcuaSubEngine()

ws_clients: list[WebSocket] = []
trace_active = False

STATIC = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")


@app.get("/opcua")
async def index():
    return FileResponse(str(STATIC / "opcua_monitor.html"))


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
class ConnectRequest(BaseModel):
    url: str = "opc.tcp://192.168.101.10:4840"


class SubscribeRequest(BaseModel):
    node_ids: list[str] = []
    var_names: list[str] = []
    interval_ms: int = 50


class BenchmarkRequest(BaseModel):
    duration_s: float = 10.0


# ── REST endpoints ───────────────────────────────────────────────
@app.post("/api/opcua/connect")
async def connect(req: ConnectRequest):
    try:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, engine.connect, req.url)
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.post("/api/opcua/disconnect")
async def disconnect():
    return engine.disconnect()


@app.get("/api/opcua/status")
async def status():
    return {
        "connected": engine.connected,
        "url": engine.url,
        "subscribed": len(engine.subscribed),
        "stats": engine.stats,
    }


@app.get("/api/opcua/discover")
async def discover(source: str = "browse"):
    """Discover gProtoTest variables. source=browse or source=registry."""
    loop = asyncio.get_event_loop()
    if source == "registry":
        return await loop.run_in_executor(None, engine.discover_from_registry)
    return await loop.run_in_executor(None, engine.discover_gprototest)


@app.post("/api/opcua/subscribe")
async def subscribe(req: SubscribeRequest):
    if not req.node_ids and not req.var_names:
        return {"ok": False, "error": "Provide node_ids + var_names"}
    return engine.subscribe(req.node_ids, req.var_names, req.interval_ms)


@app.get("/api/opcua/values")
async def get_values():
    return engine.get_all_values()


@app.get("/api/opcua/detailed_stats")
async def detailed_stats():
    return engine.get_detailed_stats()


@app.post("/api/opcua/stats/reset")
async def reset_stats():
    engine.reset_stats()
    return {"ok": True}


@app.post("/api/opcua/benchmark/start")
async def benchmark_start(req: BenchmarkRequest):
    return engine.start_benchmark(req.duration_s)


@app.get("/api/opcua/benchmark/status")
async def benchmark_status():
    return engine.get_benchmark_status()


@app.get("/api/opcua/defaults")
async def get_defaults():
    """Return gProtoTest node_ids from browse or registry."""
    loop = asyncio.get_event_loop()
    # Try browse first
    vars_list = await loop.run_in_executor(None, engine.discover_gprototest)
    if not vars_list:
        vars_list = await loop.run_in_executor(None, engine.discover_from_registry)
    return {
        "vars": vars_list,
        "count": len(vars_list),
        "source": "browse" if vars_list else "registry",
    }


# ── Trace with WebSocket ────────────────────────────────────────
@app.post("/api/opcua/trace/start")
async def trace_start():
    global trace_active
    if trace_active:
        return {"ok": False, "error": "Trace already running"}

    trace_active = True
    loop = asyncio.get_event_loop()

    def on_update(var_name, value):
        if trace_active:
            asyncio.run_coroutine_threadsafe(
                broadcast({"type": "trace", "name": var_name, "value": value}),
                loop,
            )

    engine.set_on_update(on_update)
    return {"ok": True}


@app.post("/api/opcua/trace/stop")
async def trace_stop():
    global trace_active
    trace_active = False
    engine.set_on_update(None)
    return {"ok": True}


# ── WebSocket ────────────────────────────────────────────────────
@app.websocket("/ws/opcua")
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
