"""
Device Manager — Multi-device connection support.

Manages multiple PlcMonitorEngine instances, each identified by a
device_id (slug). Allows the web app to connect to multiple PLCs,
embedded carts, or other devices simultaneously.

Usage:
    from web.device_manager import devices

    # Register a new device
    devices.add("plc_main", registry_path="plc_var_registry.json")
    devices.add("cart_embedded", registry_path="cart_registry.json")

    # Get a device engine
    engine = devices.get("plc_main")
    engine.connect("192.168.101.10")

    # List all devices
    devices.list_all()  # [{"id": "plc_main", "connected": True, ...}]
"""

import json
import threading
from pathlib import Path
from typing import Optional

from web.plc_engine import PlcMonitorEngine


class DeviceManager:
    """Manages multiple PlcMonitorEngine instances for multi-device support.

    Each device has:
    - A unique string ID (e.g. "plc_main", "cart_1", "press_2")
    - Its own PlcMonitorEngine instance
    - Its own variable registry (JSON file)
    - Independent connection, subscription, and stats

    Thread-safe: all operations use a lock.
    """

    def __init__(self):
        self._devices: dict[str, dict] = {}
        self._lock = threading.Lock()

    def add(self, device_id: str, registry_path: str | Path | None = None,
            label: str = "", description: str = "") -> dict:
        """Register a new device.

        Args:
            device_id: Unique identifier (slug, no spaces).
            registry_path: Path to plc_var_registry.json for this device.
            label: Human-friendly name (e.g. "Main PLC", "Embedded Cart").
            description: Optional description.

        Returns:
            {"ok": True} or {"ok": False, "error": "..."}.
        """
        with self._lock:
            if device_id in self._devices:
                return {"ok": False, "error": f"Device '{device_id}' already exists"}

            engine = PlcMonitorEngine()

            if registry_path:
                p = Path(registry_path)
                if p.exists():
                    engine.load_registry(p)

            self._devices[device_id] = {
                "engine": engine,
                "label": label or device_id,
                "description": description,
                "registry_path": str(registry_path) if registry_path else None,
            }
            return {"ok": True, "device_id": device_id}

    def remove(self, device_id: str) -> dict:
        """Remove a device and disconnect if connected."""
        with self._lock:
            if device_id not in self._devices:
                return {"ok": False, "error": f"Device '{device_id}' not found"}
            entry = self._devices.pop(device_id)
            entry["engine"].disconnect()
            return {"ok": True}

    def get(self, device_id: str) -> Optional[PlcMonitorEngine]:
        """Get the engine for a device. Returns None if not found."""
        entry = self._devices.get(device_id)
        return entry["engine"] if entry else None

    def get_or_error(self, device_id: str) -> tuple[Optional[PlcMonitorEngine], Optional[dict]]:
        """Get engine or return error dict. For use in API endpoints."""
        engine = self.get(device_id)
        if engine is None:
            return None, {"ok": False, "error": f"Device '{device_id}' not found"}
        return engine, None

    def list_all(self) -> list[dict]:
        """Return status of all registered devices."""
        result = []
        for dev_id, entry in self._devices.items():
            eng = entry["engine"]
            result.append({
                "id": dev_id,
                "label": entry["label"],
                "description": entry["description"],
                "connected": eng.connected,
                "ip": eng.plc_ip if eng.connected else None,
                "transport": "TCP" if eng.transport_mode == 0 else "UDP",
                "registry_size": len(eng.registry),
                "subscribed": len(eng.subscribed),
                "available_count": len(eng.available_vars),
                "packets_received": eng.stats.get("packets_received", 0),
            })
        return result

    def __contains__(self, device_id: str) -> bool:
        return device_id in self._devices

    def __len__(self) -> int:
        return len(self._devices)


# Singleton instance used by the app
devices = DeviceManager()
