"""Launcher for PLC Monitor web UI."""
import uvicorn

if __name__ == "__main__":
    uvicorn.run("web.plc_app:app", host="0.0.0.0", port=8082, reload=False)
