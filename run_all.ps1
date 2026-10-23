#Requires -RunAsAdministrator
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$HeadsetMac,
    [Parameter(Mandatory = $true)][string]$WifiSsid,
    [Security.SecureString]$WifiPassword,
    [int]$WifiInterfaceIndex,
    [int]$UsbInterfaceIndex,
    [string]$UsbPeerIP,
    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'
$options = @{} + $PSBoundParameters
[void]$options.Remove('NoBrowser')
& (Join-Path $PSScriptRoot 'scripts/deploy.ps1') @options
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
if (-not $NoBrowser) { Start-Process 'http://127.0.0.1:8000' }
