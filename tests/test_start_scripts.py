"""Exercise Docker startup reporting without starting Docker or media processes."""

import os
from pathlib import Path
import subprocess
import unittest


@unittest.skipUnless(os.name == "nt", "Windows PowerShell startup helpers")
class StartupScriptTests(unittest.TestCase):
    def run_docker_helper(self, reachable):
        script = r'''
$ErrorActionPreference = 'Stop'
function Get-NetTCPConnection { return }
function docker { $global:LASTEXITCODE = 0 }
function wsl { $global:LASTEXITCODE = 0 }
function Test-Path {
    param($LiteralPath, $PathType)
    # These prerequisite checks are covered by the real launcher smoke check.
    return $false -eq ([string]$LiteralPath -like '*settings-store.json')
}
$global:operatorTestClock = 0
function Get-Date {
    $global:operatorTestClock++
    $date = [datetime]'2026-10-10T00:00:00'
    if ($global:operatorTestClock -ge 3) { return $date.AddMinutes(5) }
    return $date
}
function Invoke-WebRequest {
    if ($env:OPERATOR_TEST_REACHABLE -eq '1') { return @{ StatusCode = 200 } }
    throw 'Simulated connection refused'
}
try {
    & (Join-Path $env:OPERATOR_TEST_ROOT 'start_docker.ps1')
    if ($env:OPERATOR_TEST_REACHABLE -ne '1') { throw 'Unexpected startup success' }
} catch {
    if ($env:OPERATOR_TEST_REACHABLE -eq '1' -or
        $_.Exception.Message -notlike 'Docker started, but Windows cannot reach*') { throw }
    Write-Output 'EXPECTED: HTTP failure rejected'
}
'''
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            env={**os.environ, "OPERATOR_TEST_ROOT": str(Path(__file__).resolve().parents[1]),
                 "OPERATOR_TEST_REACHABLE": "1" if reachable else "0"},
            capture_output=True, text=True, timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout

    def test_docker_cannot_report_success_when_windows_http_fails(self):
        output = self.run_docker_helper(False)
        self.assertIn("EXPECTED: HTTP failure rejected", output)
        self.assertNotIn("Operator UI verified:", output)

    def test_docker_reports_success_after_windows_http_check(self):
        output = self.run_docker_helper(True)
        self.assertIn("Operator UI verified:", output)

    def test_native_stop_refuses_to_interrupt_recording(self):
        script = r'''
$ErrorActionPreference = 'Stop'
function Invoke-RestMethod { return @{ recording = $true } }
function python { throw 'Process cleanup must not run during recording' }
try {
    & (Join-Path $env:OPERATOR_TEST_ROOT 'stop_operator.ps1')
    throw 'Unexpected stop success'
} catch {
    if ($_.Exception.Message -notlike 'Stop the recording in the operator UI*') { throw }
    Write-Output 'EXPECTED: active recording protected'
}
'''
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            env={**os.environ, "OPERATOR_TEST_ROOT": str(Path(__file__).resolve().parents[1])},
            capture_output=True, text=True, timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
