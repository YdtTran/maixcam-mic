[CmdletBinding()]
param(
    [switch]$Build,
    [string]$MaixIp,
    [ValidateSet('tcp', 'udp')][string]$Transport,
    [ValidateSet('video', 'audio', 'combined')][string]$StreamMode
)

$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    # Only read operator settings; never execute .env as PowerShell.
    $operatorSettings = @{ MAIX_IP = '192.168.1.7'; RTSP_TRANSPORT = 'tcp'; STREAM_MODE = 'video' }
    if (Test-Path -LiteralPath .env) {
        foreach ($line in Get-Content -LiteralPath .env) {
            if ($line -match '^\s*(MAIX_IP|RTSP_TRANSPORT|STREAM_MODE)\s*=\s*(.*?)\s*$') {
                $operatorSettings[$Matches[1]] = $Matches[2].Trim('"', "'")
            }
        }
    }
    if (-not $MaixIp) { $MaixIp = $operatorSettings.MAIX_IP }
    if (-not $Transport) { $Transport = $operatorSettings.RTSP_TRANSPORT }
    if (-not $StreamMode) { $StreamMode = $operatorSettings.STREAM_MODE }
    $operatorAddress = $null
    if (-not [System.Net.IPAddress]::TryParse($MaixIp, [ref]$operatorAddress) -or
        $operatorAddress.AddressFamily -ne [System.Net.Sockets.AddressFamily]::InterNetwork) {
        throw 'MAIX_IP must be an IPv4 address.'
    }
    if ($Transport -notin @('tcp', 'udp') -or $StreamMode -notin @('video', 'audio', 'combined')) {
        throw 'Invalid RTSP_TRANSPORT or STREAM_MODE in .env.'
    }
    if ($StreamMode -ne 'video') {
        throw 'This startup helper preserves video-only operation. Earbuds audio remains pending; use app.py explicitly for audio experiments.'
    }
    $operatorPython = (Get-Command python -ErrorAction Stop).Source
    Get-Command ffmpeg -ErrorAction Stop | Out-Null
    if (-not (Test-Path -LiteralPath mediamtx.exe -PathType Leaf)) {
        throw 'Place mediamtx.exe in the project root before starting the native operator.'
    }
    if (-not (Test-Path -LiteralPath .talkback_token -PathType Leaf)) {
        throw 'Missing .talkback_token. Keep the existing token synchronized with MaixCAM.'
    }

    if ($Build) {
        Push-Location frontend
        try {
            if (-not (Test-Path -LiteralPath node_modules -PathType Container)) {
                & npm.cmd ci
                if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' }
            }
            & npm.cmd run build
            if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
        } finally { Pop-Location }
    }

    # Stop only this project's Docker operator, without restarting Docker or other services.
    if (Get-Command docker -ErrorAction SilentlyContinue) {
        try {
            $ErrorActionPreference = 'Continue'
            & docker info --format '{{.OSType}}' *> $null
            $operatorDockerReady = $LASTEXITCODE -eq 0
        } finally { $ErrorActionPreference = 'Stop' }
        if ($operatorDockerReady) {
            $operatorContainers = & docker compose -f compose.yaml -f compose.host.yaml ps --status running --quiet server
            if ($LASTEXITCODE -ne 0) { throw 'Could not inspect the Docker operator.' }
            if ($operatorContainers) {
                & docker compose -f compose.yaml -f compose.host.yaml stop server
                if ($LASTEXITCODE -ne 0) { throw 'Could not stop the Docker operator; native startup aborted.' }
            }
        }
    }

    New-Item -ItemType Directory -Force .runtime, recordings | Out-Null
    $operatorUrl = 'http://127.0.0.1:8000/operator_test.html'
    $operatorOwners = @(Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique)
    if ($operatorOwners.Count) {
        $operatorSavedPid = if (Test-Path .runtime/operator-native.pid) { (Get-Content .runtime/operator-native.pid -Raw).Trim() } else { '' }
        $operatorAppPath = Join-Path $PSScriptRoot 'app.py'
        foreach ($operatorOwner in $operatorOwners) {
            $operatorExisting = Get-CimInstance Win32_Process -Filter "ProcessId = $operatorOwner"
            $operatorCommand = $operatorExisting.CommandLine
            $operatorOwnApp = ($operatorCommand -like "*$operatorAppPath*" -or
                ($operatorSavedPid -eq [string]$operatorOwner -and $operatorCommand -match '(?i)(?:^|[\s\\/])app\.py(?:["\s]|$)'))
            if ($operatorExisting.Name -notin @('python.exe', 'pythonw.exe') -or -not $operatorOwnApp) {
                throw "Port 8000 belongs to another process (PID $operatorOwner). It was not stopped."
            }
            foreach ($operatorFlag in @("--maix-ip $MaixIp", "--rtsp-transport $Transport", "--stream-mode $StreamMode")) {
                if (-not $operatorCommand.Contains($operatorFlag)) {
                    throw 'The running operator uses different settings. Stop it with .\stop_operator.ps1 before restarting.'
                }
            }
        }
        $operatorResponse = Invoke-WebRequest -UseBasicParsing -Uri $operatorUrl -TimeoutSec 5
        if ($operatorResponse.StatusCode -ne 200) { throw 'The running operator failed its HTTP check.' }
        Write-Host "Operator already running: $operatorUrl (admin / admin)"
        return
    }

    $operatorProcess = Start-Process -FilePath $operatorPython -ArgumentList @(
        '-u', ('"' + (Join-Path $PSScriptRoot 'app.py') + '"'),
        '--maix-ip', $MaixIp, '--rtsp-transport', $Transport, '--stream-mode', $StreamMode
    ) -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $PSScriptRoot '.runtime/operator-native.stdout.log') `
        -RedirectStandardError (Join-Path $PSScriptRoot '.runtime/operator-native.stderr.log')
    $operatorProcess.Id | Set-Content .runtime/operator-native.pid
    $operatorDeadline = (Get-Date).AddSeconds(30)
    do {
        $operatorProcess.Refresh()
        if ($operatorProcess.HasExited) {
            throw 'Native operator exited. Read .runtime/operator-native.stdout.log and .runtime/operator-native.stderr.log.'
        }
        try {
            $operatorResponse = Invoke-WebRequest -UseBasicParsing -Uri $operatorUrl -TimeoutSec 2
            $operatorReady = $operatorResponse.StatusCode -eq 200
        } catch { $operatorReady = $false }
        if ($operatorReady) { break }
        if ((Get-Date) -ge $operatorDeadline) {
            throw 'Operator HTTP check timed out. Read .runtime/operator-native.* logs; use .\stop_operator.ps1 before retrying.'
        }
        Start-Sleep -Milliseconds 500
    } while ($true)
    Write-Host "Operator UI verified: $operatorUrl (admin / admin)"
    Write-Host "Native Windows: $Transport / $StreamMode; PID $($operatorProcess.Id). Stop with .\stop_operator.ps1."
} finally { Pop-Location }
