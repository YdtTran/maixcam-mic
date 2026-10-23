"""Run PowerShell discovery/configuration helpers without network or Docker mutations."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.name == "nt", "Windows PowerShell networking")
class NetworkDeploymentTests(unittest.TestCase):
    def test_docker_network_overlap_is_rejected_without_mutation(self):
        self.run_ps(r'''
& $module {
    function script:Invoke-NetworkProcess {
        param($FilePath, $Arguments)
        if (($Arguments -join ' ') -eq 'network ls --quiet') { return "fixture-network`nother-network" }
        if (($Arguments -join ' ') -eq 'network inspect fixture-network other-network') {
            return '[{"Name":"n8n_default","IPAM":{"Config":[{"Subnet":"172.20.0.0/16"},{"Subnet":"fd00::/64"}]}}]'
        }
        throw 'Unexpected Docker mutation'
    }
    Assert-DockerNetworkRoute '192.168.1.7'
    foreach ($address in @('172.20.10.2', '172.20.10.7')) {
        try { Assert-DockerNetworkRoute $address; throw 'Overlap accepted' }
        catch {
            if ($_.Exception.Message -notlike "*n8n_default*172.20.0.0/16*overlaps*") { throw }
        }
    }
}
''')

    def test_child_process_uses_powershell_location_after_directory_change(self):
        with tempfile.TemporaryDirectory() as directory:
            self.run_ps(r'''
Push-Location '__DIRECTORY__'
try {
    $shell = Join-Path $PSHOME 'powershell.exe'
    $location = Invoke-NetworkProcess $shell @('-NoProfile','-NonInteractive','-Command','(Get-Location).Path')
    if ($location -ne (Get-Location).Path) { throw 'Child process ignored PowerShell location' }
} finally { Pop-Location }
'''.replace('__DIRECTORY__', directory))

    def test_camera_ssh_defaults_to_root_without_prompt_and_cleans_helper(self):
        self.run_ps(r'''
$context = New-SshContext
$directory = $context.Directory
try {
    $credential = Import-Clixml -LiteralPath $context.Environment.WORKERCAM_SSH_CREDENTIAL
    if ($credential.UserName -cne 'root' -or $credential.GetNetworkCredential().Password -cne 'root') {
        throw 'Wrong default camera credentials'
    }
    if ('StrictHostKeyChecking=accept-new' -notin $context.Options -or
        'PreferredAuthentications=password' -notin $context.Options -or
        $context.Environment.SSH_ASKPASS_REQUIRE -ne 'force') { throw 'Camera login can prompt' }
    $helper = Get-Content -LiteralPath (Join-Path $directory 'askpass.ps1') -Raw
    if ($helper.Contains('root')) { throw 'Plaintext credential embedded in helper' }
} finally { Close-SshContext $context }
if (Test-Path -LiteralPath $directory) { throw 'Temporary SSH credential retained' }
$key = Join-Path $env:TEMP ('workercam-key-test-' + [guid]::NewGuid().ToString('N'))
try {
    Set-Content -LiteralPath $key 'test key'
    $context = New-SshContext -KeyPath $key
    if ($context.Directory -or 'BatchMode=yes' -notin $context.Options) { throw 'Explicit key override was replaced' }
} finally { Remove-Item -LiteralPath $key }
''')

    def test_wifi_credentials_use_ssh_stdin_and_preserve_ssid(self):
        self.run_ps(r'''
& $module {
    function script:Invoke-MaixSsh {
        param($Context,$Address,$Command,$TimeoutSeconds)
        if ($Command -notmatch "(?s)<<'WORKERCAM_WIFI'\n(.*)\nWORKERCAM_WIFI$") { throw 'Missing stdin payload' }
        $data = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($Matches[1])) | ConvertFrom-Json
        if ($data.ssid -cne 'Test "WiFi" & $(noop)' -or $data.password -cne 'sample-password' -or
            $data.mac -ne 'ab:cd:ef:01:23:45' -or $Address -ne '10.9.8.1') { throw 'Credential/identity payload damaged' }
        if ($Command.Split("`n")[0] -like '*sample-password*') { throw 'Password in command arguments' }
        return '{"ssid":"Test \"WiFi\" & $(noop)","mac":"ab:cd:ef:01:23:45","ip":"192.0.2.1"}'
    }
    $password = New-Object Security.SecureString; 'sample-password'.ToCharArray() | ForEach-Object { $password.AppendChar($_) }
    $result = Set-MaixWifi @{} '10.9.8.1' 'Test "WiFi" & $(noop)' $password 'ab:cd:ef:01:23:45'
    if ($result.ip -ne '192.0.2.1') { throw 'Wi-Fi setup result missing' }
}
''')

    def test_fresh_ssh_uses_disposable_host_keys(self):
        self.run_ps(r'''
$context = New-SshContext -Fresh
$directory = $context.Directory
try {
    $expected = 'UserKnownHostsFile=' + (Join-Path $directory 'known_hosts')
    if ($expected -notin $context.Options -or 'GlobalKnownHostsFile=NUL' -notin $context.Options) {
        throw 'Fresh install still uses old saved SSH keys'
    }
} finally { Close-SshContext $context }
if (Test-Path -LiteralPath $directory) { throw 'Fresh SSH state retained' }
''')

    def test_setup_switches_camera_over_usb_and_dry_run_is_read_only(self):
        for dry_run in (False, True):
            with self.subTest(dry_run=dry_run), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.deployment_fixture(root)
                runner = root / 'run.ps1'
                if not dry_run:
                    runner.write_text(runner.read_text().replace(
                        "& (Join-Path $PSScriptRoot 'scripts/deploy.ps1') @args",
                        "$wifiPassword = New-Object Security.SecureString; 'sample-password'.ToCharArray() | ForEach-Object { $wifiPassword.AppendChar($_) }\n"
                        "& (Join-Path $PSScriptRoot 'scripts/deploy.ps1') -WifiPassword $wifiPassword @args"))
                original = (root / '.env').read_bytes()
                result = self.run_deployment(root, 'wrong-camera-ssid', ('-DryRun',) if dry_run else ())
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertNotIn('sample-password', result.stdout + result.stderr)
                self.assertIn('ab:cd:ef:01:23:45', result.stdout)
                if dry_run:
                    self.assertFalse((root / '.runtime/actions').exists())
                    self.assertEqual((root / '.env').read_bytes(), original)
                else:
                    actions = (root / '.runtime/actions').read_text()
                    self.assertLess(actions.index('WIFI_SWITCH'), actions.index('CAMERA_DEPLOY'))
                    self.assertFalse((root / 'recordings/.maintenance.json').exists())

    def test_laptop_ssid_uses_selected_adapter_and_rejects_missing_or_wrong_network(self):
        self.run_ps(r'''
& $module {
    function Get-NetAdapter { [pscustomobject]@{ifIndex=18;InterfaceGuid='11111111-1111-1111-1111-111111111111'} }
    function netsh.exe {
        $global:LASTEXITCODE=0
        @'
    GUID : 22222222-2222-2222-2222-222222222222
    SSID : Wrong Adapter
    GUID : 11111111-1111-1111-1111-111111111111
    SSID : Test "WiFi" & Network
    AP BSSID : ab:cd:ef:01:23:45
'@
    }
    if ((Get-LaptopWifiSsid 18) -cne 'Test "WiFi" & Network') { throw 'SSID damaged or wrong adapter' }
    function Get-DeploymentInterfaces { [pscustomobject]@{Kind='Wifi';Address='192.0.2.2';Index=18} }
    Assert-LaptopWifiSsid 'Test "WiFi" & Network' '192.0.2.2'
    foreach ($ip in @('192.0.2.2','192.0.2.9')) {
        try { Assert-LaptopWifiSsid 'Wrong Network' $ip; throw 'Mismatch accepted' }
        catch { if ($_.Exception.Message -notlike '*exactly match*') { throw } }
    }
    function netsh.exe { $global:LASTEXITCODE=0; 'Wi-Fi is disconnected' }
    try { Get-LaptopWifiSsid 18; throw 'Missing SSID accepted' }
    catch { if ($_.Exception.Message -notlike '*no readable connected SSID*') { throw } }
}
''')

    def test_setup_rejects_host_or_camera_ssid_mismatch_without_mutations(self):
        for case in ('wrong-host-ssid', 'wrong-camera-ssid'):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.deployment_fixture(root)
                original = (root / '.env').read_bytes()
                result = self.run_deployment(root, case)
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertRegex(result.stdout + result.stderr, 'SSID|WifiPassword')
                self.assertEqual((root / '.env').read_bytes(), original)
                self.assertFalse((root / '.runtime/actions').exists())

    def test_firewall_creates_then_updates_camera_scope_without_duplicates(self):
        self.run_ps(r'''
& $module {
    $script:rule = $null
    $script:created = 0
    $script:updated = 0
    function script:Get-NetFirewallRule { if ($script:rule) { return $script:rule } }
    function script:New-NetFirewallRule {
        param($DisplayName,$Direction,$Action,$Protocol,$LocalPort,$RemoteAddress,$Profile,$Enabled,$ErrorAction)
        if ($DisplayName -ne 'MaixCAM headset UDP from camera' -or $Direction -ne 'Inbound' -or
            $Action -ne 'Allow' -or $Protocol -ne 'UDP' -or ($LocalPort -join ',') -ne '8004,8005' -or
            $Profile -ne 'Any' -or $Enabled -ne 'True') { throw 'Wrong firewall settings' }
        $script:rule = [pscustomobject]@{DisplayName=$DisplayName; RemoteAddress=$RemoteAddress}
        $script:created++
    }
    function script:Set-NetFirewallRule {
        param([Parameter(ValueFromPipeline)]$InputObject,$Direction,$Action,$Protocol,$LocalPort,$RemoteAddress,$Profile,$Enabled)
        process { $InputObject.RemoteAddress = $RemoteAddress; $script:updated++ }
    }
    Set-HeadsetFirewallRule '192.0.2.1'
    Set-HeadsetFirewallRule '192.0.2.9'
    Set-HeadsetFirewallRule '192.0.2.9'
    if ($script:created -ne 1 -or $script:updated -ne 2 -or $script:rule.RemoteAddress -ne '192.0.2.9') {
        throw 'Firewall rule duplicated or camera scope stale'
    }
    try { Set-HeadsetFirewallRule 'Any'; throw 'Invalid address accepted' }
    catch { if ($_.Exception.Message -notlike '*valid camera IPv4*') { throw } }
}
''')

    def test_host_lock_nested_calls_competing_process_and_explicit_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'compete.ps1').write_text(r'''
$ErrorActionPreference='Stop'
Import-Module '__MODULE__' -DisableNameChecking
try { Enter-ProjectMaintenance '__ROOT__'; throw 'Competing process entered' }
catch { if ($_.Exception.Message -notlike '*Another project maintenance*') { throw }; 'COMPETITOR_REFUSED' }
'''.replace('__MODULE__', str(ROOT / 'scripts/NetworkDeployment.psm1')).replace('__ROOT__', str(root)))
            (root / 'nested.ps1').write_text(r'''
$ErrorActionPreference='Stop'
Import-Module '__MODULE__' -DisableNameChecking
$nested = Enter-ProjectMaintenance '__ROOT__'
if ($nested.Outer) { throw 'Child acquired outer ownership' }
Exit-ProjectMaintenance $nested $true
'NESTED_OK'
'''.replace('__MODULE__', str(ROOT / 'scripts/NetworkDeployment.psm1')).replace('__ROOT__', str(root)))
            self.run_ps(r'''
& $module { function script:Get-MaintenanceOperator { return 'stopped' } }
$root = '__ROOT__'
$context = Enter-ProjectMaintenance $root -StopOnly
$marker = Join-Path $root 'recordings/.maintenance.json'
$shell = Join-Path $PSHOME 'powershell.exe'
try {
    $nested = Enter-ProjectMaintenance $root
    if ($nested.Outer -or $nested.Owner -cne $context.Owner) { throw 'Nested ownership changed' }
    Exit-ProjectMaintenance $nested $true
    if (-not (Test-Path $marker)) { throw 'Nested call released marker' }
    $result = Invoke-NetworkProcess $shell @('-NoProfile','-File',(Join-Path $root 'nested.ps1'))
    if ($result.Trim() -ne 'NESTED_OK') { throw 'Child did not share maintenance' }
    $result = Invoke-NetworkProcess $shell @('-NoProfile','-File',(Join-Path $root 'compete.ps1')) -Environment @{WORKERCAM_MAINTENANCE_OWNER=''}
    if ($result.Trim() -ne 'COMPETITOR_REFUSED') { throw 'Competing process entered' }
} finally { Exit-ProjectMaintenance $context $false }
try { Enter-ProjectMaintenance $root -StopOnly; throw 'Stale owner was replaced' }
catch { if ($_.Exception.Message -notlike '*Maintenance marker retained*') { throw } }
try { Enter-ProjectMaintenance $root -RecoverOwner ('b' * 32); throw 'Foreign owner recovered' }
catch { if ($_.Exception.Message -notlike '*Maintenance marker retained*') { throw } }
$recovery = Enter-ProjectMaintenance $root -RecoverOwner $context.Owner -StopOnly
Exit-ProjectMaintenance $recovery $true
if (Test-Path $marker) { throw 'Recovery failed to release marker' }
'''.replace('__ROOT__', str(root)))

    def run_ps(self, body, timeout=20):
        script = "$ErrorActionPreference='Stop'\n"
        script += f"$module = Import-Module '{ROOT / 'scripts/NetworkDeployment.psm1'}' -Force -PassThru -DisableNameChecking\n"
        script += body
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.ps1"
            path.write_text(script)
            result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-File", str(path)],
                                    capture_output=True, text=True, timeout=timeout)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout

    def test_updates_named_keys_only_and_is_idempotent(self):
        self.run_ps(r'''
$original = "# retained`r`nMAIX_IP=192.0.2.1`r`nOTHER=http://192.0.2.1`r`nEARBUDS_MAC=aa:BB:cc:DD:ee:FF`r`n"
$values = @{ MAIX_IP='192.0.2.9'; LAPTOP_WIFI_IP='192.0.2.2' }
$changed = Update-EnvText $original $values
if ($changed -notmatch 'OTHER=http://192.0.2.1' -or $changed -notmatch 'EARBUDS_MAC=aa:BB:cc:DD:ee:FF') { throw 'Unrelated data changed' }
if ((Update-EnvText $changed $values) -cne $changed) { throw 'Not idempotent' }
if ((Read-EnvText $changed).MAIX_IP -ne '192.0.2.9') { throw 'Address was not updated' }
try { Read-EnvText "MAIX_IP=x`nMAIX_IP=y"; throw 'Duplicate accepted' }
catch { if ($_.Exception.Message -notlike '*Duplicate configuration key*') { throw } }
''')

    def test_ipv4_and_subnets_reject_invalid_addresses(self):
        self.run_ps(r'''
foreach ($bad in @('127.0.0.1','169.254.1.1','224.1.1.1','0.0.0.0','999.1.2.3','::1','192.168.1')) {
    if (Test-IPv4 $bad) { throw "Accepted $bad" }
}
if (-not (Test-IPv4 '10.131.167.1')) { throw 'Valid IP rejected' }
if (-not (Test-SameSubnet '10.131.167.100' '10.131.167.1' 24)) { throw 'Subnet mismatch' }
if (Test-SameSubnet '10.131.167.100' '10.131.168.1' 24) { throw 'Wrong subnet accepted' }
''')

    def test_filters_virtual_and_usb_from_wifi(self):
        self.run_ps(r'''
& $module {
    function Get-NetAdapter {
        foreach ($entry in @(@('Wi-Fi','802.11 adapter','Native 802.11',1,$true),
                @('Ethernet 2','UsbNcm Host Device','Unspecified',2,$true),
                @('VPN','Virtual Wi-Fi','Native 802.11',3,$false),
                @('Ethernet','Realtek PCIe','802.3',4,$true))) {
            [pscustomobject]@{ Name=$entry[0]; InterfaceDescription=$entry[1]; PhysicalMediaType=$entry[2];
                ifIndex=$entry[3]; HardwareInterface=$entry[4]; Status='Up' }
        }
    }
    function Get-NetIPAddress {
        foreach ($index in 1..4) { [pscustomobject]@{ InterfaceIndex=$index; IPAddress="192.0.$index.2";
            PrefixLength=24; AddressState='Preferred'; SkipAsSource=$false } }
    }
    $result = @(Get-DeploymentInterfaces)
    if ($result.Count -ne 2 -or $result[0].Kind -ne 'Wifi' -or $result[1].Kind -ne 'Usb') { throw 'Adapter filtering failed' }
}
''')

    def test_usb_peers_are_bounded_to_detected_subnet(self):
        self.run_ps(r'''
& $module {
    function Get-NetNeighbor { [pscustomobject]@{IPAddress='10.9.8.3';State='Stale'} }
    function Get-NetRoute { [pscustomobject]@{NextHop='0.0.0.0'} }
    $peers = @(Get-UsbPeers ([pscustomobject]@{Index=7;Address='10.9.8.2';PrefixLength=29}) '192.168.1.1')
    if ($peers.Count -ne 5 -or '10.9.8.3' -notin $peers -or '10.9.8.7' -in $peers -or '10.9.8.2' -in $peers -or '192.168.1.1' -in $peers) { throw 'Invalid USB candidate list' }
}
''')

    def test_wifi_selection_uses_actual_windows_route(self):
        self.run_ps(r'''
& $module {
    function Find-NetRoute { [pscustomobject]@{InterfaceIndex=18;IPAddress='10.4.2.9'}; [pscustomobject]@{InterfaceIndex=18;NextHop='0.0.0.0'} }
    $interfaces = @([pscustomobject]@{Kind='Wifi';Index=18;Address='10.4.2.9';PrefixLength=16},
        [pscustomobject]@{Kind='Wifi';Index=19;Address='10.4.2.10';PrefixLength=16})
    if ((Select-LaptopWifi $interfaces '10.4.3.2' 0).Index -ne 18) { throw 'Wrong selected interface' }
    try { Select-LaptopWifi $interfaces '10.4.3.2' 19; throw 'Wrong route accepted' }
    catch { if ($_.Exception.Message -notlike '*Cannot select*') { throw } }
}
''')

    def test_process_handles_stdin_quoting_exit_and_timeout(self):
        self.run_ps(r'''
$shell = Join-Path $PSHOME 'powershell.exe'
$result = Invoke-NetworkProcess $shell @('-NoProfile','-NonInteractive','-Command','[Console]::Write([Console]::In.ReadToEnd())') -InputText 'a "quoted" value'
if ($result -cne 'a "quoted" value') { throw 'Stdin damaged' }
$result = Invoke-NetworkProcess $shell @('-NoProfile','-NonInteractive','-Command','[Console]::Write("a b")')
if ($result -cne 'a b') { throw 'Arguments damaged' }
foreach ($streamOutput in @($false, $true)) {
    try { Invoke-NetworkProcess $shell @('-NoProfile','-Command','exit 7') -StreamOutput:$streamOutput; throw 'Exit ignored' }
    catch { if ($_.Exception.Message -notlike '*failed (7)*') { throw } }
    try { Invoke-NetworkProcess $shell @('-NoProfile','-Command','Start-Sleep 30') -TimeoutSeconds 1 -StreamOutput:$streamOutput; throw 'Timeout ignored' }
    catch { if ($_.Exception.Message -notlike '*timed out*') { throw } }
}
''')

    def test_process_streams_stdout_and_stderr_before_child_finishes(self):
        self.run_ps(r'''
$marker = Join-Path ([IO.Path]::GetTempPath()) ([guid]::NewGuid().ToString('N'))
$sawLiveOutput = $false
$sawDiagnostic = $false
$command = "[Console]::WriteLine('READY'); Start-Sleep -Seconds 2; [IO.File]::WriteAllText(`$env:STREAM_TEST_MARKER,'done'); [Console]::Error.WriteLine('DIAGNOSTIC')"
try {
    Invoke-NetworkProcess (Join-Path $PSHOME 'powershell.exe') @('-NoProfile','-NonInteractive','-Command',$command) -StreamOutput -Environment @{STREAM_TEST_MARKER=$marker} 6>&1 |
        ForEach-Object {
            if ($_ -is [Management.Automation.InformationRecord]) {
                if ($_.ToString() -eq 'READY') {
                    if (Test-Path -LiteralPath $marker) { throw 'Output was buffered until the child finished' }
                    $sawLiveOutput = $true
                }
                if ($_.ToString() -eq 'DIAGNOSTIC') { $sawDiagnostic = $true }
            }
        }
    if (-not $sawLiveOutput -or -not $sawDiagnostic) { throw 'Missing streamed stdout/stderr' }
} finally { if (Test-Path -LiteralPath $marker) { Remove-Item -LiteralPath $marker } }
''')

    def deployment_fixture(self, root):
        (root / 'scripts').mkdir()
        for name in ('deploy.ps1', 'NetworkDeployment.psm1'):
            shutil.copy2(ROOT / 'scripts' / name, root / 'scripts' / name)
        # Only the isolated script copy bypasses elevation; external operations are mocked.
        deploy = root / 'scripts/deploy.ps1'
        deploy.write_text(deploy.read_text().replace('#Requires -RunAsAdministrator\n', ''))
        for folder in ('maix', 'pc', 'frontend/src', 'frontend/scripts', '.runtime'):
            (root / folder).mkdir(parents=True, exist_ok=True)
        (root / '.runtime/deploy-credential.xml').write_text('stale credentials must not override root defaults')
        for name in ('Dockerfile', 'compose.yaml', 'app.py', 'mediamtx.yml'):
            (root / name).write_text('# fixture')
        (root / 'pc/talkback_protocol.py').write_text('# fixture protocol\n')
        (root / '.env.example').write_text('MAIX_IP=192.0.2.8\nRTSP_TRANSPORT=tcp\nSTREAM_MODE=video\n')
        (root / '.env').write_text('MAIX_IP=192.0.2.8\nMAIX_USB_IP=10.9.8.1\nOTHER=preserved\n')
        with (root / 'scripts/NetworkDeployment.psm1').open('a') as module:
            module.write(r'''
function Install-MaixCamera {
    param($MaixHost,$PcIp,$HeadsetMac,$WifiSsid,$AudioProfile,[switch]$Reboot,$DeploymentId)
    if ($WifiSsid -cne 'Test WiFi') { throw 'Required SSID not forwarded to camera installer' }
    Add-Content '.runtime/actions' 'CAMERA_DEPLOY'
}
function Install-PcRuntime {
    param([switch]$Build,[switch]$Recreate,[switch]$NoCache)
    if ($Build) {
        Add-Content '.runtime/actions' 'PC_DEPLOY'
        if ($env:NETWORK_TEST_CASE -in @('pc-failed','legacy-failed','legacy-missing-failed','legacy-malformed-failed','legacy-mismatched-failed')) { throw 'Simulated Docker build failure' }
    }
}
function Stop-PcRuntime {
    param([switch]$CheckOnly)
    if ($env:NETWORK_TEST_CASE -eq 'recording') { throw 'Stop the recording first' }
    if (-not $CheckOnly) {
        Add-Content '.runtime/actions' 'PC_STOP'
        Set-Content '.runtime/return-recovered' 'yes'
    }
}
function Set-HeadsetFirewallRule {
    param($CameraIP)
    if ($CameraIP -ne '192.0.2.1') { throw 'Wrong discovered firewall IP' }
    Add-Content '.runtime/actions' 'FIREWALL_ALLOW'
}
function Invoke-MaintenanceDocker {
    param([string[]]$Arguments)
    $call = $Arguments -join ' '
    $marker = Join-Path (Get-Location) 'recordings/.maintenance.json'
    if ($call -eq 'ps --quiet') { Add-Content '.runtime/actions' 'ALL_STOP'; return 'fixture-container' }
    if ($call -like '*ps --all --quiet server*') { return 'fixture-container' }
    if ($call -like '*inspect --format*') { return 'running' }
    if ($call -like '*exec -T server python*') {
        if ($env:NETWORK_TEST_CASE -eq 'recording') { return '{"recording":true}' }
        if ($call -like '*/api/maintenance/begin*') {
            if ($call -notmatch "owner='([a-f0-9]{32})'") { throw 'Missing owner' }
            [void](New-Item -ItemType Directory -Path (Split-Path $marker) -Force)
            [IO.File]::WriteAllText($marker, (@{owner=$Matches[1]} | ConvertTo-Json))
        }
        if ($call -like '*/api/maintenance/end*') {
            if ($env:NETWORK_TEST_CASE -eq 'release-failed') { throw 'Simulated maintenance release failure' }
            Remove-Item -LiteralPath $marker
        }
        $maintenance = if (Test-Path -LiteralPath $marker) { Get-Content -LiteralPath $marker -Raw | ConvertFrom-Json } else { $null }
        return (@{recording=$false;finalizing=$false;maintenance=$maintenance} | ConvertTo-Json -Compress)
    }
    return ''
}
function Get-DeploymentInterfaces {
    [pscustomobject]@{Kind='Wifi';Index=18;Address='192.0.2.2';PrefixLength=24;Name='Wi-Fi'}
    [pscustomobject]@{Kind='Usb';Index=17;Address='10.9.8.2';PrefixLength=24;Name='USB'}
}
function Get-UsbPeers { return '10.9.8.1' }
function Find-OpenSshPeers { return '10.9.8.1' }
function Select-LaptopWifi { return [pscustomobject]@{Address='192.0.2.2';Index=18} }
function Get-LaptopWifiSsid {
    if ($env:NETWORK_TEST_CASE -eq 'wrong-host-ssid') { return 'Other WiFi' }
    return 'Test WiFi'
}
function Set-MaixWifi {
    param($Context,$HostAddress,$WifiSsid,$WifiPassword,$WifiMac)
    if ($HostAddress -ne '10.9.8.1' -or $WifiSsid -cne 'Test WiFi' -or
        $WifiMac -ne 'ab:cd:ef:01:23:45' -or -not $WifiPassword) { throw 'Wrong Wi-Fi setup arguments' }
    Set-Content '.runtime/wifi-joined' 'yes'
    Add-Content '.runtime/actions' 'WIFI_SWITCH'
    return [pscustomobject]@{ssid=$WifiSsid;mac=$WifiMac;ip='192.0.2.1'}
}
function Invoke-MaixSsh {
    param($Context,$Address,$Command,$TimeoutSeconds)
    if ($env:NETWORK_TEST_CASE -eq 'ssh-failed') { throw 'Permission denied (publickey,password)' }
    if ($Command -like '*glob, json, pathlib*') {
        $ssid = if ($env:NETWORK_TEST_CASE -eq 'wrong-camera-ssid' -and -not (Test-Path '.runtime/wifi-joined')) { 'Other WiFi' } else { 'Test WiFi' }
        return ('{"model":"MaixCAM","wifi":[{"ip":"192.0.2.1","mac":"ab:cd:ef:01:23:45","state":"COMPLETED","ssid":"' + $ssid + '"}],"settings":{"PC_IP":"192.0.2.2","HEADSET_MAC":"aA:bB:cC:dD:eE:fF","AUDIO_PROFILE":"sco"}}')
    }
    if ($Command -like '*hashlib,json,pathlib,re*') {
        if ($env:NETWORK_TEST_CASE -like 'legacy-*') {
            $sha = [Security.Cryptography.SHA256]::Create()
            try { $digest = [BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes(('00' * 16)))).Replace('-', '').ToLowerInvariant() }
            finally { $sha.Dispose() }
            return (@{legacy=$true;digest=$digest} | ConvertTo-Json)
        }
        return '{"legacy":false,"digest":null}'
    }
    if ($Command -like '*talkback_protocol.PROTOCOL_VERSION*') { return 'TB3' }
    if ($Command -like '*hashlib.sha256(pathlib*') {
        $text = [IO.File]::ReadAllText((Join-Path (Get-Location) 'pc/talkback_protocol.py')).Replace("`r`n", "`n")
        $sha = [Security.Cryptography.SHA256]::Create()
        try { return [BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($text))).Replace('-', '') }
        finally { $sha.Dispose() }
    }
    if ($Command -like '*p.unlink*') {
        Add-Content '.runtime/actions' 'CAMERA_TOKEN_CLEANUP'
        if ($env:NETWORK_TEST_CASE -eq 'cleanup-failed') { throw 'Permission denied' }
    }
    if ($Command -like '*backup=__*' -or $Command -like '*backup=/root*') { Add-Content '.runtime/actions' 'CAMERA_ROLLBACK' }
    return ''
}
function Invoke-NetworkProcess {
    param($FilePath,$Arguments,$TimeoutSeconds,$InputText,$Environment,[switch]$StreamOutput)
    $call = $Arguments -join ' '
    if ($FilePath -ne 'docker.exe') { return '' }
    if ($call -like '*--force-recreate*--no-deps*server*') {
        Add-Content '.runtime/actions' 'UDP_RECREATE'
    }
    if ($call -like '*ffmpeg*headsetmic*' -and $env:NETWORK_TEST_CASE -eq 'headset-once' -and -not (Test-Path '.runtime/headset-retried')) { Set-Content '.runtime/headset-retried' 'yes'; throw 'Server returned 404 Not Found' }
    if ($Arguments[0] -eq 'info') { return 'linux' }
    if ($Arguments[0] -eq 'cp' -and $env:NETWORK_TEST_CASE -eq 'legacy-retained') {
        if (Test-Path -LiteralPath $Arguments[2] -PathType Container) {
            [IO.File]::WriteAllText((Join-Path $Arguments[2] 'preserved.mp4'), 'old-recording-fixture')
        } else { [IO.File]::WriteAllText($Arguments[2], ('00' * 16)) }
        return ''
    }
    if ($call -like '*config --format json*') { return '{"services":{"server":{"command":["python","--maix-ip","192.0.2.1"],"environment":{"MAIX_USB_IP":"10.9.8.1"}}}}' }
    if ($call -like '*ps *') { return 'fixture-container' }
    if ($Arguments[0] -eq 'inspect') {
        $mounts = @()
        $isPrevious = -not (Test-Path '.runtime/actions') -or -not ((Get-Content '.runtime/actions') -contains 'PC_DEPLOY')
        if ($isPrevious -and $env:NETWORK_TEST_CASE -like 'legacy-*') {
            $tokenSource = if ($env:NETWORK_TEST_CASE -eq 'legacy-retained') { '.removed-token' } else { '.talkback_token' }
            $mounts = @(@{Type='bind';Source=(Join-Path (Get-Location) $tokenSource);Destination='/app/.talkback_token';RW=$false})
            if ($env:NETWORK_TEST_CASE -eq 'legacy-retained') {
                $mounts += @{Type='bind';Source=(Join-Path (Get-Location) '.removed-recordings');Destination='/app/recordings';RW=$true}
            }
        }
        return (ConvertTo-Json -Depth 12 -InputObject @(@{Id='fixture-container';Image='old-image-id';State=@{Running=$true;Health=@{Status='healthy'}};
            Config=@{Cmd=@('python','--maix-ip','192.0.2.1');Env=@('ORIGINAL=kept');Entrypoint=$null;WorkingDir='/app';User='';Healthcheck=$null};
            Mounts=@($mounts);HostConfig=@{PortBindings=@{'8000/tcp'=@(@{HostIp='127.0.0.1';HostPort='8000'})};RestartPolicy=@{Name='unless-stopped'};LogConfig=@{Type='json-file';Config=@{'max-size'='10m'}};Init=$true}}))
    }
    if ($call -like '*rollback.compose.json*') {
        if ($call -notlike '* create --no-build server') { throw 'Rollback must restore the previous image stopped' }
        Add-Content '.runtime/actions' 'PC_ROLLBACK'
        if ($call -like '*compose.yaml*') { throw 'Rollback used new configuration' }
    }
    return ''
}
function Test-HostUdpListeners {
    param($Ports)
    if ($env:NETWORK_TEST_CASE -eq 'udp-missing') { return $false }
    if ($env:NETWORK_TEST_CASE -eq 'udp-recovered') {
        if (Test-Path '.runtime/actions') {
            if ((Get-Content '.runtime/actions') -contains 'UDP_RECREATE') { return $true }
        }
        return $false
    }
    return $true
}
Export-ModuleMember -Function *
''')
        (root / 'run.ps1').write_text(r'''
$ErrorActionPreference='Stop'
function docker.exe {}
function Get-NetTCPConnection { return }
function Invoke-RestMethod {
    param($Uri,$TimeoutSec)
    if ($Uri -like '*diagnostics') { return [pscustomobject]@{media_ip='192.0.2.1';wifi=@{reachable=$true}} }
    if ($Uri -like '*/api/bluetooth/status') { return [pscustomobject]@{selected='aA:bB:cC:dD:eE:fF';connected=$true;error=$null} }
    if ($Uri -like '*:8765/bluetooth/status') {
        $protocol = if ($env:NETWORK_TEST_CASE -eq 'mixed-camera') { 'TB2' } else { 'TB3' }
        return [pscustomobject]@{talkback_protocol=$protocol}
    }
    $protocol = if ($env:NETWORK_TEST_CASE -eq 'mixed-pc') { 'TB2' } else { 'TB3' }
    return [pscustomobject]@{available=$true;error=$null;protocol=$protocol}
}
& (Join-Path $PSScriptRoot 'scripts/deploy.ps1') @args
exit $LASTEXITCODE
''')

    def run_deployment(self, root, case='ready', arguments=()):
        return subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-File', str(root / 'run.ps1'), '-WifiSsid', 'Test WiFi', '-HeadsetMac', 'aA:bB:cC:dD:eE:fF', *arguments],
                              env={**os.environ, 'NETWORK_TEST_CASE': case}, capture_output=True, text=True, timeout=30)

    def test_dry_run_discovers_without_mutating_configuration_or_services(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.deployment_fixture(root)
            original = (root / '.env').read_bytes()
            result = self.run_deployment(root, arguments=('-DryRun',))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual((root / '.env').read_bytes(), original)
            self.assertFalse((root / '.runtime/actions').exists())
            self.assertFalse((root / '.runtime/deploy-state.json').exists())
            self.assertNotIn('SUCCESS', result.stdout)
            self.assertFalse((root / '.talkback_token').exists())
            self.assertFalse((root / '.runtime/mutation.lock').exists())
            self.assertFalse((root / 'recordings/.maintenance.json').exists())

    def test_release_failure_keeps_marker_and_does_not_claim_success(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.deployment_fixture(root)
            result = self.run_deployment(root, 'release-failed')
            self.assertEqual(result.returncode, 6, result.stdout + result.stderr)
            self.assertTrue((root / 'recordings/.maintenance.json').exists())
            self.assertIn('Maintenance release failed', result.stdout)
            self.assertNotIn('Deployment completed successfully', result.stdout)

    def test_every_run_reinstalls_both_devices_without_backups(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.deployment_fixture(root)
            for arguments in ((), (), ('-Force',)):
                result = self.run_deployment(root, arguments=arguments)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                if not arguments and (root / '.runtime/actions').read_text().count('PC_DEPLOY') == 1:
                    self.assertIn('EARBUDS_MAC=aA:bB:cC:dD:eE:fF', (root / '.env').read_text())
            self.assertEqual((root / '.runtime/actions').read_text().count('PC_DEPLOY'), 3)
            self.assertEqual((root / '.runtime/actions').read_text().count('CAMERA_DEPLOY'), 3)
            self.assertEqual((root / '.runtime/actions').read_text().count('FIREWALL_ALLOW'), 3)

    def test_ssh_failure_does_not_change_configuration(self):
        for case, code in (('ssh-failed', 3),):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.deployment_fixture(root)
                original = (root / '.env').read_bytes()
                result = self.run_deployment(root, case)
                self.assertEqual(result.returncode, code, result.stdout + result.stderr)
                self.assertEqual((root / '.env').read_bytes(), original)
                self.assertFalse((root / '.runtime/actions').exists())

    def test_failed_build_keeps_new_config_and_rerun_needs_no_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.deployment_fixture(root)
            result = self.run_deployment(root, 'pc-failed')
            self.assertEqual(result.returncode, 4, result.stdout + result.stderr)
            self.assertNotIn('OTHER=preserved', (root / '.env').read_text())
            self.assertFalse((root / '.runtime/deploy-backups').exists())
            self.assertTrue((root / 'recordings/.maintenance.json').exists())
            self.assertNotIn('ROLLBACK', (root / '.runtime/actions').read_text())
            result = self.run_deployment(root)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertFalse((root / 'recordings/.maintenance.json').exists())

    def test_missing_headset_return_uses_one_scoped_stop_start(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.deployment_fixture(root)
            result = self.run_deployment(root, 'headset-once')
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('refresh Docker UDP forwarding', result.stdout)
            self.assertEqual((root / '.runtime/actions').read_text().count('PC_STOP'), 1)

    def test_fresh_checkout_ignores_old_config_and_camera_installation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.deployment_fixture(root)
            (root / '.env').unlink()
            module = root / 'scripts/NetworkDeployment.psm1'
            module.write_text(module.read_text().replace('"settings":{"PC_IP":"192.0.2.2","HEADSET_MAC":"aA:bB:cC:dD:eE:fF","AUDIO_PROFILE":"sco"}', '"settings":{}'))
            result = self.run_deployment(root)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('EARBUDS_MAC=aA:bB:cC:dD:eE:fF', (root / '.env').read_text())
            actions = (root / '.runtime/actions').read_text()
            self.assertLess(actions.index('ALL_STOP'), actions.index('CAMERA_DEPLOY'))
            self.assertLess(actions.index('CAMERA_DEPLOY'), actions.index('PC_DEPLOY'))

    def test_mixed_versions_fail_without_rollback_or_success(self):
        for case in ('mixed-camera', 'mixed-pc'):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.deployment_fixture(root)
                result = self.run_deployment(root, case)
                self.assertEqual(result.returncode, 5, result.stdout + result.stderr)
                self.assertNotIn('ROLLBACK', (root / '.runtime/actions').read_text())
                self.assertNotIn('SUCCESS', result.stdout)

    def test_cleanup_follows_verification_and_cannot_fail_startup(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.deployment_fixture(root)
            (root / '.talkback_token').write_text('ignored')
            result = self.run_deployment(root, 'cleanup-failed')
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('cleanup failed', result.stdout)
            self.assertIn('SUCCESS', result.stdout)
            actions = (root / '.runtime/actions').read_text()
            self.assertLess(actions.index('ALL_STOP'), actions.index('CAMERA_DEPLOY'))
            self.assertLess(actions.index('PC_DEPLOY'), actions.index('CAMERA_TOKEN_CLEANUP'))
            self.assertTrue((root / '.talkback_token').exists())


    def test_host_udp_listener_detection(self):
        self.run_ps(r'''
& $module {
    function Get-NetUDPEndpoint {
        param($LocalPort)
        if ($LocalPort -eq 8004) { return [pscustomobject]@{LocalPort=8004} }
        return
    }
    if (-not (Test-HostUdpListeners -Ports @(8004))) { throw 'Expected 8004 to be detected' }
    if (Test-HostUdpListeners -Ports @(8004, 8005)) { throw 'Expected missing 8005 to fail' }
}
''')

    def test_missing_host_udp_listener_triggers_recreate_and_recovers(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.deployment_fixture(root)
            result = self.run_deployment(root, 'udp-recovered')
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('host UDP listeners verified', result.stdout)
            actions = (root / '.runtime/actions').read_text()
            self.assertIn('UDP_RECREATE', actions)

    def test_missing_host_udp_listener_fails_when_unrecovered(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.deployment_fixture(root)
            result = self.run_deployment(root, 'udp-missing')
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('UDP listener 8004/8005 remains missing', result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
