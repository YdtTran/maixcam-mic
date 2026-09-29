"""PC-side client for the MaixCAM Bluetooth control endpoint."""

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class CameraBluetoothClient:
    def __init__(self, host, token, open_url=urlopen):
        self.base = f"http://{host}:8765/bluetooth"
        self.token = token
        self.open_url = open_url

    def request(self, action, mac=None):
        if action not in ("status", "scan", "select"):
            raise ValueError("unsupported Bluetooth action")
        body = json.dumps({"mac": mac}).encode() if action == "select" else None
        method = "GET" if action == "status" else "POST"
        request = Request(self.base + "/" + action, data=body, method=method,
                          headers={"X-Control-Token": self.token,
                                   "Content-Type": "application/json"})
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
