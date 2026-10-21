"""PC-side client for the MaixCAM Bluetooth control endpoint."""

import json
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class CameraBluetoothClient:
    def __init__(self, host, open_url=urlopen):
        self.base = f"http://{host}:8765/bluetooth"
        self.open_url = open_url

    def request(self, action, mac=None):
        if action not in ("status", "clock", "scan", "select"):
            raise ValueError("unsupported Bluetooth action")
        body = json.dumps({"mac": mac}).encode() if action == "select" else None
        method = "GET" if action in ("status", "clock") else "POST"
        request = Request(self.base + "/" + action, data=body, method=method,
                          headers={"Content-Type": "application/json"})
        try:
            timeout = 25 if action == "scan" else 60 if action == "select" else 5
            with self.open_url(request, timeout=timeout) as response:
                return response.status, json.load(response)
        except HTTPError as error:
            try:
                return error.code, json.load(error)
            except (ValueError, OSError):
                return error.code, {"error": "camera rejected Bluetooth request"}
        except (OSError, URLError) as error:
            return 503, {"error": f"camera Bluetooth service unavailable: {error}"}

    def talkback_clock(self):
        """Anchor packet timestamps to the receiver clock for this talk session."""
        started = time.monotonic()
        code, body = self.request("clock")
        finished = time.monotonic()
        if code == 404 or (code == 200 and body.get("talkback_protocol") != "TB3"):
            raise RuntimeError("Incompatible talkback protocol; update PC and camera together to TB3")
        remote = body.get("time_ms")
        if (code != 200 or type(remote) is not int or remote <= 0
                or finished - started > 1):
            raise RuntimeError("Camera clock unavailable; release and retry")
        midpoint = (started + finished) / 2
        # Monotonic time avoids jumps if Windows later synchronizes its clock.
        return lambda: int(remote + (time.monotonic() - midpoint) * 1000)
