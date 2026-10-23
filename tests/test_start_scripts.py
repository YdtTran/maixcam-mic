"""Exercise deployment failures without touching Docker, SSH or the camera."""

import os
import base64
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


class BootTuningTests(unittest.TestCase):
    def test_installer_requires_matching_camera_ssid_and_mac(self):
        source = (ROOT / 'scripts/NetworkDeployment.psm1').read_text()
        check = source.split(". ./workercam.env\npython3 - <<'PY'\n", 1)[1].split('\nPY\n', 1)[0]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            net = root / 'net'
            wifi = net / 'wlan0'
            (wifi / 'wireless').mkdir(parents=True)
            (wifi / 'address').write_text('ab:cd:ef:01:23:45\n')
            ssid = 'Lab "WiFi" & $(noop)'
            (root / 'workercam.env').write_text('WIFI_SSID_B64=' + base64.b64encode(ssid.encode()).decode() +
                                               '\nWIFI_MAC=ab:cd:ef:01:23:45\n')
            check = check.replace("'/sys/class/net'", repr(str(net))).replace("'workercam.env'", repr(str(root / 'workercam.env')))
            with patch('subprocess.check_output', return_value=f'wpa_state=COMPLETED\nssid={ssid}\n') as command:
                exec(compile(check, '<installer wifi check>', 'exec'), {})
                command.assert_called_once_with(['wpa_cli', '-i', 'wlan0', 'status'], text=True)
            with patch('subprocess.check_output', return_value='wpa_state=COMPLETED\nssid=Other WiFi\n'):
                with self.assertRaisesRegex(SystemExit, 'laptop Wi-Fi SSID'):
                    exec(compile(check, '<installer wifi check>', 'exec'), {})
            (wifi / 'address').write_text('ab:cd:ef:01:23:46\n')
            with self.assertRaisesRegex(SystemExit, 'Wi-Fi MAC changed'):
                exec(compile(check, '<installer wifi check>', 'exec'), {})

    def test_deployment_entry_points_require_administrator(self):
        scripts = sorted(str(path.relative_to(ROOT)).replace('\\', '/')
                         for path in ROOT.glob('*.ps1'))
        scripts += sorted(str(path.relative_to(ROOT)).replace('\\', '/')
                          for path in (ROOT / 'scripts').glob('*.ps1'))
        self.assertEqual(scripts, ['scripts/deploy.ps1'])
        self.assertEqual((ROOT / scripts[0]).read_text().splitlines()[0], '#Requires -RunAsAdministrator')

    def test_tuning_precedes_bluetooth_and_is_best_effort(self):
        script = (ROOT / "maix/background_services.rc.local").read_text()
        tuning = script[script.index("dmesg -n 4"):script.index('case "${AUDIO_PROFILE')]
        self.assertIn("echo 4 >/proc/sys/kernel/printk", tuning)
        self.assertIn("iw dev wlan0 set power_save off", tuning)
        self.assertIn("iwconfig wlan0 power off", tuning)
        self.assertEqual(tuning.count("|| true"), 2)
        self.assertLess(script.index(tuning), script.index("--prepare-sco"))

    @unittest.skipUnless(os.name != "nt" and shutil.which("sh"), "POSIX boot shell")
    def test_shell_runs_fallbacks_and_continues_when_tuning_fails(self):
        script = (ROOT / "maix/background_services.rc.local").read_text()
        tuning = script[script.index("dmesg -n 4"):script.index('case "${AUDIO_PROFILE')]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("dmesg", "iw", "iwconfig"):
                stub = root / name
                stub.write_text('#!/bin/sh\necho "' + name + ' $*" >> "$EVENTS"\nexit 1\n')
                stub.chmod(0o755)
            for writable in (True, False):
                target = root / "printk" if writable else root / "missing" / "printk"
                result = subprocess.run([shutil.which("sh"), "-ec", tuning.replace("/proc/sys/kernel/printk", str(target)) +
                                         "echo services-started"], capture_output=True, text=True, timeout=5,
                                        env={**os.environ, "PATH": directory, "EVENTS": str(root / "events")})
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("services-started", result.stdout)
            self.assertEqual((root / "printk").read_text(), "4\n")
            self.assertEqual((root / "events").read_text().splitlines(),
                             ["dmesg -n 4", "iw dev wlan0 set power_save off", "iwconfig wlan0 power off"] * 2)


@unittest.skipUnless(os.name == "nt", "Windows PowerShell deployment helpers")
class DeploymentScriptTests(unittest.TestCase):
    def run_helper(self, name, case="ready", arguments=""):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            helpers = {'deploy_maix.ps1': 'Install-MaixCamera',
                       'deploy_pc.ps1': 'Install-PcRuntime', 'stop_docker_pc.ps1': 'Stop-PcRuntime'}
            for filename, function in helpers.items():
                (root / filename).write_text(
                    "Import-Module (Join-Path $PSScriptRoot 'scripts/NetworkDeployment.psm1') -Force -DisableNameChecking\n"
                    + function + ' @args\n')
            (root / "scripts").mkdir()
            shutil.copy2(ROOT / "scripts/NetworkDeployment.psm1", root / "scripts/NetworkDeployment.psm1")
            with (root / "scripts/NetworkDeployment.psm1").open("a") as module:
                module.write(r'''
function Invoke-NetworkProcess {
    param($FilePath, $Arguments, $TimeoutSeconds, $InputText, $Environment)
    if ($FilePath -eq 'docker.exe') { return '' }
    if ($FilePath -eq 'ssh-keygen.exe') { return '256 SHA256:test key' }
    if ($FilePath -eq 'ssh.exe') {
        if ($InputText -like 'set -eu*') {
            Write-Host 'CAMERA_PREFLIGHT'
            if ($env:DEPLOY_TEST_CASE -eq 'preflight-failed') { throw 'Camera prerequisite check failed' }
        } elseif ($InputText -like "sh '*install.sh'*") {
            Write-Host 'CAMERA_INSTALL'
            if ($env:DEPLOY_TEST_CASE -eq 'install-failed') { throw 'Camera installation failed' }
        } else { throw 'Unexpected remote command' }
        return ''
    }
    if ($FilePath -eq 'scp.exe') {
        Write-Host 'CAMERA_UPLOAD'
        if ($env:DEPLOY_TEST_CASE -eq 'upload-failed') { throw 'Camera upload failed' }
        $installer = @($Arguments | Where-Object { $_ -like '*install.sh' })[0]
        Copy-Item -LiteralPath $installer -Destination (Join-Path $env:DEPLOY_TEST_ROOT 'captured-installer.sh')
        Copy-Item -LiteralPath (Join-Path (Split-Path $installer) 'workercam.env') -Destination (Join-Path $env:DEPLOY_TEST_ROOT 'captured-camera.env')
        return ''
    }
    throw 'Unexpected executable'
}
function Test-HostUdpListeners {
    param($Ports)
    if ($env:DEPLOY_TEST_CASE -eq 'udp-missing') { return $false }
    if ($env:DEPLOY_TEST_CASE -eq 'udp-recovered') {
        if ($global:recreated) { return $true }
        return $false
    }
    return $true
}
function Assert-LaptopWifiSsid {
    param($WifiSsid,$PcIp)
    if ($WifiSsid -cne 'Test WiFi' -or $PcIp -ne '192.0.2.2') { throw 'Wrong laptop SSID/IP' }
}
function Set-MaixWifi {
    param($Context,$HostAddress,$WifiSsid,$WifiPassword,$WifiMac)
    $ssid = if ($env:DEPLOY_TEST_CASE -eq 'wrong-ssid') { 'Other WiFi' } else { 'Test WiFi' }
    return [pscustomobject]@{ssid=$ssid;mac='ab:cd:ef:01:23:45';ip='192.0.2.1'}
}
Export-ModuleMember -Function *
''')
            for folder in ("maix", "pc"):
                (root / folder).mkdir()
                for source in (ROOT / folder).iterdir():
                    if source.suffix in (".py", ".yaml", ".local"):
                        shutil.copy2(source, root / folder / source.name)
            (root / ".env").write_text("MAIX_IP=192.0.2.1\n")
            if case == 'no-env':
                (root / '.env').unlink()
            (root / ".env.example").write_text("MAIX_IP=192.0.2.1\n")
            (root / "test.ppk").write_text("mock key; not used for authentication")
            script = r'''
$ErrorActionPreference = 'Stop'
function Get-NetTCPConnection { return }
function Get-NetFirewallRule { return }
function New-NetFirewallRule {
    param($DisplayName,$Direction,$Action,$Protocol,$LocalPort,$RemoteAddress,$Profile,$Enabled,$ErrorAction)
    if ($env:DEPLOY_TEST_CASE -eq 'firewall-failed') { throw 'Firewall denied' }
    if ($RemoteAddress -ne '192.0.2.1') { throw 'Wrong firewall camera IP' }
    Write-Host 'FIREWALL_ALLOW'
}
$global:recreated = $false
$global:stopped = $false
$global:upgraded = $false
function Get-NetUDPEndpoint {
    param($LocalPort)
    if ($env:DEPLOY_TEST_CASE -eq 'udp-missing') { return }
    if ($env:DEPLOY_TEST_CASE -eq 'udp-recovered') {
        if ($global:recreated) { return [pscustomobject]@{ LocalPort = $LocalPort } }
        return
    }
    return [pscustomobject]@{ LocalPort = $LocalPort }
}
function docker {
    $global:LASTEXITCODE = 0
    $call = $args -join ' '
    if ($args[0] -eq 'info') { return 'linux' }
    if ($call -like '*config --format json*') {
        if ($env:DEPLOY_TEST_CASE -eq 'wrong-mode') {
            return '{"services":{"server":{"environment":{"RTSP_TRANSPORT":"udp","STREAM_MODE":"combined"}}}}'
        }
        return '{"services":{"server":{"command":["python","app.py","--maix-ip","192.0.2.1"],"environment":{"RTSP_TRANSPORT":"tcp","STREAM_MODE":"video"}}}}'
    }
    if ($call -like '*ps --all --quiet server*') {
        if ($env:DEPLOY_TEST_CASE -ne 'empty') { return 'test-container' }
        return
    }
    if ($args[0] -eq 'inspect') { if ($global:stopped) { return 'exited' }; return 'running' }
    if ($call -like '*exec -T server*') {
        switch ($env:DEPLOY_TEST_CASE) {
            'recording' { return '{"recording":true}' }
            'finalizing' { return '{"recording":false,"finalizing":true}' }
            'status-failed' { $global:LASTEXITCODE = 1; return }
            'invalid-status' { return '{}' }
            'no-finalizing' { return '{"recording":false}' }
            default {
                if (($env:DEPLOY_TEST_CASE -eq 'legacy' -and -not $global:upgraded) -or $env:DEPLOY_TEST_CASE -eq 'legacy-unsupported') { return '{"recording":false,"finalizing":false}' }
                $marker = Join-Path $env:DEPLOY_TEST_ROOT 'recordings/.maintenance.json'
                if ($call -like '*/api/maintenance/begin*') {
                    if ($call -notmatch "owner='([a-f0-9]{32})'") { throw 'Missing API owner' }
                    [void](New-Item -ItemType Directory -Path (Split-Path $marker) -Force)
                    [IO.File]::WriteAllText($marker, (@{owner=$Matches[1]} | ConvertTo-Json))
                    Write-Host 'MAINTENANCE_BEGIN'
                }
                if ($call -like '*/api/maintenance/end*') { Remove-Item -LiteralPath $marker; Write-Host 'MAINTENANCE_END' }
                $maintenance = if (Test-Path -LiteralPath $marker) { Get-Content -LiteralPath $marker -Raw | ConvertFrom-Json } else { $null }
                return (@{recording=$false;finalizing=$false;maintenance=$maintenance} | ConvertTo-Json -Compress)
            }
        }
    }
    if ($call -like '*--force-recreate*') {
        $global:recreated = $true
        Write-Host 'DOCKER_RECREATE_SERVER'
    }
    if ($call -like '* up *') { $global:stopped = $false; $global:upgraded = $true; Write-Host 'DOCKER_UP' }
    if ($call -like '* stop server') { $global:stopped = $true; Write-Host 'DOCKER_STOP_SERVER' }
}
$global:testClock = 0
function Get-Date {
    $global:testClock++
    return ([datetime]'2026-10-11').AddMinutes($global:testClock)
}
function Invoke-WebRequest {
    if ($env:DEPLOY_TEST_CASE -eq 'http-failed') { throw 'Simulated connection refused' }
    return @{ StatusCode = 200 }
}
try {
    & (Join-Path $env:DEPLOY_TEST_ROOT '__SCRIPT__') __ARGS__
} catch {
    Write-Output ('ERROR: ' + $_.Exception.Message)
    exit 1
}
'''.replace("__SCRIPT__", name).replace("__ARGS__", arguments)
            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                env={**os.environ, "DEPLOY_TEST_ROOT": directory, "DEPLOY_TEST_CASE": case},
                capture_output=True, text=True, timeout=25,
            )
            captured = {p.name: p.read_text() for p in root.glob("captured-*")}
            captured['maintenance-retained'] = (root / 'recordings/.maintenance.json').exists()
            captured['host-lock-created'] = (root / '.runtime/mutation.lock').exists()
            return result.returncode, result.stdout + result.stderr, captured

    def test_legacy_bootstrap_precedes_camera_mutation_and_stop_does_not_restart(self):
        code, output, files = self.run_helper('deploy_maix.ps1', 'legacy', self.camera_arguments())
        self.assertEqual(code, 0, output)
        self.assertLess(output.index('DOCKER_STOP_SERVER'), output.index('DOCKER_UP'))
        self.assertLess(output.index('DOCKER_UP'), output.index('CAMERA_PREFLIGHT'))
        self.assertFalse(files['maintenance-retained'])
        code, output, files = self.run_helper('stop_docker_pc.ps1', 'legacy')
        self.assertEqual(code, 0, output)
        self.assertNotIn('DOCKER_UP', output)
        self.assertFalse(files['maintenance-retained'])

    def test_unsupported_replacement_is_stopped_before_camera_mutation(self):
        code, output, files = self.run_helper('deploy_maix.ps1', 'legacy-unsupported', self.camera_arguments())
        self.assertNotEqual(code, 0, output)
        self.assertNotIn('CAMERA_PREFLIGHT', output)
        self.assertIn('Replacement does not honor maintenance', output)
        self.assertGreater(output.rindex('DOCKER_STOP_SERVER'), output.index('DOCKER_UP'))
        self.assertTrue(files['maintenance-retained'])

    def test_check_only_does_not_create_maintenance_or_host_lock(self):
        for script in ('deploy_pc.ps1', 'stop_docker_pc.ps1'):
            code, output, files = self.run_helper(script, arguments='-CheckOnly')
            self.assertEqual(code, 0, output)
            self.assertFalse(files['maintenance-retained'])
            self.assertFalse(files['host-lock-created'])
            self.assertNotIn('FIREWALL_ALLOW', output)

    def test_firewall_precedes_start_and_failure_prevents_mutation(self):
        code, output, _ = self.run_helper('deploy_pc.ps1')
        self.assertEqual(code, 0, output)
        self.assertLess(output.index('FIREWALL_ALLOW'), output.index('DOCKER_UP'))
        code, output, files = self.run_helper('deploy_pc.ps1', 'firewall-failed')
        self.assertNotEqual(code, 0, output)
        self.assertIn('Firewall denied', output)
        self.assertNotIn('DOCKER_UP', output)
        self.assertFalse(files['host-lock-created'])

    def test_missing_env_preflight_is_read_only_and_initialization_does_not_start(self):
        code, output, files = self.run_helper('deploy_pc.ps1', 'no-env', '-CheckOnly')
        self.assertNotEqual(code, 0, output)
        self.assertFalse(files['host-lock-created'])
        code, output, files = self.run_helper('deploy_pc.ps1', 'no-env')
        self.assertNotEqual(code, 0, output)
        self.assertIn('Created .env', output)
        self.assertNotIn('DOCKER_UP', output)
        self.assertFalse(files['maintenance-retained'])

    def test_failed_camera_install_retains_maintenance_for_explicit_recovery(self):
        code, output, files = self.run_helper('deploy_maix.ps1', 'install-failed', self.camera_arguments())
        self.assertNotEqual(code, 0, output)
        self.assertTrue(files['maintenance-retained'])
        self.assertIn('Maintenance retained for owner', output)

    def test_deploy_checks_windows_access_after_container_start(self):
        code, output, _ = self.run_helper("deploy_pc.ps1")
        self.assertEqual(code, 0, output)
        self.assertIn("DOCKER_UP", output)
        self.assertIn("Operator UI verified:", output)
        code, output, _ = self.run_helper("deploy_pc.ps1", "http-failed")
        self.assertNotEqual(code, 0)
        self.assertIn("Windows cannot reach", output)
        self.assertNotIn("Operator UI verified:", output)

    def test_deploy_pc_recreates_container_when_udp_listener_missing_and_recovers(self):
        code, output, _ = self.run_helper("deploy_pc.ps1", "udp-recovered")
        self.assertEqual(code, 0, output)
        self.assertIn("DOCKER_RECREATE_SERVER", output)
        self.assertIn("Recreated container; Windows host UDP 8004/8005 listeners verified.", output)
        self.assertIn("Operator UI verified:", output)

    def test_deploy_pc_fails_when_udp_listener_remains_missing_after_recreate(self):
        code, output, _ = self.run_helper("deploy_pc.ps1", "udp-missing")
        self.assertNotEqual(code, 0)
        self.assertIn("DOCKER_RECREATE_SERVER", output)
        self.assertIn("listeners on port 8004/8005 are missing", output)
        self.assertNotIn("Operator UI verified:", output)

    def test_stop_and_update_protect_recording_and_unknown_status(self):
        for name in ("deploy_pc.ps1", "stop_docker_pc.ps1"):
            for case in ("recording", "finalizing", "status-failed", "invalid-status"):
                with self.subTest(name=name, case=case):
                    code, output, _ = self.run_helper(name, case)
                    self.assertNotEqual(code, 0, output)
                    self.assertNotIn("DOCKER_UP", output)
                    self.assertNotIn("DOCKER_STOP_SERVER", output)

    def test_stop_targets_only_operator_and_check_only_does_not_stop(self):
        for case in ("ready", "empty"):
            code, output, _ = self.run_helper("stop_docker_pc.ps1", case)
            self.assertEqual(code, 0, output)
            self.assertIn("DOCKER_STOP_SERVER", output)
        code, output, _ = self.run_helper("stop_docker_pc.ps1", arguments="-CheckOnly")
        self.assertEqual(code, 0, output)
        self.assertNotIn("DOCKER_STOP_SERVER", output)

    def test_stop_check_accepts_idle_status_without_optional_finalizing(self):
        code, output, _ = self.run_helper('stop_docker_pc.ps1', 'no-finalizing', '-CheckOnly')
        self.assertEqual(code, 0, output)
        self.assertNotIn('DOCKER_STOP_SERVER', output)

    def test_legacy_combined_docker_settings_are_rejected(self):
        code, output, _ = self.run_helper("deploy_pc.ps1", "wrong-mode")
        self.assertNotEqual(code, 0)
        self.assertIn("RTSP_TRANSPORT=tcp", output)
        self.assertNotIn("DOCKER_UP", output)

    def camera_arguments(self):
        return ("-WifiSsid 'Test WiFi' -MaixHost 192.0.2.1 -PcIp 192.0.2.2 -HeadsetMac 'AA:BB:CC:DD:EE:FF' "
                "-HostKey 'SHA256:test' -KeyPath (Join-Path $env:DEPLOY_TEST_ROOT 'test.ppk')")

    def test_camera_preflight_or_upload_failure_cannot_install(self):
        for case in ("preflight-failed", "upload-failed"):
            with self.subTest(case=case):
                code, output, _ = self.run_helper("deploy_maix.ps1", case, self.camera_arguments())
                self.assertNotEqual(code, 0, output)
                self.assertNotIn("CAMERA_INSTALL", output)
                if case == "preflight-failed":
                    self.assertNotIn("CAMERA_UPLOAD", output)

    def test_camera_installer_stops_old_runtime_without_backup(self):
        code, output, files = self.run_helper("deploy_maix.ps1", arguments=self.camera_arguments())
        self.assertEqual(code, 0, output)
        self.assertIn("CAMERA_INSTALL", output)
        self.assertIn("PC_IP=192.0.2.2", files["captured-camera.env"])
        self.assertIn("AUDIO_PROFILE=sco", files["captured-camera.env"])
        self.assertIn("WIFI_SSID_B64=VGVzdCBXaUZp", files["captured-camera.env"])
        self.assertIn("WIFI_MAC=ab:cd:ef:01:23:45", files["captured-camera.env"])
        self.assertIn("Wi-Fi MAC: ab:cd:ef:01:23:45", output)
        installer = files["captured-installer.sh"]
        self.assertLess(installer.index('os.kill(pid, sig)'), installer.index('cp "$name" "/root/$name"'))
        self.assertNotIn('workercam-backup-', installer)
        self.assertIn("chmod 600 /root/workercam.env", installer)
        self.assertNotIn("workercam.env .talkback_token; do\n    cp", installer)
        self.assertNotIn("__STAGE__", installer)

    def test_camera_rejects_different_ssid_before_upload(self):
        code, output, _ = self.run_helper('deploy_maix.ps1', 'wrong-ssid', self.camera_arguments())
        self.assertNotEqual(code, 0, output)
        self.assertIn('same Wi-Fi SSID', output)
        self.assertNotIn('CAMERA_UPLOAD', output)
        self.assertNotIn('CAMERA_INSTALL', output)

    def test_camera_deployment_retains_explicit_a2dp_fallback(self):
        code, output, files = self.run_helper("deploy_maix.ps1",
            arguments=self.camera_arguments() + " -AudioProfile a2dp")
        self.assertEqual(code, 0, output)
        self.assertIn("AUDIO_PROFILE=a2dp", files["captured-camera.env"])

    def test_camera_install_failure_is_reported(self):
        code, output, _ = self.run_helper("deploy_maix.ps1", "install-failed", self.camera_arguments())
        self.assertNotEqual(code, 0)
        self.assertIn("Camera installation failed", output)


if __name__ == "__main__":
    unittest.main()
