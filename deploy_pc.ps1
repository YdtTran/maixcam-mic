[CmdletBinding()]
param([switch]$Build, [switch]$CheckOnly, [switch]$Recreate)

$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        throw 'Install Docker Desktop, select Linux containers, and open Docker Desktop first.'
    }
    Write-Host '[PC 1/5] Checking Docker Desktop Linux engine...'
    $engineType = & docker info --format '{{.OSType}}' 2>$null
    if ($LASTEXITCODE -ne 0 -or $engineType -ne 'linux') {
        throw 'Open Docker Desktop and wait for the Linux engine to be running, then try again.'
    }
    if (-not (Test-Path -LiteralPath .env -PathType Leaf)) {
        Copy-Item -LiteralPath .env.example -Destination .env
        throw 'Created .env. Set MAIX_IP to your camera address, save the file, then run this command again.'
    }
    if (-not (Test-Path -LiteralPath .talkback_token -PathType Leaf)) {
        $tokenBytes = New-Object byte[] 16
        $tokenGenerator = [Security.Cryptography.RandomNumberGenerator]::Create()
        try { $tokenGenerator.GetBytes($tokenBytes) } finally { $tokenGenerator.Dispose() }
        [IO.File]::WriteAllText((Join-Path $PSScriptRoot '.talkback_token'),
            ([BitConverter]::ToString($tokenBytes).Replace('-', '').ToLowerInvariant()))
        Write-Host 'Created the camera pairing token. Deploy MaixCAM with deploy_maix.ps1 to synchronize it.'
    }
    if ((Get-Content -LiteralPath .talkback_token -Raw).Trim() -notmatch '^[0-9a-fA-F]{32}$') {
        throw '.talkback_token must contain 32 hexadecimal characters. Restore the matching camera token.'
    }
    Write-Host '[PC 2/5] Validating configuration and pairing token...'
    $composeOptions = @('compose', '-f', 'compose.yaml')
    $configuration = & docker @composeOptions config --format json
    if ($LASTEXITCODE -ne 0) { throw 'Compose configuration is invalid. Check .env.' }
    $service = ($configuration | ConvertFrom-Json).services.server
    if ($service.environment.RTSP_TRANSPORT -ne 'tcp' -or $service.environment.STREAM_MODE -ne 'video') {
        throw 'Set RTSP_TRANSPORT=tcp and STREAM_MODE=video in .env for this Docker deployment.'
    }
    if ($env:OS -eq 'Windows_NT') {
        foreach ($listenerPid in @(Get-NetTCPConnection -LocalPort 8000,8554,8889 -State Listen -ErrorAction SilentlyContinue |
                Select-Object -ExpandProperty OwningProcess -Unique)) {
            $listenerProcess = Get-CimInstance Win32_Process -Filter "ProcessId = $listenerPid"
            if ($listenerProcess.Name -in @('python.exe', 'pythonw.exe', 'mediamtx.exe')) {
                throw 'A native media service owns a required port. Ask the installer to stop that project service before migrating to Docker.'
            }
        }
    }
    # Checks the project's container directly, so a different local HTTP server cannot pass.
    Write-Host '[PC 3/5] Checking port conflicts and recording status...'
    & (Join-Path $PSScriptRoot 'stop_docker_pc.ps1') -CheckOnly
    if ($CheckOnly) { Write-Host 'PC preflight passed.'; return }
    New-Item -ItemType Directory -Force -Path recordings | Out-Null
    $upOptions = @('up', '-d', '--wait', '--wait-timeout', '120')
    if ($Build) { $upOptions += '--build' }
    if ($Recreate) { $upOptions += '--force-recreate' }
    Write-Host '[PC 4/5] Building/starting Docker service and waiting for container health...'
    if ($Build) { Write-Host 'The first build downloads images and dependencies and can take several minutes.' }
    & docker @composeOptions @upOptions server
    if ($LASTEXITCODE -ne 0) {
        throw 'Docker deployment failed. Run: docker compose logs --tail 80 server'
    }
    Write-Host '[PC 5/5] Checking the operator page from Windows...'
    $operatorDeadline = (Get-Date).AddSeconds(30)
    do {
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8000/operator_test.html' -TimeoutSec 2
            $ready = $response.StatusCode -eq 200
        } catch { $ready = $false }
        if ($ready) { break }
        if ((Get-Date) -ge $operatorDeadline) {
            throw 'Docker started, but Windows cannot reach the operator page. Check Docker port forwarding and run: docker compose logs --tail 80 server'
        }
        Start-Sleep -Milliseconds 500
    } while ($true)
    Write-Host 'Operator UI verified: http://127.0.0.1:8000 (admin / admin)'
    Write-Host 'TCP video and separate microphone return on UDP 8004. Confirm live picture and sound in the browser.'
} finally { Pop-Location }
