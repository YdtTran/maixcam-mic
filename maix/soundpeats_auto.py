"""Run on MaixCAM: reconnect SOUNDPEATS and route ALSA playback to BlueALSA.

The RTSP script keeps its existing MaixPy audio.Recorder microphone input.
Put the earbuds into pairing mode for the first pairing attempt.
"""

import argparse
import os
import re
import subprocess
import time
from pathlib import Path


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
            self.spawn(["bluealsa", "-p", "a2dp-source"], stdin=subprocess.DEVNULL,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       start_new_session=True)
            time.sleep(1)

    def _route_playback(self):
        config = (
            ROUTE_MARKER + "\n"
            + 'pcm.bt_output { type plug slave { pcm { type bluealsa device "' + self.mac + '" profile "a2dp" } channels 2 } }\n'
            + 'pcm.!default { type asym playback.pcm "bt_output" capture.pcm "hw:0,0" }\n'
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
        self.run(["bluetoothctl", "trust", self.mac])
        if "Connected: yes" not in info:
            code, output = self.run(["bluetoothctl", "connect", self.mac], timeout=20)
            if code != 0:
                print("Connection pending:", output.strip(), flush=True)
                return False
        self._route_playback()
        return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mac", required=True, help="Bluetooth MAC address of the earbuds")
    args = parser.parse_args()
    connector = SoundpeatsConnector(args.mac)
    while True:
        try:
            connected = connector.attempt()
            print("SOUNDPEATS connected" if connected else "Retrying SOUNDPEATS", flush=True)
        except Exception as error:
            print("SOUNDPEATS error:", error, flush=True)
        time.sleep(15)


if __name__ == "__main__":
    main()
