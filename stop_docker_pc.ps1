[CmdletBinding()]
param([switch]$CheckOnly)

$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
Import-Module (Join-Path $PSScriptRoot 'scripts/NetworkDeployment.psm1') -DisableNameChecking
$maintenance = $null
$maintenanceSuccess = $false
try {
    if ($CheckOnly) { [void](Get-MaintenanceOperator $PSScriptRoot) }
    $composeOptions = @('compose', '-f', 'compose.yaml')
    $containers = @(& docker @composeOptions ps --all --quiet server)
    if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect the Docker project. Check that Docker Desktop is running.' }
    foreach ($container in $containers) {
        if (-not $container) { continue }
        $state = & docker inspect --format '{{.State.Status}}' $container
        if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect the operator container.' }
        if ($state -eq 'running') {
            $statusJson = & docker @composeOptions exec -T server python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/api/recordings/status', timeout=3).read().decode())"
            if ($LASTEXITCODE -ne 0) {
                throw 'Cannot verify recording status. Open the operator page and finish recording before stopping or updating.'
            }
            $recordingStatus = $statusJson | ConvertFrom-Json
            if ($null -eq $recordingStatus.recording) { throw 'Invalid recording status; refusing to stop or update.' }
            if ($recordingStatus.recording -or $recordingStatus.finalizing) {
                throw 'Stop the recording in the operator UI and wait for finalization before stopping or updating Docker.'
            }
        } elseif ($state -notin @('exited', 'created')) {
            throw "Operator container is $state; recording status cannot be verified. Inspect Docker logs before stopping or updating."
        }
    }
    if (-not $CheckOnly) {
        $maintenance = Enter-ProjectMaintenance $PSScriptRoot -StopOnly
        & docker @composeOptions stop server
        if ($LASTEXITCODE -ne 0) { throw 'Docker could not stop the operator.' }
        Write-Host 'PC operator stopped. Saved recordings remain in the recordings folder.'
        $maintenanceSuccess = $true
    }
} finally { try { Exit-ProjectMaintenance $maintenance $maintenanceSuccess } finally { Pop-Location } }
