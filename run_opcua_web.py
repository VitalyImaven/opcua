"""Launcher for OPC UA Subscription Monitor web UI."""
import uvicorn

if __name__ == "__main__":
    uvicorn.run("web.opcua_sub_app:app", host="0.0.0.0", port=8083, reload=False)
