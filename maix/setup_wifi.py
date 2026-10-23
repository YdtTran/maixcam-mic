"""Join the laptop's required Wi-Fi over USB SSH; read credentials from stdin."""

import json
import hashlib
import codecs
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time


def configure_wifi(settings):
    ssid = settings['ssid']
    password = settings.get('password')
    if not isinstance(ssid, str) or not 1 <= len(ssid.encode('utf-8')) <= 32 or any(ord(c) < 32 or ord(c) == 127 for c in ssid):
        raise ValueError('Invalid SSID')
    interfaces = [p for p in Path('/sys/class/net').iterdir() if (p / 'wireless').exists()]
    if len(interfaces) != 1:
        raise RuntimeError('Camera must have one Wi-Fi interface')
    interface = interfaces[0]
    mac = (interface / 'address').read_text().strip()
    if settings.get('mac') and settings['mac'].lower() != mac.lower():
        raise RuntimeError('Camera Wi-Fi MAC changed')

    def wpa(*args):
        result = subprocess.run(['wpa_cli', '-i', interface.name, *args], capture_output=True, text=True, timeout=10)
        if result.returncode or 'FAIL' in result.stdout.splitlines():
            raise RuntimeError('Camera Wi-Fi command failed')
        return result.stdout.strip()

    def status():
        result = dict(line.split('=', 1) for line in wpa('status').splitlines() if '=' in line)
        if 'ssid' in result:
            result['ssid'] = codecs.escape_decode(result['ssid'].encode('utf-8'))[0].decode('utf-8')
        return result

    current = status()
    previous_id = current.get('id', '')
    needs_switch = current.get('ssid') != ssid or current.get('wpa_state') != 'COMPLETED'
    if needs_switch:
        if not isinstance(password, str) or not 8 <= len(password) <= 63 or any(ord(c) < 32 or ord(c) > 126 for c in password):
            raise ValueError('Supply an 8–63 character WPA/WPA2-Personal Wi-Fi password')
    config = Path('/etc/wpa_supplicant.conf')
    boot = Path('/boot/wpa_supplicant.conf')
    backup = Path('/root') / ('workercam-wifi-backup-' + str(time.time_ns()))
    backup.mkdir(mode=0o700)
    for source, name in ((config, 'etc.conf'), (boot, 'boot.conf')):
        if source.exists():
            shutil.copy2(source, backup / name)
            (backup / name).chmod(0o600)
    network = None
    try:
        if needs_switch:
            network = wpa('add_network')
            if not network.isdecimal():
                raise RuntimeError('Invalid Wi-Fi network identifier')
            wpa('set_network', network, 'ssid', ssid.encode('utf-8').hex())
            psk = hashlib.pbkdf2_hmac('sha1', password.encode('ascii'), ssid.encode('utf-8'), 4096, 32).hex()
            wpa('set_network', network, 'psk', psk)
            wpa('set_network', network, 'key_mgmt', 'WPA-PSK')
            wpa('select_network', network)
        else:
            if not previous_id.isdecimal():
                raise RuntimeError('Camera current Wi-Fi network identifier is missing')
            wpa('select_network', previous_id)
        deadline = time.monotonic() + 60
        while True:
            current = status()
            if current.get('ssid') == ssid and current.get('wpa_state') == 'COMPLETED':
                break
            if time.monotonic() >= deadline:
                raise RuntimeError('Camera did not join the required Wi-Fi')
            time.sleep(1)
        if needs_switch:
            # A one-shot lease refresh avoids retaining the previous network's address.
            lease = subprocess.run(['udhcpc', '-i', interface.name, '-n', '-q', '-t', '5', '-T', '2'],
                                   capture_output=True, timeout=20)
            if lease.returncode:
                raise RuntimeError('Camera Wi-Fi DHCP failed')
        current = status()
        if current.get('ssid') != ssid or current.get('wpa_state') != 'COMPLETED' or not current.get('ip_address'):
            raise RuntimeError('Camera must remain connected to the required Wi-Fi')
        wpa('set', 'update_config', '1')
        wpa('save_config')
        config.chmod(0o600)
        temporary = boot.with_name('workercam-wifi.conf.tmp')
        try:
            shutil.copy2(config, temporary)
            temporary.chmod(0o600)
            os.replace(temporary, boot)
        finally:
            temporary.unlink(missing_ok=True)
    except Exception:
        if network and network.isdecimal():
            try:
                wpa('remove_network', network)
                if previous_id.isdecimal():
                    wpa('select_network', previous_id)
            except Exception:
                pass
        for target, name in ((config, 'etc.conf'), (boot, 'boot.conf')):
            if (backup / name).exists():
                shutil.copy2(backup / name, target)
            else:
                target.unlink(missing_ok=True)
        raise
    return dict(ssid=ssid, mac=mac, ip=current['ip_address'])


def main():
    try:
        result = configure_wifi(json.load(sys.stdin))
    except Exception:
        # Credentials and subprocess arguments must never reach SSH error output.
        print('Camera Wi-Fi setup failed. Check password, WPA/WPA2-Personal support and camera Wi-Fi backups.', file=sys.stderr)
        return 1
    print(json.dumps(result))
    return 0


if __name__ == '__main__':
    sys.exit(main())
