[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    $operatorRecording = $null
    try {
        $operatorRecording = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/recordings/status' -TimeoutSec 2
    } catch { }
    if ($operatorRecording.recording) {
        throw 'Stop the recording in the operator UI before stopping the native stack so the MP4 can be finalized.'
    }
    # Reuse the supervisor's narrowly scoped process matching, not a global process kill.
    & python -c 'import app; app.stop_old_processes()'
    if ($LASTEXITCODE -ne 0) { throw 'Could not stop the native operator. Check its process and logs.' }
    if (Test-Path -LiteralPath .runtime/operator-native.pid) {
        Remove-Item -LiteralPath .runtime/operator-native.pid
    }
    Write-Host 'Native operator stopped. Docker and camera services were not restarted.'
} finally { Pop-Location }
