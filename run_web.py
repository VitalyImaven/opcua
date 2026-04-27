"""Launch the Protocol Test Suite web app."""
import uvicorn
import webbrowser
import threading

def open_browser():
    import time
    time.sleep(1.5)
    webbrowser.open("http://127.0.0.1:8080")

if __name__ == "__main__":
    threading.Thread(target=open_browser, daemon=True).start()
    print("Starting Protocol Test Suite at http://127.0.0.1:8080")
    uvicorn.run("web.app:app", host="127.0.0.1", port=8080, reload=False, log_level="info")
