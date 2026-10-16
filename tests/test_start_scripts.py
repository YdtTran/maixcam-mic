"""Exercise deployment failures without touching Docker, SSH or the camera."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.name == "nt", "Windows PowerShell deployment helpers")
class DeploymentScriptTests(unittest.TestCase):
    def run_helper(self, name, case="ready", arguments=""):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for source in ROOT.glob("*.ps1"):
                shutil.copy2(source, root / source.name)
            for folder in ("maix", "pc"):
                (root / folder).mkdir()
                for source in (ROOT / folder).iterdir():
                    if source.suffix in (".py", ".yaml", ".local"):
                        shutil.copy2(source, root / folder / source.name)
            (root / ".env").write_text("MAIX_IP=192.0.2.1\n")
            (root / ".env.example").write_text("MAIX_IP=192.0.2.1\n")
            (root / ".talkback_token").write_text("00" * 16)
            (root / "test.ppk").write_text("mock key; not used for authentication")
            script = r'''
$ErrorActionPreference = 'Stop'
function Get-NetTCPConnection { return }
function docker {
    $global:LASTEXITCODE = 0
    $call = $args -join ' '
    if ($args[0] -eq 'info') { return 'linux' }
    if ($call -like '*config --format json*') {
        if ($env:DEPLOY_TEST_CASE -eq 'wrong-mode') {
            return '{"services":{"server":{"environment":{"RTSP_TRANSPORT":"udp","STREAM_MODE":"combined"}}}}'
        }
        return '{"services":{"server":{"environment":{"RTSP_TRANSPORT":"tcp","STREAM_MODE":"video"}}}}'
    }
    if ($call -like '*ps --all --quiet server*') {
        if ($env:DEPLOY_TEST_CASE -ne 'empty') { return 'test-container' }
        return
    }
    if ($args[0] -eq 'inspect') { return 'running' }
    if ($call -like '*exec -T server*') {
        switch ($env:DEPLOY_TEST_CASE) {
            'recording' { return '{"recording":true}' }
            'finalizing' { return '{"recording":false,"finalizing":true}' }
            'status-failed' { $global:LASTEXITCODE = 1; return }
            'invalid-status' { return '{}' }
            default { return '{"recording":false,"finalizing":false}' }
        }
    }
    if ($call -like '* up *') { Write-Host 'DOCKER_UP' }
    if ($call -like '* stop server') { Write-Host 'DOCKER_STOP_SERVER' }
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
function plink {
    $global:LASTEXITCODE = 0
    if ($args[-1] -like 'set -eu*') {
        Write-Host 'CAMERA_PREFLIGHT'
        if ($env:DEPLOY_TEST_CASE -eq 'preflight-failed') { $global:LASTEXITCODE = 1 }
    } elseif ($args[-1] -like "sh '*install.sh'") {
        Write-Host 'CAMERA_INSTALL'
        if ($env:DEPLOY_TEST_CASE -eq 'install-failed') { $global:LASTEXITCODE = 1 }
    } else { throw 'Unexpected remote command' }
}
function pscp {
    $global:LASTEXITCODE = 0
    Write-Host 'CAMERA_UPLOAD'
    if ($env:DEPLOY_TEST_CASE -eq 'upload-failed') { $global:LASTEXITCODE = 1 }
    $installer = @($args | Where-Object { $_ -like '*install.sh' })[0]
    Copy-Item -LiteralPath $installer -Destination (Join-Path $env:DEPLOY_TEST_ROOT 'captured-installer.sh')
    $stage = Split-Path -Parent $installer
    Copy-Item -LiteralPath (Join-Path $stage 'workercam.env') -Destination (Join-Path $env:DEPLOY_TEST_ROOT 'captured-camera.env')
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
            return result.returncode, result.stdout + result.stderr, captured

    def test_deploy_checks_windows_access_after_container_start(self):
        code, output, _ = self.run_helper("deploy_pc.ps1")
        self.assertEqual(code, 0, output)
        self.assertIn("DOCKER_UP", output)
        self.assertIn("Operator UI verified:", output)
        code, output, _ = self.run_helper("deploy_pc.ps1", "http-failed")
        self.assertNotEqual(code, 0)
        self.assertIn("Windows cannot reach", output)
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

    def test_legacy_combined_docker_settings_are_rejected(self):
        code, output, _ = self.run_helper("deploy_pc.ps1", "wrong-mode")
        self.assertNotEqual(code, 0)
        self.assertIn("RTSP_TRANSPORT=tcp", output)
        self.assertNotIn("DOCKER_UP", output)

    def test_run_all_validates_pc_before_camera_mutation(self):
        arguments = "-DeployMaix -NoBrowser " + self.camera_arguments()
        code, output, _ = self.run_helper("run_all.ps1", "recording", arguments)
        self.assertNotEqual(code, 0, output)
        self.assertNotIn("CAMERA_PREFLIGHT", output)
        self.assertNotIn("DOCKER_UP", output)

    def test_run_all_starts_pc_without_reinstalling_camera(self):
        code, output, _ = self.run_helper("run_all.ps1", arguments="-NoBrowser")
        self.assertEqual(code, 0, output)
        self.assertIn("DOCKER_UP", output)
        self.assertNotIn("CAMERA_PREFLIGHT", output)

    def camera_arguments(self):
        return ("-MaixHost 192.0.2.1 -PcIp 192.0.2.2 -HeadsetMac 'AA:BB:CC:DD:EE:FF' "
                "-HostKey 'SHA256:test' -KeyPath (Join-Path $env:DEPLOY_TEST_ROOT 'test.ppk')")

    def test_camera_preflight_or_upload_failure_cannot_install(self):
        for case in ("preflight-failed", "upload-failed"):
            with self.subTest(case=case):
                code, output, _ = self.run_helper("deploy_maix.ps1", case, self.camera_arguments())
                self.assertNotEqual(code, 0, output)
                self.assertNotIn("CAMERA_INSTALL", output)
                if case == "preflight-failed":
                    self.assertNotIn("CAMERA_UPLOAD", output)

    def test_camera_installer_stages_settings_and_backs_up_before_replacing(self):
        code, output, files = self.run_helper("deploy_maix.ps1", arguments=self.camera_arguments())
        self.assertEqual(code, 0, output)
        self.assertIn("CAMERA_INSTALL", output)
        self.assertIn("PC_IP=192.0.2.2", files["captured-camera.env"])
        self.assertIn("AUDIO_PROFILE=sco", files["captured-camera.env"])
        installer = files["captured-installer.sh"]
        self.assertLess(installer.index('cp -p /etc/rc.local'), installer.index('cp "$name" "/root/$name"'))
        self.assertIn("chmod 600 /root/.talkback_token", installer)
        self.assertNotIn("__STAGE__", installer)

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
