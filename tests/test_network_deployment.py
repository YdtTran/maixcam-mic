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
try { Invoke-NetworkProcess $shell @('-NoProfile','-Command','exit 7'); throw 'Exit ignored' }
catch { if ($_.Exception.Message -notlike '*failed (7)*') { throw } }
try { Invoke-NetworkProcess $shell @('-NoProfile','-Command','Start-Sleep 30') -TimeoutSeconds 1; throw 'Timeout ignored' }
catch { if ($_.Exception.Message -notlike '*timed out*') { throw } }
''')

    def deployment_fixture(self, root):
        (root / 'scripts').mkdir()
        for name in ('deploy.ps1', 'NetworkDeployment.psm1'):
            shutil.copy2(ROOT / 'scripts' / name, root / 'scripts' / name)
        for folder in ('maix', 'pc', 'frontend/src', 'frontend/scripts', '.runtime'):
            (root / folder).mkdir(parents=True, exist_ok=True)
        for name in ('Dockerfile', 'compose.yaml', 'app.py', 'mediamtx.yml', 'deploy_pc.ps1', 'stop_docker_pc.ps1'):
            (root / name).write_text('# fixture')
        (root / 'deploy_maix.ps1').write_text(r'''
param($MaixHost,$PcIp,$HeadsetMac,$AudioProfile,[switch]$Reboot,$DeploymentId)
Add-Content -LiteralPath (Join-Path $PSScriptRoot '.runtime/actions') 'CAMERA_DEPLOY'
''')
        (root / '.env').write_text('MAIX_IP=192.0.2.8\nMAIX_USB_IP=10.9.8.1\nOTHER=preserved\n')
        (root / '.talkback_token').write_text('00' * 16)
        with (root / 'scripts/NetworkDeployment.psm1').open('a') as module:
            module.write(r'''
function Get-DeploymentInterfaces {
    [pscustomobject]@{Kind='Wifi';Index=18;Address='192.0.2.2';PrefixLength=24;Name='Wi-Fi'}
    [pscustomobject]@{Kind='Usb';Index=17;Address='10.9.8.2';PrefixLength=24;Name='USB'}
}
function Get-UsbPeers { return '10.9.8.1' }
function Find-OpenSshPeers { return '10.9.8.1' }
function Select-LaptopWifi { return [pscustomobject]@{Address='192.0.2.2';Index=18} }
function Invoke-MaixSsh {
    param($Context,$Address,$Command,$TimeoutSeconds)
    if ($env:NETWORK_TEST_CASE -eq 'ssh-failed') { throw 'Permission denied (publickey,password)' }
    if ($Command -like '*import glob*') {
        return '{"model":"MaixCAM","wifi":[{"ip":"192.0.2.1","mac":"ab:cd:ef:01:23:45"}],"settings":{"PC_IP":"192.0.2.2","HEADSET_MAC":"aA:bB:cC:dD:eE:fF","AUDIO_PROFILE":"sco"}}'
    }
    if ($Command -like '*backup=/root*') { Add-Content '.runtime/actions' 'CAMERA_ROLLBACK' }
    return ''
}
function Invoke-NetworkProcess {
    param($FilePath,$Arguments,$TimeoutSeconds,$InputText,$Environment)
    $call = $Arguments -join ' '
    if ($call -like '*stop_docker_pc.ps1*' -and $env:NETWORK_TEST_CASE -eq 'recording') { throw 'Stop the recording first' }
    if ($call -like '*stop_docker_pc.ps1*' -and $call -notlike '*-CheckOnly*') {
        Add-Content '.runtime/actions' 'PC_RETURN_RECOVERY'
        Set-Content '.runtime/return-recovered' 'yes'
    }
    if ($call -like '*deploy_pc.ps1*' -and $call -like '*-Build*') {
        Add-Content '.runtime/actions' 'PC_DEPLOY'
        if ($env:NETWORK_TEST_CASE -eq 'pc-failed') { throw 'Simulated Docker build failure' }
    }
    if ($FilePath -ne 'docker.exe') { return '' }
    if ($call -like '*ffmpeg*headsetmic*' -and $env:NETWORK_TEST_CASE -eq 'headset-once' -and -not (Test-Path '.runtime/return-recovered')) { throw 'Server returned 404 Not Found' }
    if ($Arguments[0] -eq 'info') { return 'linux' }
    if ($call -like '*config --format json*') { return '{"services":{"server":{"command":["python","--maix-ip","192.0.2.1"],"environment":{"MAIX_USB_IP":"10.9.8.1"}}}}' }
    if ($call -like '*ps *') { return 'fixture-container' }
    if ($Arguments[0] -eq 'inspect') {
        if ($call -like '*State.Running*') { return 'true' }
        if ($call -like '*Image*') { return 'old-image-id' }
        return '[{"State":{"Health":{"Status":"healthy"}},"Config":{"Cmd":["192.0.2.1"]}}]'
    }
    if ($call -like '*rollback.compose.yaml*') { Add-Content '.runtime/actions' 'PC_ROLLBACK' }
    return ''
}
Export-ModuleMember -Function *
''')
        (root / 'run.ps1').write_text(r'''
$ErrorActionPreference='Stop'
function docker.exe {}
function Invoke-RestMethod {
    param($Uri,$TimeoutSec)
    if ($Uri -like '*diagnostics') { return [pscustomobject]@{media_ip='192.0.2.1';wifi=@{reachable=$true}} }
    return [pscustomobject]@{available=$true;error=$null}
}
& (Join-Path $PSScriptRoot 'scripts/deploy.ps1') @args
exit $LASTEXITCODE
''')

    def run_deployment(self, root, case='ready', arguments=()):
        return subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-File', str(root / 'run.ps1'), *arguments],
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

    def test_deployment_is_idempotent_and_force_redeploys(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.deployment_fixture(root)
            for arguments in ((), (), ('-Force',)):
                result = self.run_deployment(root, arguments=arguments)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                if not arguments and (root / '.runtime/actions').read_text().count('PC_DEPLOY') == 1:
                    self.assertIn('EARBUDS_MAC=aA:bB:cC:dD:eE:fF', (root / '.env').read_text())
            self.assertEqual((root / '.runtime/actions').read_text().count('PC_DEPLOY'), 2)
            self.assertEqual((root / '.runtime/actions').read_text().count('CAMERA_DEPLOY'), 2)

    def test_ssh_and_recording_failures_do_not_change_configuration(self):
        for case, code in (('ssh-failed', 3), ('recording', 3)):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.deployment_fixture(root)
                original = (root / '.env').read_bytes()
                result = self.run_deployment(root, case)
                self.assertEqual(result.returncode, code, result.stdout + result.stderr)
                self.assertEqual((root / '.env').read_bytes(), original)
                self.assertFalse((root / '.runtime/actions').exists())

    def test_failed_pc_deployment_restores_config_camera_and_previous_image(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.deployment_fixture(root)
            original = (root / '.env').read_bytes()
            result = self.run_deployment(root, 'pc-failed')
            self.assertEqual(result.returncode, 4, result.stdout + result.stderr)
            self.assertEqual((root / '.env').read_bytes(), original)
            actions = (root / '.runtime/actions').read_text()
            self.assertIn('CAMERA_ROLLBACK', actions)
            self.assertIn('PC_ROLLBACK', actions)
            self.assertNotIn('SUCCESS', result.stdout)

    def test_missing_headset_return_uses_one_scoped_stop_start(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.deployment_fixture(root)
            result = self.run_deployment(root, 'headset-once')
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('refresh Docker UDP forwarding', result.stdout)
            self.assertEqual((root / '.runtime/actions').read_text().count('PC_RETURN_RECOVERY'), 1)


if __name__ == '__main__':
    unittest.main()
