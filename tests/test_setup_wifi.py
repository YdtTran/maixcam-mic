"""Camera Wi-Fi setup with isolated files and mocked wpa_cli/DHCP."""

import io
import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from maix import setup_wifi


class WifiSetupTests(unittest.TestCase):
    def run_setup(self, failure=None, already_connected=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            wifi = root / 'sys/class/net/wlan0'
            (wifi / 'wireless').mkdir(parents=True)
            (wifi / 'address').write_text('ab:cd:ef:01:23:45\n')
            (root / 'root').mkdir()
            for name in ('etc', 'boot'):
                (root / name).mkdir()
                (root / name / 'wpa_supplicant.conf').write_text('original-' + name)
            calls = []
            joined = already_connected
            ssid = 'Café "WiFi" & $(noop)'
            password = 'secret"\\password'

            def command(args, **kwargs):
                nonlocal joined
                calls.append(args)
                action = args[3] if args[0] == 'wpa_cli' else 'dhcp'
                output = 'OK'
                if action == 'status':
                    encoded_ssid = ssid.encode('utf-8').decode('latin1').encode('unicode_escape').decode('ascii')
                    output = f'wpa_state=COMPLETED\nssid={encoded_ssid if joined else "Old WiFi"}\nid={"1" if joined else "0"}\nip_address=192.0.2.1'
                if action == 'add_network':
                    output = '1'
                if action == 'select_network' and args[4] == '1' and failure != 'timeout':
                    joined = True
                if action == 'set_network' and failure == 'password':
                    output = 'FAIL'
                if action == 'save_config':
                    (root / 'etc/wpa_supplicant.conf').write_text('new-wifi-config')
                    if failure == 'save':
                        output = 'FAIL'
                return subprocess.CompletedProcess(args, 1 if failure == 'dhcp' and action == 'dhcp' else 0, output, '')

            with patch.object(setup_wifi, 'Path', side_effect=lambda path: root / str(path).lstrip('/')), \
                    patch.object(setup_wifi.subprocess, 'run', side_effect=command), \
                    patch.object(setup_wifi.time, 'monotonic', return_value=0, side_effect=[0, 61] if failure == 'timeout' else None):
                settings = dict(ssid=ssid, mac='ab:cd:ef:01:23:45', password=password)
                if already_connected:
                    settings.pop('password')
                if failure:
                    with self.assertRaises(RuntimeError):
                        setup_wifi.configure_wifi(settings)
                else:
                    self.assertEqual(setup_wifi.configure_wifi(settings), dict(ssid=ssid, mac=settings['mac'], ip='192.0.2.1'))
            contents = [(root / name / 'wpa_supplicant.conf').read_text() for name in ('etc', 'boot')]
            if failure:
                self.assertEqual(contents, ['original-etc', 'original-boot'])
            else:
                self.assertEqual(contents, ['new-wifi-config'] * 2)
                if not already_connected:
                    self.assertIn(['wpa_cli', '-i', 'wlan0', 'set_network', '1', 'ssid', ssid.encode().hex()], calls)
                    self.assertIn(['wpa_cli', '-i', 'wlan0', 'set_network', '1', 'psk',
                                   hashlib.pbkdf2_hmac('sha1', password.encode(), ssid.encode(), 4096, 32).hex()], calls)
                self.assertNotIn(password, str(calls))
            return calls

    def test_switch_persists_boot_settings_and_treats_credentials_as_data(self):
        self.run_setup()

    def test_same_ssid_persists_current_profile_without_password_or_dhcp(self):
        calls = self.run_setup(already_connected=True)
        self.assertNotIn('udhcpc', str(calls))
        self.assertNotIn('add_network', str(calls))
        self.assertIn(['wpa_cli', '-i', 'wlan0', 'save_config'], calls)

    def test_failed_switch_restores_configs_and_previous_network(self):
        for failure in ('password', 'timeout', 'dhcp', 'save'):
            with self.subTest(failure=failure):
                calls = self.run_setup(failure=failure)
                self.assertIn(['wpa_cli', '-i', 'wlan0', 'remove_network', '1'], calls)
                self.assertIn(['wpa_cli', '-i', 'wlan0', 'select_network', '0'], calls)

    def test_main_never_prints_credentials_or_command_errors(self):
        with patch.object(setup_wifi.sys, 'stdin', io.StringIO('{"ssid":"test"}')), \
                patch.object(setup_wifi, 'configure_wifi', side_effect=RuntimeError('secret-password')), \
                patch.object(setup_wifi.sys, 'stderr', new_callable=io.StringIO) as errors:
            self.assertEqual(setup_wifi.main(), 1)
            self.assertNotIn('secret-password', errors.getvalue())

    def test_invalid_ssid_is_rejected_before_camera_commands(self):
        for ssid in ('', 'x' * 33, 'bad\nssid', 'bad\x00ssid'):
            with self.subTest(ssid=ssid), patch.object(setup_wifi.subprocess, 'run') as command:
                with self.assertRaises(ValueError):
                    setup_wifi.configure_wifi(dict(ssid=ssid))
                command.assert_not_called()
