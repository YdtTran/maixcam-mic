"""Read-only camera reachability checks; USB is a diagnostic fallback."""
import argparse
import ipaddress
import json
import os
import socket
from concurrent.futures import ThreadPoolExecutor

DEFAULT_USB_IP = "10.172.16.1"
PORTS = {"ssh": 22, "rtsp_control": 8554, "bluetooth_control": 8765}


def ipv4(value):
    return str(ipaddress.IPv4Address(value))


def probe(host, connect=socket.create_connection):
    def reachable(item):
        name, port = item
        try:
            with connect((host, port), timeout=2):
                return name, True
        except OSError:
            return name, False

    with ThreadPoolExecutor(max_workers=len(PORTS)) as executor:
        services = dict(executor.map(reachable, PORTS.items()))
    return {"ip": host, "reachable": any(services.values()), "tcp_services": services}


class CameraDiagnostics:
    def __init__(self, wifi_ip, usb_ip=DEFAULT_USB_IP, probe_host=probe):
        self.wifi_ip = ipv4(wifi_ip)
        self.usb_ip = ipv4(usb_ip) if usb_ip else None
        self.probe_host = probe_host

    def check(self):
        wifi = self.probe_host(self.wifi_ip)
        usb = None
        if wifi["reachable"]:
            message = "Wi-Fi services reachable. Check media services if playback is unavailable."
        elif self.usb_ip:
            usb = self.probe_host(self.usb_ip)
            message = ("Wi-Fi services unreachable. USB services reachable; use USB to diagnose the camera."
                       if usb["reachable"] else "Wi-Fi and USB services unreachable. Check camera power and network connections.")
        else:
            message = "Wi-Fi services unreachable. Configure MAIX_USB_IP for USB diagnosis."
        return {"wifi": wifi, "usb": usb, "usb_ip": self.usb_ip, "message": message,
                "media_ip": self.wifi_ip, "diagnostic_only": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--maix-ip", type=ipv4, default=os.environ.get("MAIX_IP", "192.168.1.7"))
    parser.add_argument("--maix-usb-ip", type=ipv4, default=os.environ.get("MAIX_USB_IP") or DEFAULT_USB_IP)
    args = parser.parse_args()
    result = CameraDiagnostics(args.maix_ip, args.maix_usb_ip).check()
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["wifi"]["reachable"] or (result["usb"] and result["usb"]["reachable"]) else 1)


if __name__ == "__main__":
    main()
