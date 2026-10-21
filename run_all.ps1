[CmdletBinding()]
param(
    [switch]$Build,
    [switch]$DeployMaix,
    [string]$MaixHost,
    [string]$PcIp,
    [string]$HeadsetMac,
    [string]$HostKey,
    [string]$KeyPath,
    [Security.SecureString]$Password,
    [ValidateSet('a2dp', 'sco')][string]$AudioProfile = 'sco',
    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'
if ($DeployMaix) {
    foreach ($parameterName in @('MaixHost', 'PcIp', 'HeadsetMac')) {
        if (-not (Get-Variable -Name $parameterName -ValueOnly)) {
            throw "-$parameterName is required with -DeployMaix. See the first-time setup in README.md."
        }
    }
}
Import-Module (Join-Path $PSScriptRoot 'scripts/NetworkDeployment.psm1') -DisableNameChecking
$maintenance = $null
$maintenanceSuccess = $false
try {
    & (Join-Path $PSScriptRoot 'deploy_pc.ps1') -CheckOnly
    $maintenance = Enter-ProjectMaintenance $PSScriptRoot
    if ($DeployMaix) {
        $cameraOptions = @{
            MaixHost = $MaixHost; PcIp = $PcIp; HeadsetMac = $HeadsetMac
            HostKey = $HostKey; AudioProfile = $AudioProfile; Reboot = $true
        }
        if ($KeyPath) { $cameraOptions.KeyPath = $KeyPath }
        if ($Password) { $cameraOptions.Password = $Password }
        & (Join-Path $PSScriptRoot 'deploy_maix.ps1') @cameraOptions
    }
    & (Join-Path $PSScriptRoot 'deploy_pc.ps1') -Build:$Build
    $maintenanceSuccess = $true
} finally { Exit-ProjectMaintenance $maintenance $maintenanceSuccess }
if (-not $NoBrowser) { Start-Process 'http://127.0.0.1:8000' }
