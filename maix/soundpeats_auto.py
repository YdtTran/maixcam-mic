"""Run on MaixCAM: connect the selected headset and route audio through BlueALSA."""

import argparse
import os
import re
import subprocess
import time
from pathlib import Path

try:
    from .bluetooth_control import BluetoothControl, SELECTION_PATH, serve
except ImportError:  # Run directly on MaixCAM.
    from bluetooth_control import BluetoothControl, SELECTION_PATH, serve


ROUTE_MARKER = "# managed by soundpeats_auto.py"


def run_command(command, timeout=20):
    try:
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, timeout=timeout)
        return result.returncode, result.stdout or ""
    except (OSError, subprocess.TimeoutExpired) as error:
        return 1, str(error)


class SoundpeatsConnector:
    def __init__(self, mac, run=run_command, spawn=subprocess.Popen, config_path=Path("/root/.asoundrc")):
        if not re.fullmatch(r"(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}", mac):
            raise ValueError("MAC must be six colon-separated hex pairs")
        self.mac = mac.upper()
        self.run = run
        self.spawn = spawn
        self.config_path = Path(config_path)

    def _start_bluealsa(self):
        code, _ = self.run(["pidof", "bluealsa"])
        if code != 0:
            self.spawn(["bluealsa", "-p", "a2dp-source", "-p", "hfp-ag", "-p", "hsp-ag"], stdin=subprocess.DEVNULL,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       start_new_session=True)
            time.sleep(1)

    def _route_playback(self):
        config = (
            ROUTE_MARKER + "\n"
            + 'pcm.bt_output { type plug slave { pcm { type bluealsa device "' + self.mac + '" profile "a2dp" } rate 48000 channels 2 } }\n'
            + 'pcm.bt_input { type plug slave { pcm { type bluealsa device "' + self.mac + '" profile "sco" } rate 8000 channels 1 } }\n'
            + 'pcm.!default { type asym playback.pcm "bt_output" capture.pcm "bt_input" }\n'
        )
        if self.config_path.exists():
            existing = self.config_path.read_text()
            if existing == config:
                return
            if not existing.startswith(ROUTE_MARKER):
                raise RuntimeError("existing ALSA config is not managed by this script")
        temporary = self.config_path.with_suffix(".tmp")
        temporary.write_text(config)
        os.replace(temporary, self.config_path)

    def attempt(self):
        self.run(["bluetoothctl", "power", "on"])
        self.run(["bluetoothctl", "pairable", "on"])
        self._start_bluealsa()
        _, info = self.run(["bluetoothctl", "info", self.mac])
        if "Paired: yes" not in info:
            code, output = self.run(["bluetoothctl", "pair", self.mac], timeout=25)
            if code != 0:
                print("Pairing pending:", output.strip(), flush=True)
                return False
        if "Connected: yes" not in info:
            code, output = self.run(["bluetoothctl", "connect", self.mac], timeout=20)
            if code != 0:
                print("Connection pending:", output.strip(), flush=True)
                return False
        self._route_playback()
        return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", type=Path, default=SELECTION_PATH)
    parser.add_argument("--token", type=Path, default=Path("/root/.talkback_token"))
    args = parser.parse_args()
    token = args.token.read_text().strip()
    if len(bytes.fromhex(token)) != 16:
        raise ValueError("control token must contain 32 hex digits")
    legacy_mac = BluetoothControl(Path("/root/.bluetooth_device")).selected()
    if legacy_mac:
        run_command(["bluetoothctl", "untrust", legacy_mac])
        run_command(["bluetoothctl", "disconnect", legacy_mac])
    control = None

    def connect(mac):
        previous = control.selected()
        if not SoundpeatsConnector(mac).attempt():
            return False
        if previous and previous != mac:
            run_command(["bluetoothctl", "disconnect", previous])
        print(f"Bluetooth {mac} connected by operator selection", flush=True)
        return True

    control = BluetoothControl(args.selection, connect=connect)
    serve(control, token)


if __name__ == "__main__":
    main()
