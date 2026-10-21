[CmdletBinding()]
param([Parameter(Mandatory=$true)][ValidatePattern('^[a-f0-9]{32}$')][string]$Owner)

$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'NetworkDeployment.psm1') -DisableNameChecking
$root = Split-Path -Parent $PSScriptRoot
$maintenance = Enter-ProjectMaintenance $root -StopOnly -RecoverOwner $Owner
Exit-ProjectMaintenance $maintenance $true
Write-Host 'Maintenance released. If the previous image was restored stopped, start it only after camera recovery is verified.'
