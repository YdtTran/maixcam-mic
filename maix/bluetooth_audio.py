"""Run on MaixCAM: reconnect the fixed headset and route audio through BlueALSA."""

import argparse
import os
import re
import subprocess
import threading
import time
from pathlib import Path

try:
    from .bluetooth_control import BluetoothControl, SELECTION_PATH, serve
except ImportError:  # Run directly on MaixCAM.
    from bluetooth_control import BluetoothControl, SELECTION_PATH, serve


ROUTE_MARKER = "# managed by bluetooth_audio.py"
LEGACY_ROUTE_MARKER = "# managed by soundpeats_auto.py"


def run_command(command, timeout=20):
    try:
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, timeout=timeout)
        return result.returncode, result.stdout or ""
    except (OSError, subprocess.TimeoutExpired) as error:
        return 1, str(error)


class BluetoothAudioConnector:
    def __init__(self, mac, run=run_command, spawn=subprocess.Popen, config_path=Path("/root/.asoundrc"),
                 playback_profile="a2dp", sco_mtu=None, recover_stuck_sco=False, monotonic=time.monotonic):
        if playback_profile not in ("a2dp", "sco"):
            raise ValueError("playback profile must be a2dp or sco")
        self.playback_profile = playback_profile
        if sco_mtu is not None and (playback_profile != "sco" or not 2 <= sco_mtu <= 254 or sco_mtu % 2):
            raise ValueError("SCO MTU override requires SCO playback and an even size from 2 to 254")
        self.sco_mtu = sco_mtu
        if recover_stuck_sco and playback_profile != "sco":
            raise ValueError("stuck SCO recovery requires explicit SCO playback")
        self.recover_stuck_sco = recover_stuck_sco
        self.monotonic = monotonic
        self.stuck_sco_since = None
        self.last_sco_reset = None
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
        rate, channels = (8000, 1) if self.playback_profile == "sco" else (48000, 2)
        config = (
            ROUTE_MARKER + "\n"
            + f'pcm.bt_output {{ type plug slave {{ pcm {{ type bluealsa device "{self.mac}" profile "{self.playback_profile}" }} rate {rate} channels {channels} }} }}\n'
            + 'pcm.bt_input { type plug slave { pcm { type bluealsa device "' + self.mac + '" profile "sco" } rate 8000 channels 1 } }\n'
            + 'pcm.!default { type asym playback.pcm "bt_output" capture.pcm "bt_input" }\n'
        )
        if self.config_path.exists():
            existing = self.config_path.read_text()
            if existing == config:
                return
            if not existing.startswith((ROUTE_MARKER, LEGACY_ROUTE_MARKER)):
                raise RuntimeError("existing ALSA config is not managed by this script")
        temporary = self.config_path.with_suffix(".tmp")
        temporary.write_text(config)
        os.replace(temporary, self.config_path)

    def _recover_sco(self):
        code, connections = self.run(["hcitool", "-i", "hci0", "con"], timeout=5)
        devices = set(re.findall(r"(?:[0-9A-F]{2}:){5}[0-9A-F]{2}", connections.upper()))
        stuck = re.search(r"(?:eSCO|SCO)\s+" + re.escape(self.mac) + r"\b.*\bstate\s+8\b",
                          connections, re.IGNORECASE)
        # An adapter reset affects every link on it. Unknown reads and another
        # device must never authorize this camera/headset-specific recovery.
        if code != 0 or devices - {self.mac} or not stuck:
            self.stuck_sco_since = None
            return True
        now = self.monotonic()
        if self.stuck_sco_since is None:
            self.stuck_sco_since = now
        if now - self.stuck_sco_since < 30 or (self.last_sco_reset is not None and now - self.last_sco_reset < 60):
            return True
        self.last_sco_reset = now
        print("Recovering persistent stuck headset SCO with scoped hci0 reset", flush=True)
        code, output = self.run(["hciconfig", "hci0", "reset"], timeout=5)
        if code != 0:
            print("SCO controller recovery failed:", output.strip(), flush=True)
            return False
        self.stuck_sco_since = None
        return True

    def prepare_sco(self):
        """Initialize the controller before setting the MTU used by new sockets."""
        if self.sco_mtu is not None:
            code, info = self.run(["hciconfig", "hci0"])
            if code != 0:
                return False
            if not re.search(r"^\s*UP\b", info, re.MULTILINE):
                code, output = self.run(["hciconfig", "hci0", "up"], timeout=5)
                if code != 0:
                    print("SCO controller power-up pending:", output.strip(), flush=True)
                    return False
                # Power-up reads the controller's original buffer size, replacing
                # overrides made while DOWN. Read it again after initialization.
                code, info = self.run(["hciconfig", "hci0"])
                if code != 0 or not re.search(r"^\s*UP\b", info, re.MULTILINE):
                    return False
            size = re.search(r"SCO MTU:\s*(\d+):(\d+)", info)
            if code != 0 or size is None:
                print("SCO MTU status unavailable", flush=True)
                return False
            if int(size.group(1)) != self.sco_mtu:
                code, output = self.run(["hciconfig", "hci0", "scomtu", f"{self.sco_mtu}:{size.group(2)}"])
                if code != 0:
                    print("SCO MTU override failed:", output.strip(), flush=True)
                    return False
                # Existing SCO sockets retain their MTU. Do not reset a healthy
                # link here; apply before capture starts or reopen audio once.
                print("SCO MTU configured; existing audio sockets retain their previous size", flush=True)
            code, verified = self.run(["hciconfig", "hci0"])
            if (code != 0 or not re.search(r"^\s*UP\b", verified, re.MULTILINE)
                    or not re.search(r"SCO MTU:\s*" + str(self.sco_mtu) + r":", verified)):
                return False
        return True

    def attempt(self):
        if self.recover_stuck_sco and not self._recover_sco():
            return False
        if not self.prepare_sco():
            return False
        self._start_bluealsa()
        code, info = self.run(["bluetoothctl", "info", self.mac])
        if code != 0 and "not available" in info.lower():
            self.run(["bluetoothctl", "power", "on"])
            self.run(["bluetoothctl", "--timeout", "10", "scan", "on"], timeout=15)
            code, info = self.run(["bluetoothctl", "info", self.mac])
        if code != 0:
            print("Headset status unavailable:", info.strip(), flush=True)
            return False
        # Polling a healthy connection must not continually mutate adapter and
        # trust state. A transient info failure must not trigger re-pairing.
        if "Connected: yes" not in info:
            code, output = self.run(["bluetoothctl", "power", "on"])
            if code != 0:
                print("Bluetooth power pending:", output.strip(), flush=True)
                return False
        if "Paired: yes" not in info:
            self.run(["bluetoothctl", "pairable", "on"])
            code, output = self.run(["bluetoothctl", "pair", self.mac], timeout=25)
            if code != 0:
                print("Pairing pending:", output.strip(), flush=True)
                return False
        if "Trusted: yes" not in info:
            code, output = self.run(["bluetoothctl", "trust", self.mac])
            if code != 0:
                print("Headset trust pending:", output.strip(), flush=True)
                return False
        if "Connected: yes" not in info:
            code, output = self.run(["bluetoothctl", "connect", self.mac], timeout=20)
            if code != 0:
                print("Connection pending:", output.strip(), flush=True)
                return False
        self._route_playback()
        return True


def reconnect_headset(connector, stop, interval=5):
    retry_delay = interval
    while not stop.is_set():
        connected = False
        try:
            connected = connector.attempt()
        except (OSError, RuntimeError) as error:
            print("Headset reconnect pending:", error, flush=True)
        delay = interval if connected else retry_delay
        retry_delay = interval if connected else min(30, retry_delay * 2)
        if stop.wait(delay):
            break


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", type=Path, default=SELECTION_PATH)
    parser.add_argument("--fixed-mac", help="Bluetooth address permanently assigned to this camera")
    parser.add_argument("--playback-profile", choices=("a2dp", "sco"), default="a2dp")
    parser.add_argument("--sco-mtu", type=int,
                        help="Opt-in controller workaround; validated MaixCAM CVSD size is 120 bytes")
    parser.add_argument("--recover-stuck-sco", action="store_true",
                        help="Opt-in hci0 reset after bound headset SCO stays in state 8 for 30s; no other links allowed")
    parser.add_argument("--prepare-sco", action="store_true",
                        help="Prepare powered controller and verified MTU before starting audio clients; exit after one attempt")
    args = parser.parse_args()
    if args.sco_mtu is not None and (args.playback_profile != "sco" or not 2 <= args.sco_mtu <= 254 or args.sco_mtu % 2):
        parser.error("--sco-mtu requires --playback-profile sco and an even size from 2 to 254")
    if args.recover_stuck_sco and args.playback_profile != "sco":
        parser.error("--recover-stuck-sco requires --playback-profile sco")
    if args.prepare_sco:
        if args.playback_profile != "sco" or args.sco_mtu is None or not args.fixed_mac:
            parser.error("--prepare-sco requires --fixed-mac, --playback-profile sco and --sco-mtu")
        connector = BluetoothAudioConnector(args.fixed_mac, playback_profile="sco", sco_mtu=args.sco_mtu)
        if not connector.prepare_sco():
            raise SystemExit(1)
        connector._route_playback()
        return
    mac = args.fixed_mac or BluetoothControl(args.selection).selected()
    if not mac:
        parser.error("set --fixed-mac once to bind this camera to its headset")
    control = BluetoothControl(args.selection, fixed_mac=mac)
    connector = (BluetoothAudioConnector(control.fixed_mac, playback_profile="sco", sco_mtu=args.sco_mtu,
                                        recover_stuck_sco=args.recover_stuck_sco)
                 if args.playback_profile == "sco" else BluetoothAudioConnector(control.fixed_mac))
    stop = threading.Event()
    reconnect = threading.Thread(target=reconnect_headset, args=(connector, stop), daemon=True)
    reconnect.start()
    try:
        serve(control)
    finally:
        stop.set()
        reconnect.join(timeout=2)


if __name__ == "__main__":
    main()
