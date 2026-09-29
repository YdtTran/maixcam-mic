[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9.-]*$')]
    [string]$MaixHost,
    [ValidatePattern('^[A-Za-z_][A-Za-z0-9_-]*$')]
    [string]$RemoteUser = 'root',
    [string]$RemoteDir = '/root',
    [string]$KeyPath,
    [string]$Password,
    [string]$HostKey
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$RemoteDir = $RemoteDir.TrimEnd('/')
if ($RemoteDir -notmatch '^/[A-Za-z0-9_./-]+$' -or $RemoteDir.Split('/') -contains '..') {
    throw 'RemoteDir must be an absolute directory using letters, numbers, _, -, . and / only.'
}
if ($KeyPath -and $Password) {
    throw 'Use either -KeyPath or -Password, not both.'
}

foreach ($command in @('plink', 'pscp')) {
    if (-not (Get-Command $command -ErrorAction SilentlyContinue)) {
        throw "'$command' was not found. Install PuTTY and add its folder to PATH."
    }
}

$sshOptions = @('-batch')
if ($HostKey) {
    $sshOptions += @('-hostkey', $HostKey)
}
if ($KeyPath) {
    if (-not (Test-Path -LiteralPath $KeyPath -PathType Leaf)) {
        throw "SSH key not found: $KeyPath"
    }
    $sshOptions += @('-i', (Resolve-Path -LiteralPath $KeyPath).Path)
}
elseif ($Password) {
    $sshOptions += @('-pw', $Password)
}

$files = @(
    @{ Source = 'maix/rtsp_av.py'; Destination = 'rtsp_av.py' },
    @{ Source = 'maix/soundpeats_auto.py'; Destination = 'soundpeats_auto.py' },
    @{ Source = 'maix/bluetooth_control.py'; Destination = 'bluetooth_control.py' },
    @{ Source = 'maix/air6_mic_stream.py'; Destination = 'air6_mic_stream.py' },
    @{ Source = 'maix/talkback_receiver.py'; Destination = 'talkback_receiver.py' },
    @{ Source = 'maix/rtsp_app.yaml'; Destination = 'rtsp_app.yaml' },
    @{ Source = 'maix/background_services.rc.local'; Destination = 'background_services.rc.local' },
    @{ Source = '.talkback_token'; Destination = '.talkback_token' }
)
foreach ($file in $files) {
    $source = Join-Path $PSScriptRoot $file.Source
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
        throw "Required upload file is missing: $source"
    }
}

$target = "${RemoteUser}@${MaixHost}"
Write-Host "[UPLOAD] Creating ${target}:$RemoteDir"
& plink @sshOptions $target "mkdir -p '$RemoteDir'"
if ($LASTEXITCODE -ne 0) {
    if (-not $HostKey) {
        Write-Warning 'If PuTTY reported an uncached host key, verify its fingerprint and retry with -HostKey <fingerprint>.'
    }
    throw "Remote directory creation failed (plink exit code $LASTEXITCODE)."
}

foreach ($file in $files) {
    $source = Join-Path $PSScriptRoot $file.Source
    $destination = "${target}:$RemoteDir/$($file.Destination)"
    Write-Host "[UPLOAD] $($file.Source) -> $destination"
    & pscp @sshOptions $source $destination
    if ($LASTEXITCODE -ne 0) {
        throw "Upload failed for $($file.Source) (pscp exit code $LASTEXITCODE)."
    }
}

# The camera runs this file with /bin/sh; remove Windows CRLF after transfer.
$remoteBoot = "$RemoteDir/background_services.rc.local"
$normalizeBoot = "tr -d '\015' < '$remoteBoot' > '$remoteBoot.tmp' && mv '$remoteBoot.tmp' '$remoteBoot' && sh -n '$remoteBoot'"
& plink @sshOptions $target $normalizeBoot
if ($LASTEXITCODE -ne 0) {
    throw "Could not normalize the MaixCAM boot script (plink exit code $LASTEXITCODE)."
}

Write-Host "[UPLOAD] Complete. Files are in $RemoteDir on $target."
