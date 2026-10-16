[CmdletBinding()]
param(
    [switch]$DryRun,
    [switch]$Force,
    [int]$WifiInterfaceIndex,
    [int]$UsbInterfaceIndex,
    [string]$UsbPeerIP,
    [string]$KeyPath,
    [Security.SecureString]$Password,
    [string]$CredentialPath,
    [ValidateRange(60, 3600)][int]$DeploymentTimeoutSeconds = 900
)

$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'NetworkDeployment.psm1') -Force -DisableNameChecking
$root = Split-Path -Parent $PSScriptRoot
$context = $null
$backup = $null
$cameraTouched = $false
$pcTouched = $false
$exitCode = 2
$deploymentId = [guid]::NewGuid().ToString('N')
$remoteBackup = "/root/workercam-backup-$deploymentId"
$configurationStatus = 'UNCHANGED'

# Read identity and only non-secret settings. No Bluetooth scan or MAC mutation.
$inventoryCommand = @'
set -eu
test -f /maixapp/apps/gen_app_info.py
test -f /root/rtsp_av.py
test -f /root/background_services.rc.local
python3 - <<'PY'
import glob, json, pathlib, re, subprocess
model = pathlib.Path('/proc/device-tree/model').read_text().strip('\0\n')
if not re.search(r'maix|licheerv', model, re.I):
    raise SystemExit('USB endpoint is not a recognized MaixCAM board: ' + model)
settings = {}
for line in pathlib.Path('/root/workercam.env').read_text().splitlines():
    if '=' in line:
        key, value = line.split('=', 1)
        if key in ('PC_IP', 'HEADSET_MAC', 'AUDIO_PROFILE'):
            if key in settings: raise SystemExit('Duplicate camera setting: ' + key)
            settings[key] = value.strip().strip('"\x27')
interfaces = []
for entry in glob.glob('/sys/class/net/*'):
    path = pathlib.Path(entry)
    if not (path / 'wireless').exists(): continue
    text = subprocess.check_output(['ip', '-4', 'addr', 'show', 'dev', path.name], text=True)
    for address in re.findall(r'inet ([0-9.]+)/', text):
        interfaces.append(dict(name=path.name, ip=address, mac=(path/'address').read_text().strip()))
print(json.dumps(dict(model=model, wifi=interfaces, settings=settings)))
PY
'@

function Invoke-ProjectScript {
    param([string]$Name, [string[]]$Arguments = @())
    $shell = (Get-Process -Id $PID).Path
    $output = Invoke-NetworkProcess $shell (@('-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
        '-File', (Join-Path $root $Name)) + $Arguments) -TimeoutSeconds $DeploymentTimeoutSeconds
    if ($output) { Write-Host $output }
}

function Get-DeploymentHash {
    $paths = @('Dockerfile', 'compose.yaml', 'app.py', 'mediamtx.yml', 'deploy_maix.ps1', 'deploy_pc.ps1', 'stop_docker_pc.ps1') |
        ForEach-Object { Get-Item -LiteralPath (Join-Path $root $_) }
    foreach ($directory in @('maix', 'pc', 'frontend/src', 'frontend/scripts', 'scripts')) {
        $paths += @(Get-ChildItem -LiteralPath (Join-Path $root $directory) -File -Recurse |
            Where-Object { $_.FullName -notmatch '[\\/]__pycache__[\\/]' -and $_.Name -ne 'operator_test.html' })
    }
    $paths += @(Get-ChildItem (Join-Path $root 'frontend') -File)
    $text = ($paths | Sort-Object FullName -Unique | ForEach-Object {
        $fileHash = [Security.Cryptography.SHA256]::Create()
        try {
            $_.FullName.Substring($root.Length) + ':' + [BitConverter]::ToString($fileHash.ComputeHash([IO.File]::ReadAllBytes($_.FullName)))
        } finally { $fileHash.Dispose() }
    }) -join "`n"
    $sha = [Security.Cryptography.SHA256]::Create()
    try { return [BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($text))).Replace('-', '') }
    finally { $sha.Dispose() }
}

function Test-Application {
    param([string]$CameraIP, [string]$UsbIP, [string]$LaptopIP, [string]$EarbudsMac)
    Write-Host 'Checking deployed settings, camera processes, Docker health and both media streams...'
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
    if (-not $CredentialPath) { $CredentialPath = Join-Path $root '.runtime/deploy-credential.xml' }
    if (-not $KeyPath -and -not $Password -and (Test-Path -LiteralPath $CredentialPath)) {
        $Password = (Import-Clixml -LiteralPath $CredentialPath).Password
    }
    $context = New-SshContext -KeyPath $KeyPath -Password $Password
    $envPath = Join-Path $root '.env'
    $envExisted = Test-Path -LiteralPath $envPath
    $originalText = if ($envExisted) { [IO.File]::ReadAllText($envPath) } else { [IO.File]::ReadAllText((Join-Path $root '.env.example')) }
    $existing = Read-EnvText $originalText
    $interfaces = @(Get-DeploymentInterfaces)
    Write-Verbose ($interfaces | Format-Table | Out-String)
    if (-not @($interfaces | Where-Object Kind -eq 'Wifi').Count) { throw 'No active physical Wi-Fi IPv4 interface. Connect laptop Wi-Fi and retry.' }
    $usbInterfaces = @($interfaces | Where-Object { $_.Kind -eq 'Usb' -and (-not $UsbInterfaceIndex -or $_.Index -eq $UsbInterfaceIndex) })
    if (-not $usbInterfaces.Count) { throw 'No USB RNDIS/NCM IPv4 adapter. Use a data cable; enable the camera USB network gadget, install its RNDIS/NCM driver in Device Manager, and enable DHCP. No serial COM port is required.' }
    $exitCode = 3
    $found = @()
    $failures = @()
    foreach ($usb in $usbInterfaces) {
        $hint = if ($UsbPeerIP) { $UsbPeerIP } else { $existing['MAIX_USB_IP'] }
        $peers = @(Get-UsbPeers $usb $hint)
        foreach ($peer in @(Find-OpenSshPeers $peers $usb.Address)) {
            try {
                Write-Host "Verifying MaixCAM over USB: $peer ($($usb.Name))"
                $inventory = Invoke-MaixSsh $context $peer $inventoryCommand | ConvertFrom-Json
                if (@($inventory.wifi).Count -ne 1) { throw 'Camera must have one active Wi-Fi IPv4 address; configure Wi-Fi on the camera first.' }
                $found += [pscustomobject]@{ Usb = $usb; Peer = $peer; Inventory = $inventory }
            } catch { $failures += "${peer}: $($_.Exception.Message)"; Write-Verbose $failures[-1] }
        }
    }
    if (-not $found.Count) {
        throw "No verified MaixCAM via USB. $($failures -join '; ') Check USB networking, camera SSH service, and root credentials. Verify the host key and connect once using ssh root@<USB-IP>; use -KeyPath or the documented credential setup. For USB subnets wider than /22, supply -UsbPeerIP from the camera network settings."
    }
    # One camera commonly exposes both NCM and RNDIS. Its Wi-Fi MAC identifies the same board.
    if (@($found | ForEach-Object { $_.Inventory.wifi[0].mac } | Sort-Object -Unique).Count -ne 1) {
        throw 'Several MaixCAMs found. Select one using -UsbInterfaceIndex and -UsbPeerIP.'
    }
    $selected = @($found | Sort-Object @{ Expression = { $_.Peer -ne $existing['MAIX_USB_IP'] } }, @{ Expression = { $_.Usb.Index } })[0]
    $camera = $selected.Inventory
    $wifiIP = [string]$camera.wifi[0].ip
    $wifiMac = [string]$camera.wifi[0].mac
    $usbIP = $selected.Peer
    if (-not (Test-IPv4 $wifiIP) -or $wifiMac -notmatch '^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$') { throw 'Camera returned invalid Wi-Fi IP/MAC.' }
    $laptop = Select-LaptopWifi $interfaces $wifiIP $WifiInterfaceIndex
    $earbuds = [string]$camera.settings.HEADSET_MAC
    if ($earbuds -notmatch '^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$') { throw 'Camera has no valid fixed HEADSET_MAC in /root/workercam.env. Restore the existing headset setting first.' }
    if ($existing['EARBUDS_MAC'] -and $existing.EARBUDS_MAC -cne $earbuds) { throw 'Local EARBUDS_MAC disagrees with camera HEADSET_MAC. Refusing to replace either fixed value.' }
    $audioProfile = [string]$camera.settings.AUDIO_PROFILE
    if ($audioProfile -notin @('sco', 'a2dp')) { throw 'Invalid existing camera AUDIO_PROFILE.' }
    # Reuse the verified USB host identity for Wi-Fi, rather than trusting an arbitrary Wi-Fi responder.
    $wifiContext = @{ Options = @($context.Options) + @('-b', $laptop.Address, '-o', "HostKeyAlias=$usbIP"); Environment = $context.Environment }
    $wifiIdentity = Invoke-MaixSsh $wifiContext $wifiIP $inventoryCommand | ConvertFrom-Json
    if ($wifiIdentity.wifi[0].mac -cne $wifiMac) { throw 'Wi-Fi endpoint identity differs from USB camera.' }
    Invoke-MaixSsh $context $usbIP "set -eu; ip route get $($laptop.Address) | grep 'src $wifiIP' >/dev/null" | Out-Null
    Write-Host "`nNetwork Discovery`n------------------------------"
    Write-Host "Laptop Wi-Fi IP:  $($laptop.Address)`nMaixCAM Wi-Fi IP: $wifiIP`nLaptop USB IP:    $($selected.Usb.Address)`nMaixCAM USB IP:   $usbIP`nMaixCAM Wi-Fi MAC: $wifiMac`nEarbuds MAC:      [UNCHANGED]"
    if ((Invoke-NetworkProcess docker.exe @('info', '--format', '{{.OSType}}')) -ne 'linux') { throw 'Start Docker Desktop with Linux containers.' }
    Invoke-NetworkProcess docker.exe @('compose', 'config', '--quiet') | Out-Null
    if (-not (Test-Path -LiteralPath .talkback_token)) { throw 'Missing .talkback_token. Restore the existing camera pairing token before deployment.' }
    Invoke-ProjectScript 'stop_docker_pc.ps1' @('-CheckOnly')
    $values = @{ LAPTOP_WIFI_IP = $laptop.Address; MAIXCAM_WIFI_IP = $wifiIP;
        LAPTOP_USB_IP = $selected.Usb.Address; MAIXCAM_USB_IP = $usbIP;
        MAIXCAM_WIFI_MAC = $wifiMac; EARBUDS_MAC = $earbuds; MAIX_IP = $wifiIP; MAIX_USB_IP = $usbIP }
    $updatedText = Update-EnvText $originalText $values
    $changed = -not $envExisted -or $updatedText -cne $originalText
    $changedKeys = @($values.Keys | Where-Object { -not $existing.ContainsKey($_) -or $existing[$_] -cne $values[$_] })
    $hash = Get-DeploymentHash
    $statePath = Join-Path $root '.runtime/deploy-state.json'
    $state = if (Test-Path -LiteralPath $statePath) { Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json } else { $null }
    $runningContainer = Invoke-NetworkProcess docker.exe @('compose', 'ps', '--quiet', 'server')
    $runtimeReady = $false
    if ($runningContainer) {
        $runtime = Invoke-NetworkProcess docker.exe @('inspect', $runningContainer) | ConvertFrom-Json
        $runtimeReady = $runtime[0].State.Health.Status -eq 'healthy' -and $wifiIP -in $runtime[0].Config.Cmd
    }
    $needsDeployment = $Force -or $changed -or -not $state -or $state.hash -ne $hash -or
        $camera.settings.PC_IP -ne $laptop.Address -or -not $runtimeReady
    Write-Host "`nPlan: changed network keys: $($changedKeys -join ', ')"
    Write-Host "Camera installation/reboot and Docker build: $needsDeployment"
    if ($DryRun) {
        Write-Host 'DRY RUN: discovery and read-only preflight verified. No configuration, services or camera files changed.'
        Write-Host 'Deployment: NOT RUN; application checks: NOT RUN.'
        exit 0
    }
    $exitCode = 4
    if ($needsDeployment) {
        $backup = Join-Path $root ".runtime/deploy-backups/$deploymentId"
        [void](New-Item -ItemType Directory -Path $backup -Force)
        if ($envExisted) { Copy-Item -LiteralPath $envPath -Destination (Join-Path $backup '.env') }
        $oldContainer = Invoke-NetworkProcess docker.exe @('compose', 'ps', '--all', '--quiet', 'server')
        $oldImage = $null
        $oldRunning = $false
        if ($oldContainer) {
            $oldImage = Invoke-NetworkProcess docker.exe @('inspect', '--format', '{{.Image}}', $oldContainer)
            $oldRunning = (Invoke-NetworkProcess docker.exe @('inspect', '--format', '{{.State.Running}}', $oldContainer)) -eq 'true'
            Invoke-NetworkProcess docker.exe @('tag', $oldImage, "workercam-rollback:$deploymentId") | Out-Null
        }
        [IO.File]::WriteAllText((Join-Path $backup 'recovery.json'), (@{ remoteBackup = $remoteBackup; usbIP = $usbIP;
            envExisted = $envExisted; oldImage = $oldImage; oldRunning = $oldRunning } | ConvertTo-Json))
        if ($changed) { [IO.File]::WriteAllText($envPath, $updatedText, (New-Object Text.UTF8Encoding $false)); $configurationStatus = 'UPDATED' }
        # Environment variables override .env in Compose: refuse a stale shell override.
        $resolved = Invoke-NetworkProcess docker.exe @('compose', 'config', '--format', 'json') | ConvertFrom-Json
        if ($wifiIP -notin $resolved.services.server.command -or $resolved.services.server.environment.MAIX_USB_IP -ne $usbIP) {
            throw 'Compose is overriding discovered addresses. Remove stale MAIX_IP/MAIX_USB_IP shell environment variables.'
        }
        Invoke-ProjectScript 'deploy_pc.ps1' @('-CheckOnly')
        Write-Host 'Installing MaixCAM using deploy_maix.ps1; then rebooting...'
        $cameraTouched = $true
        $cameraOptions = @{ MaixHost = $usbIP; PcIp = $laptop.Address; HeadsetMac = $earbuds;
            AudioProfile = $audioProfile; Reboot = $true; DeploymentId = $deploymentId }
        if ($KeyPath) { $cameraOptions.KeyPath = $KeyPath }
        if ($Password) { $cameraOptions.Password = $Password }
        & (Join-Path $root 'deploy_maix.ps1') @cameraOptions
        Write-Host 'Building and starting laptop services using deploy_pc.ps1...'
        $pcTouched = $true
        Invoke-ProjectScript 'deploy_pc.ps1' @('-Build', '-Recreate')
    }
    $exitCode = 5
    $deadline = [datetime]::UtcNow.AddSeconds(90)
    $returnRecoveryUsed = $false
    do {
        try { Test-Application $wifiIP $usbIP $laptop.Address $earbuds; break }
        catch {
            if ($needsDeployment -and -not $returnRecoveryUsed -and $_.Exception.Message -like 'Headset return verification failed:*') {
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
    [void](New-Item -ItemType Directory -Path (Split-Path $statePath -Parent) -Force)
    [IO.File]::WriteAllText($statePath, (@{ hash = $hash; verifiedAt = [datetime]::UtcNow.ToString('o') } | ConvertTo-Json))
    $status = if ($needsDeployment) { 'SUCCESS (deployed and verified)' } else { 'UNCHANGED (verified)' }
    Write-Host "`nDeployment`n------------------------------`nConfiguration:   $configurationStatus`nLaptop services: $status`nMaixCAM app:     $status`nConnectivity:    VERIFIED (video, headset return, talkback API)`nDeployment completed successfully."
    exit 0
} catch {
    Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
    if ($backup) {
        Write-Host "Recovering previous configuration. Backup: $backup"
        $rollbackFailed = $false
        try {
            if ($envExisted) { Copy-Item -LiteralPath (Join-Path $backup '.env') -Destination $envPath -Force }
            elseif (Test-Path -LiteralPath $envPath) { Remove-Item -LiteralPath $envPath }
            if ($cameraTouched) {
                $restore = @'
set -eu
backup=__BACKUP__
if test -d "$backup"; then
    for name in rtsp_av.py video_rtsp.py bluetooth_audio.py bluetooth_control.py headset_mic_stream.py talkback_receiver.py talkback_protocol.py rtsp_app.yaml background_services.rc.local workercam.env .talkback_token; do
        if test -f "$backup/$name"; then cp -p "$backup/$name" "/root/$name"; fi
    done
    for pair in 'rc.local:/etc/rc.local' 'auto_start.txt:/maixapp/auto_start.txt' 'app.info:/maixapp/apps/app.info'; do
        name=${pair%%:*}; destination=${pair#*:}
        if test -f "$backup/$name"; then cp -p "$backup/$name" "$destination"; fi
    done
    if test -d "$backup/maix_rtsp"; then cp -Rp "$backup/maix_rtsp/." /maixapp/apps/maix_rtsp/; fi
    sync
    nohup sh -c 'sleep 2; reboot' >/dev/null 2>&1 </dev/null &
fi
'@
                Invoke-MaixSsh $context $usbIP ($restore.Replace('__BACKUP__', $remoteBackup)) -TimeoutSeconds 60 | Out-Null
            }
            if ($pcTouched -and $oldImage) {
                $override = Join-Path $backup 'rollback.compose.yaml'
                [IO.File]::WriteAllText($override, "services:`n  server:`n    image: workercam-rollback:$deploymentId`n")
                Invoke-NetworkProcess docker.exe @('compose', '-f', 'compose.yaml', '-f', $override, 'up', '-d', '--no-build', '--wait', '--wait-timeout', '120', 'server') -TimeoutSeconds 180 | Out-Null
                if (-not $oldRunning) { Invoke-ProjectScript 'stop_docker_pc.ps1' }
            }
            Write-Host 'Previous configuration restored; camera reboot requested if installation had begun. Check old-address reachability before retrying.'
        } catch { $rollbackFailed = $true; Write-Host "ROLLBACK INCOMPLETE: $($_.Exception.Message). See scripts/README.md and $backup/recovery.json" }
        if ($rollbackFailed) { $exitCode = 6 }
    }
    Write-Host "Deployment failed (exit $exitCode). No success claimed."
    exit $exitCode
} finally { Close-SshContext $context; Pop-Location }
