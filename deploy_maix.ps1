#Requires -RunAsAdministrator
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateScript({ $_ -notmatch '[\x00-\x1f\x7f]' -and [Text.Encoding]::UTF8.GetByteCount($_) -le 32 })]
    [ValidateNotNullOrEmpty()][string]$WifiSsid,
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9.-]*$')][string]$MaixHost,
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^\d{1,3}(\.\d{1,3}){3}$')][string]$PcIp,
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$')][string]$HeadsetMac,
    [string]$HostKey,
    [string]$KeyPath,
    [Security.SecureString]$Password,
    [Security.SecureString]$WifiPassword,
    [ValidateSet('a2dp', 'sco')][string]$AudioProfile = 'sco',
    [switch]$Reboot,
    [ValidatePattern('^[a-f0-9]{32}$')][string]$DeploymentId = [Guid]::NewGuid().ToString('N')
)

$ErrorActionPreference = 'Stop'
$parsedIp = $null
if (-not [Net.IPAddress]::TryParse($PcIp, [ref]$parsedIp)) { throw 'PcIp must be the PC LAN IPv4 address.' }
if ($KeyPath -and $Password) { throw 'Use either -KeyPath or -Password.' }
Import-Module (Join-Path $PSScriptRoot 'scripts/NetworkDeployment.psm1') -Force -DisableNameChecking
Assert-LaptopWifiSsid $WifiSsid $PcIp
foreach ($command in @('ssh.exe', 'scp.exe')) {
    if (-not (Get-Command $command -ErrorAction SilentlyContinue)) {
        throw "Install the Windows OpenSSH Client optional feature; $command is required for camera deployment."
    }
}
if ($KeyPath -and -not (Test-Path -LiteralPath $KeyPath -PathType Leaf)) { throw 'SSH key file was not found.' }
$files = @{
    'maix/rtsp_av.py' = 'rtsp_av.py'
    'maix/video_rtsp.py' = 'video_rtsp.py'
    'maix/bluetooth_audio.py' = 'bluetooth_audio.py'
    'maix/bluetooth_control.py' = 'bluetooth_control.py'
    'maix/headset_mic_stream.py' = 'headset_mic_stream.py'
    'maix/talkback_receiver.py' = 'talkback_receiver.py'
    'pc/talkback_protocol.py' = 'talkback_protocol.py'
    'maix/rtsp_app.yaml' = 'rtsp_app.yaml'
    'maix/background_services.rc.local' = 'background_services.rc.local'
}
foreach ($source in $files.Keys) {
    if (-not (Test-Path -LiteralPath (Join-Path $PSScriptRoot $source) -PathType Leaf)) {
        throw "Required camera file is missing: $source"
    }
}
Write-Host 'TB3 release: update PC and camera together using scripts/deploy.ps1; older PC releases cannot send compatible talkback.'
$tempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
$stagingPath = Join-Path $tempRoot "workercam-$deploymentId"
$remoteStage = "/root/workercam-deploy-$deploymentId"
$sshContext = $null
$target = "root@$MaixHost"
New-Item -ItemType Directory -Path $stagingPath | Out-Null
$maintenance = $null
$maintenanceSuccess = $false
try {
    $maintenance = Enter-ProjectMaintenance $PSScriptRoot
    $sshContext = New-SshContext -KeyPath $KeyPath -Password $Password -Fresh:(-not $HostKey)
    if ($HostKey) {
        # Compatibility for existing callers: also require the supplied fingerprint.
        $known = Invoke-NetworkProcess ssh-keygen.exe @('-F', $MaixHost)
        $knownFile = Join-Path $stagingPath 'known-host'
        [IO.File]::WriteAllText($knownFile, $known)
        $fingerprints = Invoke-NetworkProcess ssh-keygen.exe @('-lf', $knownFile, '-E', 'sha256')
        if ($HostKey -notin ($fingerprints -split '\s+')) { throw 'Supplied HostKey does not match OpenSSH known_hosts. Verify the camera host key.' }
    }
    Invoke-MaixSsh $sshContext $MaixHost "set -eu; test `"`$(id -u)`" = 0; command -v python3; command -v ffmpeg; command -v bluetoothctl; command -v bluealsa; command -v arecord; command -v aplay; test -f /maixapp/apps/gen_app_info.py; mkdir -m 700 '$remoteStage'" | Write-Host
    $cameraWifi = Set-MaixWifi $sshContext $MaixHost $WifiSsid $WifiPassword
    if ($cameraWifi.ssid -cne $WifiSsid -or $cameraWifi.mac -notmatch '^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$') {
        throw 'MaixCAM must use the same Wi-Fi SSID as the laptop and report a valid Wi-Fi MAC.'
    }
    Write-Host "MaixCAM Wi-Fi SSID: $WifiSsid; Wi-Fi MAC: $($cameraWifi.mac)"
    $ssidBase64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($WifiSsid))
    foreach ($source in $files.Keys) {
        $destination = Join-Path $stagingPath $files[$source]
        $content = [IO.File]::ReadAllText((Join-Path $PSScriptRoot $source)).Replace("`r`n", "`n")
        [IO.File]::WriteAllText($destination, $content, (New-Object Text.UTF8Encoding $false))
    }
    [IO.File]::WriteAllText((Join-Path $stagingPath 'workercam.env'),
        "PC_IP=$PcIp`nHEADSET_MAC=$HeadsetMac`nAUDIO_PROFILE=$AudioProfile`nWIFI_SSID_B64=$ssidBase64`nWIFI_MAC=$($cameraWifi.mac)`n")
    # All paths in the installer are fixed project paths or a generated hexadecimal id.
    $installer = @'
#!/bin/sh
set -eu
stage=__STAGE__
cd "$stage"
sh -n background_services.rc.local
python3 -c 'import ast,pathlib; [ast.parse(p.read_text()) for p in pathlib.Path(".").glob("*.py")]'
. ./workercam.env
python3 - <<'PY'
import base64, codecs, pathlib, subprocess
settings = dict(line.split('=', 1) for line in pathlib.Path('workercam.env').read_text().splitlines())
expected = base64.b64decode(settings['WIFI_SSID_B64'], validate=True).decode('utf-8')
matches = [p for p in pathlib.Path('/sys/class/net').iterdir()
           if (p/'wireless').exists() and (p/'address').read_text().strip() == settings['WIFI_MAC']]
if len(matches) != 1: raise SystemExit('Camera Wi-Fi MAC changed before installation')
status = dict(line.split('=', 1) for line in subprocess.check_output(
    ['wpa_cli', '-i', matches[0].name, 'status'], text=True).splitlines() if '=' in line)
actual = codecs.escape_decode(status.get('ssid', '').encode('utf-8'))[0].decode('utf-8')
if actual != expected or status.get('wpa_state') != 'COMPLETED':
    raise SystemExit('Camera must remain on the laptop Wi-Fi SSID during setup')
PY
if test "$AUDIO_PROFILE" = sco; then command -v hciconfig >/dev/null; fi
# Disable auto-start while replacing the application; reboot restores the launcher.
printf '' > /maixapp/auto_start.txt
python3 - <<'PY'
import os, pathlib, signal, time
scripts = {'/root/rtsp_av.py', '/root/video_rtsp.py', '/root/bluetooth_audio.py',
           '/root/talkback_receiver.py', '/root/headset_mic_stream.py',
           '/maixapp/apps/maix_rtsp/main.py', '/maixapp/apps/launcher/launcher_daemon'}
processes = {}
for path in pathlib.Path('/proc').glob('[0-9]*/cmdline'):
    try:
        processes[int(path.parent.name)] = path.read_bytes().decode(errors='replace').split('\0')
    except OSError:
        pass
victims = {pid for pid, args in processes.items() if scripts.intersection(args)}
# Include capture/playback subprocesses owned by the old application.
for path in pathlib.Path('/proc').glob('[0-9]*/status'):
    try:
        parent = int(next(line.split()[1] for line in path.read_text().splitlines() if line.startswith('PPid:')))
        if parent in victims:
            victims.add(int(path.parent.name))
    except (OSError, StopIteration):
        pass
for sig in (signal.SIGTERM, signal.SIGKILL):
    for pid in victims:
        try: os.kill(pid, sig)
        except ProcessLookupError: pass
    time.sleep(1)
for name in ('.asoundrc', '.talkback_token', '.bluetooth_device'):
    pathlib.Path('/root', name).unlink(missing_ok=True)
PY
for name in rtsp_av.py video_rtsp.py bluetooth_audio.py bluetooth_control.py headset_mic_stream.py talkback_receiver.py talkback_protocol.py rtsp_app.yaml background_services.rc.local workercam.env; do
    cp "$name" "/root/$name"
done
chmod 600 /root/workercam.env
mkdir -p /maixapp/apps/maix_rtsp
cp rtsp_av.py /maixapp/apps/maix_rtsp/main.py
cp rtsp_app.yaml /maixapp/apps/maix_rtsp/app.yaml
python3 /maixapp/apps/gen_app_info.py /maixapp/apps
printf maix_rtsp > /maixapp/auto_start.txt
cp background_services.rc.local /etc/rc.local
chmod 755 /etc/rc.local
sync
echo 'Camera installation complete. A reboot activates the installed programs.'
'@
    $installer = $installer.Replace('__STAGE__', $remoteStage).Replace('__ID__', $deploymentId).Replace("`r`n", "`n")
    [IO.File]::WriteAllText((Join-Path $stagingPath 'install.sh'), $installer, (New-Object Text.UTF8Encoding $false))
    $uploadPaths = @(Get-ChildItem -LiteralPath $stagingPath -File | Where-Object Name -ne 'known-host' | Select-Object -ExpandProperty FullName)
    Invoke-NetworkProcess scp.exe (@('-O') + @($sshContext.Options) + $uploadPaths + @("${target}:$remoteStage/")) -Environment $sshContext.Environment -TimeoutSeconds 120 | Write-Host
    Invoke-MaixSsh $sshContext $MaixHost "sh '$remoteStage/install.sh'" -TimeoutSeconds 120 | Write-Host
    if ($Reboot) {
        Invoke-MaixSsh $sshContext $MaixHost 'nohup sh -c "sleep 2; reboot" >/dev/null 2>&1 </dev/null &' | Out-Null
        Write-Host 'Camera reboot requested. Waiting for the video service...'
        Start-Sleep -Seconds 10
        $deadline = (Get-Date).AddSeconds(120)
        do {
            $client = New-Object Net.Sockets.TcpClient
            try {
                $connection = $client.BeginConnect($MaixHost, 8554, $null, $null)
                $videoReady = $connection.AsyncWaitHandle.WaitOne(2000) -and $client.Connected
                if ($videoReady) { $client.EndConnect($connection) }
            } catch { $videoReady = $false } finally { $client.Dispose() }
            if ($videoReady) { break }
            if ((Get-Date) -ge $deadline) { throw 'Camera installed, but video did not return within two minutes. Check camera power and network.' }
            Start-Sleep -Seconds 2
        } while ($true)
        Write-Host 'Camera video port is reachable. Verify picture, headset connection and sound in the operator page.'
    } else {
        Write-Host 'Reboot the camera before using the new files, or rerun with -Reboot when ready.'
    }
    $maintenanceSuccess = $true
} finally {
    try { Exit-ProjectMaintenance $maintenance $maintenanceSuccess } finally {
    Close-SshContext $sshContext
    $resolvedStaging = [IO.Path]::GetFullPath($stagingPath)
    if ($resolvedStaging -ne (Join-Path $tempRoot "workercam-$deploymentId")) { throw 'Unexpected temporary cleanup path.' }
    Remove-Item -LiteralPath $resolvedStaging -Recurse -Force
    }
}
