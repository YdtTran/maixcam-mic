"""Bluetooth headset status and fixed-device binding on MaixCAM."""

import json
import os
import re
import subprocess
import tempfile
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


SELECTION_PATH = Path("/root/.bluetooth_device")
MAC = re.compile(r"(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}")


def read_capture_volume(selection_path=SELECTION_PATH):
    try:
        value = int(Path(selection_path).with_suffix(".capture-volume").read_text())
    except FileNotFoundError:
        return 100
    if not 0 <= value <= 100:
        raise ValueError("invalid saved microphone volume")
    return value


def parse_devices(output):
    devices = {}
    for line in output.splitlines():
        match = re.match(r"^Device (" + MAC.pattern + r")\s+(.+)$", line.strip())
        if match:
            devices[match.group(1).upper()] = match.group(2).strip()
    return [{"mac": mac, "name": name} for mac, name in devices.items()]


def parse_scan_devices(output):
    clean = re.sub(r"\x1b\[[0-9;]*m|[\x01\x02]", "", output)
    devices = {}
    for line in clean.splitlines():
        match = re.search(r"\[(?:NEW|CHG)\]\s+Device (" + MAC.pattern + r")\s+(.+)$", line)
        if match and not re.match(r"(?:RSSI|UUIDs|ManufacturerData|ServicesResolved|TxPower):", match.group(2)):
            devices[match.group(1).upper()] = match.group(2).strip()
    return [{"mac": mac, "name": name} for mac, name in devices.items()]


def run_command(command, timeout=20):
    try:
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, timeout=timeout)
        return result.returncode, result.stdout or ""
    except (OSError, subprocess.TimeoutExpired) as error:
        return 1, str(error)


class BluetoothControl:
    def __init__(self, selection_path=SELECTION_PATH, run=run_command, connect=None, fixed_mac=None):
        self.selection_path = Path(selection_path)
        self.run = run
        self.connect = connect
        self._scanned_devices = []
        if fixed_mac is not None and not MAC.fullmatch(fixed_mac):
            raise ValueError("invalid fixed Bluetooth address")
        self.fixed_mac = fixed_mac.upper() if fixed_mac else None
        if self.fixed_mac:
            temporary = self.selection_path.with_suffix(".tmp")
            temporary.write_text(self.fixed_mac + "\n")
            os.replace(temporary, self.selection_path)

    def selected(self):
        try:
            mac = self.selection_path.read_text().strip().upper()
        except FileNotFoundError:
            return None
        return mac if MAC.fullmatch(mac) else None

    def devices(self):
        code, output = self.run(["bluetoothctl", "devices"])
        if code:
            raise RuntimeError("Could not list Bluetooth devices: " + output.strip())
        return parse_devices(output)

    def scan(self):
        if self.fixed_mac:
            return [device for device in self.devices() if device["mac"] == self.fixed_mac]
        code, output = self.run(["bluetoothctl", "power", "on"])
        if code:
            raise RuntimeError("Could not power on Bluetooth: " + output.strip())
        try:
            code, output = self.run(["bluetoothctl", "--timeout", "15", "scan", "on"], timeout=20)
            if code:
                raise RuntimeError("Bluetooth scan failed: " + output.strip())
        finally:
            self.run(["bluetoothctl", "scan", "off"])
        devices = {device["mac"]: device for device in parse_scan_devices(output)}
        devices.update({device["mac"]: device for device in self.devices()})
        self._scanned_devices = list(devices.values())
        return self._scanned_devices

    def select(self, mac):
        if not isinstance(mac, str) or not MAC.fullmatch(mac):
            raise ValueError("invalid Bluetooth address")
        mac = mac.upper()
        if self.fixed_mac:
            if mac != self.fixed_mac:
                raise ValueError("MaixCAM is bound to a fixed headset")
            return self.status()
        if mac not in {item["mac"] for item in self._scanned_devices}:
            raise ValueError("device is not in the discovered list; scan again")
        if self.connect is not None and not self.connect(mac):
            raise RuntimeError("Could not connect. Put the device in pairing mode and try again.")
        temporary = self.selection_path.with_suffix(".tmp")
        temporary.write_text(mac + "\n")
        os.replace(temporary, self.selection_path)
        return self.status()

    def status(self):
        mac = self.selected()
        if not mac:
            return {"selected": None, "connected": False, "fixed": bool(self.fixed_mac)}
        code, output = self.run(["bluetoothctl", "info", mac])
        return {"selected": mac, "connected": code == 0 and "Connected: yes" in output,
                "fixed": bool(self.fixed_mac)}

    def capture_volume(self, value=None):
        if value is not None and (type(value) is not int or not 0 <= value <= 100):
            raise ValueError("volume must be an integer from 0 to 100")
        if not self.selected():
            raise RuntimeError("Connect the camera earbuds before adjusting microphone volume")
        if value is not None:
            path = self.selection_path.with_suffix(".capture-volume")
            with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as temporary:
                temporary.write(str(value))
            try:
                os.replace(temporary.name, path)
            finally:
                Path(temporary.name).unlink(missing_ok=True)
        return {"volume": read_capture_volume(self.selection_path)}


def make_handler(control):
    class Handler(BaseHTTPRequestHandler):
        def _json(self, code, value):
            data = json.dumps({**value, "talkback_protocol": "TB3"}).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path == "/bluetooth/clock":
                return self._json(200, {"time_ms": int(time.time() * 1000)})
            if self.path == "/bluetooth/status":
                return self._json(200, control.status())
            if self.path == "/bluetooth/capture-volume":
                try:
                    return self._json(200, control.capture_volume())
                except (OSError, RuntimeError, ValueError) as error:
                    return self._json(503, {"error": str(error)})
            self._json(404, {"error": "not found"})

        def do_POST(self):
            try:
                if self.path == "/bluetooth/scan":
                    return self._json(200, {"devices": control.scan(), **control.status()})
                if self.path in ("/bluetooth/select", "/bluetooth/capture-volume"):
                    size = int(self.headers.get("Content-Length", "0"))
                    if size < 1 or size > 256:
                        raise ValueError("invalid selection body")
                    body = json.loads(self.rfile.read(size))
                    if not isinstance(body, dict):
                        raise ValueError("invalid selection body")
                    if self.path.endswith("/capture-volume"):
                        if set(body) != {"volume"} or type(body["volume"]) is not int:
                            raise ValueError("volume must be an integer from 0 to 100")
                        return self._json(200, control.capture_volume(body["volume"]))
                    return self._json(200, control.select(body.get("mac")))
            except (ValueError, TypeError, json.JSONDecodeError) as error:
                return self._json(400, {"error": str(error)})
            except (OSError, RuntimeError) as error:
                return self._json(503, {"error": str(error)})
            self._json(404, {"error": "not found"})

    return Handler


def serve(control, port=8765):
    ThreadingHTTPServer(("0.0.0.0", port), make_handler(control)).serve_forever()
