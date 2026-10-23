#Requires -RunAsAdministrator
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateScript({ $_ -notmatch '[\x00-\x1f\x7f]' -and [Text.Encoding]::UTF8.GetByteCount($_) -le 32 })]
    [ValidateNotNullOrEmpty()][string]$WifiSsid,
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$')][string]$HeadsetMac,
    [switch]$DryRun,
    [switch]$Force,
    [int]$WifiInterfaceIndex,
    [int]$UsbInterfaceIndex,
    [string]$UsbPeerIP,
    [string]$KeyPath,
    [Security.SecureString]$Password,
    [Security.SecureString]$WifiPassword,
    [string]$CredentialPath,
    [ValidateRange(60, 3600)][int]$DeploymentTimeoutSeconds = 900
)

$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'NetworkDeployment.psm1') -Force -DisableNameChecking
$root = Split-Path -Parent $PSScriptRoot
$context = $null
$exitCode = 2
$deploymentId = [guid]::NewGuid().ToString('N')
$configurationStatus = 'UNCHANGED'
$maintenance = $null
$maintenanceSuccess = $false

# Read hardware identity; a previous WorkerCam installation is not required.
$inventoryCommand = @'
set -eu
test -f /maixapp/apps/gen_app_info.py
python3 - <<'PY'
import codecs, glob, json, pathlib, re, subprocess
model = pathlib.Path('/proc/device-tree/model').read_text().strip('\0\n')
if not re.search(r'maix|licheerv', model, re.I):
    raise SystemExit('USB endpoint is not a recognized MaixCAM board: ' + model)
interfaces = []
for entry in glob.glob('/sys/class/net/*'):
    path = pathlib.Path(entry)
    if not (path / 'wireless').exists(): continue
    text = subprocess.check_output(['ip', '-4', 'addr', 'show', 'dev', path.name], text=True)
    addresses = re.findall(r'inet ([0-9.]+)/', text)
    if len(addresses) > 1: raise SystemExit('Camera Wi-Fi has multiple IPv4 addresses')
    status = dict(line.split('=', 1) for line in subprocess.check_output(
        ['wpa_cli', '-i', path.name, 'status'], text=True).splitlines() if '=' in line)
    interfaces.append(dict(name=path.name, ip=addresses[0] if addresses else None,
                           mac=(path/'address').read_text().strip(),
                           ssid=codecs.escape_decode(status.get('ssid', '').encode('utf-8'))[0].decode('utf-8'),
                           state=status.get('wpa_state')))
print(json.dumps(dict(model=model, wifi=interfaces)))
PY
'@

function Invoke-ProjectScript {
    param([string]$Name, [string[]]$Arguments = @())
    $shell = (Get-Process -Id $PID).Path
    Invoke-NetworkProcess $shell (@('-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
        '-File', (Join-Path $root $Name)) + $Arguments) -TimeoutSeconds $DeploymentTimeoutSeconds -StreamOutput | Out-Null
}

function Test-Application {
    param([string]$CameraIP, [string]$UsbIP, [string]$LaptopIP, [string]$EarbudsMac, [switch]$PreviousRelease)
    Write-Host 'Checking deployed settings, camera processes, Docker health and both media streams...'
    if (-not $PreviousRelease) {
        Assert-LaptopWifiSsid $WifiSsid $LaptopIP
        $wifiStatus = Invoke-MaixSsh $context $UsbIP $inventoryCommand | ConvertFrom-Json
        if ($wifiStatus.wifi[0].ssid -cne $WifiSsid -or $wifiStatus.wifi[0].state -ne 'COMPLETED' -or
            $wifiStatus.wifi[0].mac -ine $wifiMac) { throw 'Camera must remain on the laptop Wi-Fi SSID with the expected Wi-Fi MAC.' }
    }
    $remote = @'
set -eu
test "$(sed -n 's/^PC_IP=//p' /root/workercam.env)" = '__LAPTOP__'
test "$(sed -n 's/^HEADSET_MAC=//p' /root/workercam.env)" = '__EARBUDS__'
ip route get __LAPTOP__ | grep 'src __CAMERA__' >/dev/null
python3 - <<'PY'
import pathlib
commands = []
for path in pathlib.Path('/proc').glob('[0-9]*/cmdline'):
    try:
        commands.append(path.read_bytes().decode(errors='replace').split('\0'))
    except (OSError, ProcessLookupError):
        pass
for script in ('bluetooth_audio.py', 'talkback_receiver.py', 'headset_mic_stream.py'):
    matches = [args for args in commands if '/root/' + script in args]
    if len(matches) != 1:
        raise SystemExit('Expected one ' + script + ', found ' + str(len(matches)))
    if script == 'headset_mic_stream.py':
        args = matches[0]
        if '--target' not in args or args[args.index('--target') + 1] != '__LAPTOP__':
            raise SystemExit('Microphone sender has the wrong laptop destination')
PY
'@
    $remote = $remote.Replace('__LAPTOP__', $LaptopIP).Replace('__CAMERA__', $CameraIP).Replace('__EARBUDS__', $EarbudsMac)
    Invoke-MaixSsh $context $UsbIP $remote | Out-Null
    if (-not $PreviousRelease) {
        $protocol = Invoke-MaixSsh $context $UsbIP "cd /root; python3 -c 'import talkback_protocol; print(talkback_protocol.PROTOCOL_VERSION)'"
        if ($protocol.Trim() -ne 'TB3') { throw 'Installed camera protocol is incompatible; update PC and camera together to TB3.' }
        $protocolText = [IO.File]::ReadAllText((Join-Path $root 'pc/talkback_protocol.py')).Replace("`r`n", "`n")
        $sha = [Security.Cryptography.SHA256]::Create()
        try { $protocolHash = [BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($protocolText))).Replace('-', '') }
        finally { $sha.Dispose() }
        $installedHash = Invoke-MaixSsh $context $UsbIP 'python3 -c ''import hashlib,pathlib; print(hashlib.sha256(pathlib.Path("/root/talkback_protocol.py").read_bytes()).hexdigest())'''
        if ($installedHash.Trim() -ine $protocolHash) { throw 'Installed camera protocol payload is incompatible with this PC release.' }
        $cameraStatus = Invoke-RestMethod "http://${CameraIP}:8765/bluetooth/status" -TimeoutSec 5
        if ($cameraStatus.talkback_protocol -ne 'TB3') { throw 'Running camera protocol is incompatible; update PC and camera together to TB3.' }
    }
    $container = Invoke-NetworkProcess docker.exe @('compose', 'ps', '--quiet', 'server')
    if (-not $container) { throw 'Operator container is not running.' }
    $inspection = Invoke-NetworkProcess docker.exe @('inspect', $container) | ConvertFrom-Json
    if ($inspection[0].State.Health.Status -ne 'healthy' -or $CameraIP -notin $inspection[0].Config.Cmd) {
        throw 'Docker is unhealthy or still uses an old camera Wi-Fi address.'
    }
    $diagnostics = Invoke-RestMethod 'http://127.0.0.1:8000/api/camera/diagnostics' -TimeoutSec 10
    if ($diagnostics.media_ip -ne $CameraIP -or -not $diagnostics.wifi.reachable) { throw 'Application cannot reach camera Wi-Fi services.' }
    $talkback = Invoke-RestMethod 'http://127.0.0.1:8000/api/talkback/status' -TimeoutSec 5
    if (-not $talkback.available -or $talkback.error) { throw 'Talkback is unavailable.' }
    $control = Invoke-RestMethod 'http://127.0.0.1:8000/api/bluetooth/status' -TimeoutSec 5
    if ($control.error -or $control.selected -ine $EarbudsMac) { throw 'Camera control or fixed headset binding verification failed.' }
    if (-not $control.connected) { throw 'Headset is disconnected. Power it on; use pairing mode for a new headset.' }
    if (-not $PreviousRelease -and $talkback.protocol -ne 'TB3') { throw 'PC protocol is incompatible; update PC and camera together to TB3.' }
    if (-not $PreviousRelease -and @($inspection[0].Mounts | Where-Object Destination -eq '/app/.talkback_token').Count) {
        throw 'New PC still mounts a legacy token; recreate the compatible TB3 service.'
    }
    if (-not $PreviousRelease -and $env:OS -eq 'Windows_NT') {
        if (-not (Test-HostUdpListeners -Ports @(8004, 8005))) {
            Write-Host 'Windows host UDP listener 8004/8005 missing; checking recording status and recreating container...'
            Invoke-ProjectScript 'stop_docker_pc.ps1' @('-CheckOnly')
            Invoke-NetworkProcess docker.exe @('compose', 'up', '-d', '--force-recreate', '--no-deps', 'server') | Out-Null
            if (-not (Test-HostUdpListeners -Ports @(8004, 8005))) {
                throw 'Windows host UDP listener 8004/8005 remains missing after container recreation.'
            }
            Write-Host 'Recreated container; host UDP listeners verified (8004, 8005).'
        }
    }
    # Decoding verifies actual H.264 and G.711 delivery, including camera -> laptop Wi-Fi.
    foreach ($stream in @('maix01', 'headsetmic')) {
        try {
            Invoke-NetworkProcess docker.exe @('compose', 'exec', '-T', 'server', 'ffmpeg', '-v', 'error',
                '-rtsp_transport', 'tcp', '-i', "rtsp://127.0.0.1:8554/$stream", '-t', '1', '-f', 'null', '-') `
                -TimeoutSeconds 25 | Out-Null
        } catch {
            if ($stream -eq 'headsetmic') { throw "Headset return verification failed: $($_.Exception.Message)" }
            throw
        }
    }
}

Push-Location $root
try {
    Write-Host 'Preflight: Windows networking, OpenSSH, credentials and Docker'
    foreach ($command in @('ssh.exe', 'scp.exe', 'docker.exe', 'Get-NetAdapter', 'Get-NetIPAddress', 'Find-NetRoute')) {
        if (-not (Get-Command $command -ErrorAction SilentlyContinue)) { throw "Missing $command. Install Windows OpenSSH Client / Docker Desktop and run on Windows." }
    }
    if ($KeyPath -and $Password) { throw 'Choose -KeyPath or -Password.' }
    if ($CredentialPath -and -not $KeyPath -and -not $Password) {
        $Password = (Import-Clixml -LiteralPath $CredentialPath).Password
    }
    $context = New-SshContext -KeyPath $KeyPath -Password $Password -Fresh
    $envPath = Join-Path $root '.env'
    $originalText = [IO.File]::ReadAllText((Join-Path $root '.env.example'))
    $interfaces = @(Get-DeploymentInterfaces)
    Write-Verbose ($interfaces | Format-Table | Out-String)
    if (-not @($interfaces | Where-Object Kind -eq 'Wifi').Count) { throw 'No active physical Wi-Fi IPv4 interface. Connect laptop Wi-Fi and retry.' }
    $usbInterfaces = @($interfaces | Where-Object { $_.Kind -eq 'Usb' -and (-not $UsbInterfaceIndex -or $_.Index -eq $UsbInterfaceIndex) })
    if (-not $usbInterfaces.Count) { throw 'No USB RNDIS/NCM IPv4 adapter. Use a data cable; enable the camera USB network gadget, install its RNDIS/NCM driver in Device Manager, and enable DHCP. No serial COM port is required.' }
    $exitCode = 3
    $found = @()
    $failures = @()
    foreach ($usb in $usbInterfaces) {
        $hint = if ($UsbPeerIP) { $UsbPeerIP } else { $null }
        $peers = @(Get-UsbPeers $usb $hint)
        foreach ($peer in @(Find-OpenSshPeers $peers $usb.Address)) {
            try {
                Write-Host "Verifying MaixCAM over USB: $peer ($($usb.Name))"
                $inventory = Invoke-MaixSsh $context $peer $inventoryCommand | ConvertFrom-Json
                if (@($inventory.wifi).Count -ne 1) { throw 'Camera must have one Wi-Fi interface.' }
                $found += [pscustomobject]@{ Usb = $usb; Peer = $peer; Inventory = $inventory }
            } catch { $failures += "${peer}: $($_.Exception.Message)"; Write-Verbose $failures[-1] }
        }
    }
    if (-not $found.Count) {
        throw "No verified MaixCAM via USB. $($failures -join '; ') Check USB networking and the camera SSH service (automatic root login). A changed saved host key requires investigation. For USB subnets wider than /22, supply -UsbPeerIP from the camera network settings."
    }
    # One camera commonly exposes both NCM and RNDIS. Its Wi-Fi MAC identifies the same board.
    if (@($found | ForEach-Object { $_.Inventory.wifi[0].mac } | Sort-Object -Unique).Count -ne 1) {
        throw 'Several MaixCAMs found. Select one using -UsbInterfaceIndex and -UsbPeerIP.'
    }
    $selected = @($found | Sort-Object { $_.Usb.Index })[0]
    $camera = $selected.Inventory
    $wifiIP = [string]$camera.wifi[0].ip
    $wifiMac = [string]$camera.wifi[0].mac
    $usbIP = $selected.Peer
    if ($wifiMac -notmatch '^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$') { throw 'Camera returned invalid Wi-Fi MAC.' }
    $wifiCandidates = @($interfaces | Where-Object { $_.Kind -eq 'Wifi' -and
        (-not $WifiInterfaceIndex -or $_.Index -eq $WifiInterfaceIndex) -and
        (Get-LaptopWifiSsid $_.Index) -ceq $WifiSsid })
    if ($wifiCandidates.Count -ne 1) { throw 'WifiSsid must exactly match one connected laptop Wi-Fi SSID. Use -WifiInterfaceIndex if needed.' }
    $laptop = $wifiCandidates[0]
    $needsWifiSwitch = $camera.wifi[0].ssid -cne $WifiSsid -or
        $camera.wifi[0].state -ne 'COMPLETED' -or -not (Test-IPv4 $wifiIP)
    if ($needsWifiSwitch -and -not $DryRun -and -not $WifiPassword) { throw 'Supply -WifiPassword (Read-Host "Wi-Fi password" -AsSecureString) to join the laptop Wi-Fi.' }
    $earbuds = $HeadsetMac
    $audioProfile = 'sco'
    if ((Invoke-NetworkProcess docker.exe @('info', '--format', '{{.OSType}}')) -ne 'linux') { throw 'Start Docker Desktop with Linux containers.' }
    Write-Host "Required Wi-Fi SSID: $WifiSsid; MaixCAM Wi-Fi MAC: $wifiMac"
    if ($needsWifiSwitch) {
        if ($DryRun) {
            Write-Host 'DRY RUN: would switch MaixCAM to the laptop SSID over USB, persist Wi-Fi and rediscover its IP. No changes made.'
            exit 0
        }
        $exitCode = 4
        $maintenance = Enter-ProjectMaintenance $root -StopOnly -Fresh
        $joined = Set-MaixWifi $context $usbIP $WifiSsid $WifiPassword $wifiMac
        if ($joined.ssid -cne $WifiSsid -or $joined.mac -ine $wifiMac -or -not (Test-IPv4 $joined.ip)) {
            throw 'Camera did not join the required laptop Wi-Fi with the expected MAC/IP.'
        }
        $wifiIP = [string]$joined.ip
    }
    $laptop = Select-LaptopWifi $interfaces $wifiIP $laptop.Index
    # Reuse the verified USB host identity for Wi-Fi, rather than trusting an arbitrary Wi-Fi responder.
    $wifiContext = @{ Options = @($context.Options) + @('-b', $laptop.Address, '-o', "HostKeyAlias=$usbIP"); Environment = $context.Environment }
    $wifiIdentity = Invoke-MaixSsh $wifiContext $wifiIP $inventoryCommand | ConvertFrom-Json
    if ($wifiIdentity.wifi[0].mac -cne $wifiMac) { throw 'Wi-Fi endpoint identity differs from USB camera.' }
    if ($wifiIdentity.wifi[0].ssid -cne $WifiSsid -or $wifiIdentity.wifi[0].state -ne 'COMPLETED') {
        throw 'Camera Wi-Fi changed during discovery; reconnect both devices to the required SSID and retry.'
    }
    Invoke-MaixSsh $context $usbIP "set -eu; ip route get $($laptop.Address) | grep 'src $wifiIP' >/dev/null" | Out-Null
    Write-Host "`nNetwork Discovery`n------------------------------"
    Write-Host "Required Wi-Fi SSID (PC and MaixCAM): $WifiSsid"
    Write-Host "Laptop Wi-Fi IP:  $($laptop.Address)`nMaixCAM Wi-Fi IP: $wifiIP`nLaptop USB IP:    $($selected.Usb.Address)`nMaixCAM USB IP:   $usbIP`nMaixCAM Wi-Fi MAC: $wifiMac`nEarbuds MAC:      $earbuds"
    $values = @{ LAPTOP_WIFI_IP = $laptop.Address; MAIXCAM_WIFI_IP = $wifiIP;
        LAPTOP_USB_IP = $selected.Usb.Address; MAIXCAM_USB_IP = $usbIP;
        MAIXCAM_WIFI_MAC = $wifiMac; EARBUDS_MAC = $earbuds; MAIX_IP = $wifiIP; MAIX_USB_IP = $usbIP }
    $updatedText = Update-EnvText $originalText $values
    Write-Host 'Plan: stop ALL running Docker containers; reset WorkerCam configuration; reinstall/reboot camera; rebuild PC without cache. No rollback.'
    if ($DryRun) {
        Write-Host 'DRY RUN: discovery verified. No configuration, services or camera files changed. Deployment: NOT RUN.'
        exit 0
    }
    $exitCode = 4
    if (-not $maintenance) { $maintenance = Enter-ProjectMaintenance $root -StopOnly -Fresh }
    foreach ($name in @('MAIX_IP', 'MAIX_USB_IP', 'CAMERA_BASE_ROTATION', 'RTSP_TRANSPORT', 'STREAM_MODE', 'RECORDING_MODE')) {
        [Environment]::SetEnvironmentVariable($name, $null, 'Process')
    }
    [IO.File]::WriteAllText($envPath, $updatedText, (New-Object Text.UTF8Encoding $false))
    $configurationStatus = 'RESET'
    Set-HeadsetFirewallRule $wifiIP
    Write-Host 'Installing MaixCAM from source; then rebooting...'
    $cameraOptions = @{ MaixHost = $usbIP; PcIp = $laptop.Address; HeadsetMac = $earbuds;
        WifiSsid = $WifiSsid; AudioProfile = $audioProfile; Reboot = $true; DeploymentId = $deploymentId }
    if ($KeyPath) { $cameraOptions.KeyPath = $KeyPath }
    if ($Password) { $cameraOptions.Password = $Password }
    if ($WifiPassword) { $cameraOptions.WifiPassword = $WifiPassword }
    & (Join-Path $root 'deploy_maix.ps1') @cameraOptions
    Write-Host 'Building and starting laptop services without cache...'
    Invoke-ProjectScript 'deploy_pc.ps1' @('-Build', '-Recreate', '-NoCache')
    $exitCode = 5
    $deadline = [datetime]::UtcNow.AddSeconds(90)
    $returnRecoveryUsed = $false
    do {
        try { Test-Application $wifiIP $usbIP $laptop.Address $earbuds; break }
        catch {
            if ($_.Exception.Message -like '*incompatible*' -or $_.Exception.Message -like '*legacy token*' -or $_.Exception.Message -like '*remains missing*') { throw }
            if (-not $returnRecoveryUsed -and $_.Exception.Message -like 'Headset return verification failed:*') {
                $returnRecoveryUsed = $true
                Write-Host 'Headset return unavailable. Performing one recording-safe PC stop/start to refresh Docker UDP forwarding...'
                Invoke-ProjectScript 'stop_docker_pc.ps1'
                Invoke-ProjectScript 'deploy_pc.ps1'
                $deadline = [datetime]::UtcNow.AddSeconds(90)
                continue
            }
            if ([datetime]::UtcNow -ge $deadline) { throw }
            Write-Verbose $_.Exception.Message
            Write-Host 'Waiting for camera/audio publication...'
            Start-Sleep -Seconds 3
        }
    } while ($true)
    try {
        Invoke-MaixSsh $context $usbIP 'python3 -c ''from pathlib import Path; p=Path("/root/.talkback_token"); p.unlink(missing_ok=True)''' | Out-Null
        $obsoleteToken = Join-Path $root '.talkback_token'
        if (Test-Path -LiteralPath $obsoleteToken -PathType Leaf) { Remove-Item -LiteralPath $obsoleteToken -Force }
    } catch { Write-Warning 'TB3 verified; obsolete token cleanup failed. The ignored legacy file does not affect startup.' }
    $status = 'SUCCESS (fresh reinstall and verified)'
    $successSummary = "`nDeployment`n------------------------------`nConfiguration:   $configurationStatus`nLaptop services: $status`nMaixCAM app:     $status`nConnectivity:    VERIFIED (video, headset return, talkback API)`nDeployment completed successfully."
    $maintenanceSuccess = $true
    $exitCode = 0
} catch {
    Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host 'No rollback. Fix the reported cause and rerun this same fresh-install command.'
    Write-Host "Deployment failed (exit $exitCode). No success claimed."
} finally {
    try { Exit-ProjectMaintenance $maintenance $maintenanceSuccess }
    catch { Write-Host "Maintenance release failed: $($_.Exception.Message). Inspect the retained owner before recovery."; $exitCode = 6 }
    finally { Close-SshContext $context; Pop-Location }
}
if ($exitCode -eq 0) { Write-Host $successSummary }
exit $exitCode
