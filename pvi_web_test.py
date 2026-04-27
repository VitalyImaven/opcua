"""Quick test: start PVI monitor via API and listen for results via WebSocket."""
import asyncio
import json
import requests
import websockets


async def main():
    # Connect PVI first
    r = requests.post("http://127.0.0.1:8080/api/pvi/connect", json={"ip": "192.168.101.10"})
    print("Connect:", r.json())
    if not r.json().get("ok"):
        return

    async with websockets.connect("ws://127.0.0.1:8080/ws") as ws:
        # Start a test: 200 vars with varied RF for 10s
        var_configs = []
        for i in range(1, 11):
            var_configs.append({"name": f"opctest{i}", "refresh_ms": 2})
        for i in range(11, 21):
            var_configs.append({"name": f"opctest{i}", "refresh_ms": 5})
        for i in range(21, 31):
            var_configs.append({"name": f"opctest{i}", "refresh_ms": 10})
        for i in range(31, 201):
            var_configs.append({"name": f"opctest{i}", "refresh_ms": 50})
        cfg = {
            "var_configs": var_configs,
            "duration": 10,
            "plc_cycle_ms": 1.6,
        }
        r = requests.post("http://127.0.0.1:8080/api/pvi/monitor/start", json=cfg)
        print("Started:", r.json())

        # Listen for results
        while True:
            msg = await asyncio.wait_for(ws.recv(), timeout=30)
            data = json.loads(msg)
            if data.get("type") == "log":
                print(data["msg"])
            elif data.get("type") == "pvi_monitor_done":
                results = data["results"]
                summary = results.get("_summary", {})
                print()
                print(f"Total notifications: {summary.get('total_notifications')}")
                print(f"Total changes: {summary.get('total_changes')}")
                print(f"Total missed: {summary.get('total_missed')}")
                print(f"Detection: {summary.get('detect_pct')}%")
                for t in summary.get("tiers", []):
                    print(
                        f"  {t['label']}: {t['notifications']} notifs, "
                        f"{t['detect_pct']}% detect, {t['verdict']}"
                    )
                print()
                for k, v in sorted(results.items()):
                    if k.startswith("opctest"):
                        print(
                            f"  {k}: notifs={v['notifications']}, "
                            f"changes={v['changes']}, missed={v['missed']}, "
                            f"avg_gap={v['avg_gap_ms']}ms"
                        )
                break
            elif data.get("type") == "error":
                print("ERROR:", data["msg"])
                break
            elif data.get("type") == "progress":
                pass  # ignore progress


asyncio.run(main())
