[CmdletBinding()]
param([switch]$Build)

$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    foreach ($operatorOwner in @(Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty OwningProcess -Unique)) {
        $operatorExisting = Get-CimInstance Win32_Process -Filter "ProcessId = $operatorOwner"
        if ($operatorExisting.Name -in @('python.exe', 'pythonw.exe') -and
            $operatorExisting.CommandLine -match '(?i)(?:^|[\s\\/])app\.py(?:["\s]|$)') {
            throw 'The native operator is already running. Stop it with .\stop_operator.ps1 before starting Docker.'
        }
    }
    & docker info --format '{{.OSType}}' 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        & docker desktop start
        if ($LASTEXITCODE -ne 0) { throw 'Could not start Docker Desktop.' }
    }
    $deadline = (Get-Date).AddSeconds(90)
    do {
        & docker info --format '{{.OSType}}' 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) { break }
        if ((Get-Date) -ge $deadline) { throw 'Docker engine did not become ready.' }
        Start-Sleep -Seconds 2
    } while ($true)

    $settingsPath = Join-Path $env:APPDATA 'Docker/settings-store.json'
    if (Test-Path -LiteralPath $settingsPath) {
        $settings = Get-Content -LiteralPath $settingsPath -Raw | ConvertFrom-Json
        if (-not $settings.hostNetworkingEnabled) {
            throw 'Enable host networking in Docker Desktop Settings > Resources > Network, then apply/restart.'
        }
    }
    # Docker Desktop's VM resets these Linux limits on engine/VM restarts.
    & wsl -d docker-desktop -u root -- sysctl -w net.core.rmem_max=4194304 net.core.wmem_max=4194304
    if ($LASTEXITCODE -ne 0) { throw 'Could not configure Docker VM UDP buffer limits.' }
    if (-not (Test-Path -LiteralPath .talkback_token -PathType Leaf)) {
        throw 'Missing .talkback_token file. Follow docs/docker-run-guide.md before starting.'
    }
    New-Item -ItemType Directory -Force recordings | Out-Null
    $composeOptions = @('compose', '-f', 'compose.yaml', '-f', 'compose.host.yaml')
    & docker @composeOptions config --quiet
    if ($LASTEXITCODE -ne 0) { throw 'Compose configuration validation failed.' }
    $upOptions = @('up', '-d')
    if ($Build) { $upOptions += '--build' }
    & docker @composeOptions @upOptions
    if ($LASTEXITCODE -ne 0) { throw 'Docker deployment failed.' }
    $operatorDeadline = (Get-Date).AddSeconds(30)
    do {
        try {
            $operatorResponse = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8000/operator_test.html' -TimeoutSec 2
            $operatorReady = $operatorResponse.StatusCode -eq 200
        } catch { $operatorReady = $false }
        if ($operatorReady) { break }
        if ((Get-Date) -ge $operatorDeadline) {
            throw 'Docker started, but Windows cannot reach the operator page. Run .\start_operator.ps1 for the native workaround; it stops only the Docker operator.'
        }
        Start-Sleep -Milliseconds 500
    } while ($true)
    Write-Host 'Operator UI verified: http://127.0.0.1:8000/operator_test.html (admin / admin)'
    Write-Host 'Media settings come from .env. TCP/video excludes earbuds microphone audio.'
} finally {
    Pop-Location
}
