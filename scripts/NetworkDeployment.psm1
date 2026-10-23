Set-StrictMode -Version Latest

function Invoke-MaintenanceDocker {
    param([string[]]$Arguments)
    $output = & docker @Arguments
    if ($LASTEXITCODE -ne 0) { throw 'Cannot verify operator maintenance; inspect Docker logs before mutation.' }
    return $output
}

function Get-MaintenanceOperator {
    param([string]$ProjectRoot)
    if ($env:OS -eq 'Windows_NT') {
        foreach ($listener in @(Get-NetTCPConnection -LocalPort 8000,8554,8889 -State Listen -ErrorAction SilentlyContinue)) {
            $process = Get-CimInstance Win32_Process -Filter "ProcessId = $($listener.OwningProcess)"
            if ($process.Name -in @('python.exe', 'pythonw.exe', 'mediamtx.exe')) {
                throw 'Stop the native project service before Docker maintenance.'
            }
        }
    }
    $compose = Join-Path $ProjectRoot 'compose.yaml'
    $ids = @(Invoke-MaintenanceDocker @('compose', '-f', $compose, 'ps', '--all', '--quiet', 'server'))
    foreach ($id in $ids) {
        if (-not $id) { continue }
        $state = Invoke-MaintenanceDocker @('inspect', '--format', '{{.State.Status}}', $id)
        if ($state -eq 'running') { return 'running' }
        if ($state -notin @('exited', 'created')) { throw "Operator is $state; cannot verify idle state." }
    }
    return 'stopped'
}

function Invoke-MaintenanceApi {
    param([string]$ProjectRoot, [string]$Action = 'status', [string]$Owner)
    $code = "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/api/recordings/status', timeout=3).read().decode())"
    if ($Action -ne 'status') {
        if ($Owner -cnotmatch '^[a-f0-9]{32}$' -or $Action -notin @('begin', 'end')) { throw 'Invalid maintenance request.' }
        $code = "import json,urllib.request; print(urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8000/api/maintenance/$Action', data=json.dumps(dict(owner='$Owner')).encode(), headers={'Content-Type':'application/json'}), timeout=3).read().decode())"
    }
    $result = Invoke-MaintenanceDocker @('compose', '-f', (Join-Path $ProjectRoot 'compose.yaml'), 'exec', '-T', 'server', 'python', '-c', $code)
    $status = $result | ConvertFrom-Json
    if ($null -eq $status -or $status.PSObject.Properties.Name -notcontains 'recording' -or $status.recording -isnot [bool]) {
        throw 'Invalid recording status; refusing maintenance.'
    }
    if ($status.recording -or ($status.PSObject.Properties.Name -contains 'finalizing' -and $status.finalizing)) {
        throw 'Stop recording and wait for finalization before maintenance.'
    }
    return $status
}

function Enter-ProjectMaintenance {
    param([string]$ProjectRoot, [switch]$StopOnly, [string]$RecoverOwner, [switch]$Fresh)
    $ProjectRoot = [IO.Path]::GetFullPath($ProjectRoot)
    $directory = Join-Path $ProjectRoot '.runtime'
    $lockPath = Join-Path $directory 'mutation.lock'
    $marker = Join-Path $ProjectRoot 'recordings/.maintenance.json'
    $inherited = $env:WORKERCAM_MAINTENANCE_OWNER
    if ($inherited -and -not $RecoverOwner) {
        # A child may reuse ownership only while the outer process holds its file handle.
        if (-not (Test-Path -LiteralPath $lockPath)) { throw 'Inherited maintenance has no host lock.' }
        $reader = [IO.File]::Open($lockPath, 'Open', 'Read', 'ReadWrite')
        try { $text = New-Object IO.StreamReader($reader); $heldOwner = $text.ReadToEnd() }
        finally { $reader.Dispose() }
        if ($heldOwner -cne $inherited) { throw 'Inherited maintenance owner mismatch.' }
        $probe = $null
        try { $probe = [IO.File]::Open($lockPath, 'Open', 'ReadWrite', 'Read') } catch [IO.IOException] { }
        if ($probe) { $probe.Dispose(); throw 'Inherited maintenance host lock is no longer held.' }
        $saved = Get-Content -LiteralPath $marker -Raw | ConvertFrom-Json
        if ($saved.owner -cne $inherited) { throw 'Inherited maintenance marker mismatch.' }
        return @{ Outer = $false; Owner = $inherited }
    }
    [void](New-Item -ItemType Directory -Path $directory -Force)
    try { $handle = [IO.File]::Open($lockPath, 'OpenOrCreate', 'ReadWrite', 'Read') }
    catch [IO.IOException] { throw 'Another project maintenance operation is running.' }
    $owner = if ($RecoverOwner) { $RecoverOwner } else { [guid]::NewGuid().ToString('N') }
    $context = @{ Outer = $true; Owner = $owner; Handle = $handle; Root = $ProjectRoot; PreviousOwner = $inherited }
    try {
        if ($owner -cnotmatch '^[a-f0-9]{32}$') { throw 'Invalid recovery owner.' }
        $handle.SetLength(0)
        $bytes = [Text.Encoding]::UTF8.GetBytes($owner)
        $handle.Write($bytes, 0, $bytes.Length); $handle.Flush()
        if ($Fresh) {
            Write-Host 'Hard-fresh reinstall: stopping ALL running Docker containers...'
            $containers = @(Invoke-MaintenanceDocker @('ps', '--quiet'))
            if ($containers.Count) { Invoke-MaintenanceDocker (@('stop', '--time', '15') + $containers) | Out-Null }
            Invoke-MaintenanceDocker @('compose', '--env-file', (Join-Path $ProjectRoot '.env.example'), '-f', (Join-Path $ProjectRoot 'compose.yaml'), 'down', '--remove-orphans') | Out-Null
            foreach ($path in @($marker, (Join-Path $ProjectRoot 'recordings/.camera-view.json'))) {
                if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Force }
            }
        }
        if (Test-Path -LiteralPath $marker) {
            $saved = Get-Content -LiteralPath $marker -Raw | ConvertFrom-Json
            if (-not $RecoverOwner -or $saved.owner -cne $owner) {
                throw "Maintenance marker retained. Inspect the failure and rerun scripts/deploy.ps1 for a complete fresh reinstall."
            }
        } elseif ($RecoverOwner) { throw 'No maintenance marker to recover.' }
        $state = if ($Fresh) { 'stopped' } else { Get-MaintenanceOperator $ProjectRoot }
        $legacy = $false
        if ($state -eq 'running') {
            $status = Invoke-MaintenanceApi $ProjectRoot
            $legacy = $status.PSObject.Properties.Name -notcontains 'maintenance'
            if (-not $legacy) {
                $status = Invoke-MaintenanceApi $ProjectRoot 'begin' $owner
                if ($status.maintenance.owner -cne $owner) { throw 'Operator did not acquire maintenance.' }
                if (-not (Test-Path -LiteralPath $marker)) { throw 'Operator recordings mount is not this checkout; maintenance retained in the operator. Refusing local mutation.' }
            } else {
                Write-Warning 'First upgrade: old operator cannot exclude starts; stopping it after idle verification before upgrading.'
                Invoke-MaintenanceDocker @('compose', '-f', (Join-Path $ProjectRoot 'compose.yaml'), 'stop', 'server') | Out-Null
            }
        }
        if (-not (Test-Path -LiteralPath $marker)) {
            [void](New-Item -ItemType Directory -Path (Split-Path $marker -Parent) -Force)
            $stream = [IO.File]::Open($marker, 'CreateNew', 'Write', 'None')
            try {
                $data = [Text.Encoding]::UTF8.GetBytes((@{owner=$owner} | ConvertTo-Json -Compress))
                $stream.Write($data, 0, $data.Length)
            } finally { $stream.Dispose() }
        }
        $env:WORKERCAM_MAINTENANCE_OWNER = $owner
        $context.RequiresUpgrade = $legacy -or $state -eq 'stopped'
        $context.LegacyWasRunning = $legacy
        if (($legacy -or $state -eq 'stopped') -and -not $StopOnly -and -not $RecoverOwner) {
            Invoke-MaintenanceDocker @('compose', '-f', (Join-Path $ProjectRoot 'compose.yaml'), 'up', '-d', '--build', '--wait', '--wait-timeout', '120', 'server') | Out-Null
            $status = Invoke-MaintenanceApi $ProjectRoot
            if ($status.PSObject.Properties.Name -notcontains 'maintenance' -or $status.maintenance.owner -cne $owner) {
                Invoke-MaintenanceDocker @('compose', '-f', (Join-Path $ProjectRoot 'compose.yaml'), 'stop', 'server') | Out-Null
                throw 'Replacement does not honor maintenance; left stopped. Camera unchanged.'
            }
        }
        Write-Host "Maintenance owner: $owner"
        return $context
    } catch {
        $env:WORKERCAM_MAINTENANCE_OWNER = $inherited
        $handle.Dispose()
        throw
    }
}

function Exit-ProjectMaintenance {
    param($Context, [bool]$Success)
    if (-not $Context -or -not $Context.Outer) { return }
    try {
        if ($Success) {
            $marker = Join-Path $Context.Root 'recordings/.maintenance.json'
            $saved = Get-Content -LiteralPath $marker -Raw | ConvertFrom-Json
            if ($saved.owner -cne $Context.Owner) { throw 'Cannot release another maintenance owner.' }
            if ((Get-MaintenanceOperator $Context.Root) -eq 'running') {
                $status = Invoke-MaintenanceApi $Context.Root 'end' $Context.Owner
                if ($status.PSObject.Properties.Name -notcontains 'maintenance' -or $null -ne $status.maintenance) {
                    throw 'Operator did not release maintenance; recovery required.'
                }
            } else { Remove-Item -LiteralPath $marker }
        } else { Write-Warning "Maintenance retained for owner $($Context.Owner). Inspect recovery state before owner-specific recovery." }
    } finally {
        $env:WORKERCAM_MAINTENANCE_OWNER = $Context.PreviousOwner
        $Context.Handle.Dispose()
    }
}

function Invoke-NetworkProcess {
    [CmdletBinding()]
    param([string]$FilePath, [string[]]$Arguments, [int]$TimeoutSeconds = 45,
        [string]$InputText, [hashtable]$Environment = @{}, [switch]$StreamOutput)
    # Windows command-line quoting, also supported by Windows PowerShell 5.1.
    $quoted = foreach ($argument in $Arguments) {
        '"' + [regex]::Replace([regex]::Replace($argument, '(\\*)"', '$1$1\"'), '(\\+)$', '$1$1') + '"'
    }
    $info = New-Object Diagnostics.ProcessStartInfo
    $info.FileName = $FilePath
    $info.WorkingDirectory = (Get-Location).ProviderPath
    $info.Arguments = $quoted -join ' '
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    $info.RedirectStandardInput = $true
    foreach ($key in $Environment.Keys) { $info.EnvironmentVariables[$key] = $Environment[$key] }
    $process = New-Object Diagnostics.Process
    $process.StartInfo = $info
    try {
        [void]$process.Start()
        if ($StreamOutput) {
            $streams = @(
                @{ Reader = $process.StandardOutput; Buffer = (New-Object Text.StringBuilder); Done = $false },
                @{ Reader = $process.StandardError; Buffer = (New-Object Text.StringBuilder); Done = $false }
            )
            foreach ($stream in $streams) { $stream.Task = $stream.Reader.ReadLineAsync() }
        } else {
            $output = $process.StandardOutput.ReadToEndAsync()
            $errors = $process.StandardError.ReadToEndAsync()
        }
        if ($InputText) { $process.StandardInput.Write($InputText.Replace("`r`n", "`n")) }
        $process.StandardInput.Close()
        if ($StreamOutput) {
            $watch = [Diagnostics.Stopwatch]::StartNew()
            do {
                foreach ($stream in $streams) {
                    if (-not $stream.Done -and $stream.Task.IsCompleted) {
                        $line = $stream.Task.GetAwaiter().GetResult()
                        if ($null -eq $line) { $stream.Done = $true }
                        else {
                            [void]$stream.Buffer.AppendLine($line)
                            Write-Host $line
                            $stream.Task = $stream.Reader.ReadLineAsync()
                        }
                    }
                }
                if ($watch.Elapsed.TotalSeconds -ge $TimeoutSeconds) {
                    if (-not $process.HasExited) { & taskkill.exe /PID $process.Id /T /F 2>$null | Out-Null }
                    throw "$([IO.Path]::GetFileName($FilePath)) timed out after $TimeoutSeconds seconds."
                }
                Start-Sleep -Milliseconds 10
            } while (-not $process.HasExited -or @($streams | Where-Object { -not $_.Done }).Count)
            $process.WaitForExit()
            $result = $streams[0].Buffer.ToString()
            $errorText = $streams[1].Buffer.ToString()
        } else {
            if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
                # Kill the command and descendants (including a blocked SSH child).
                & taskkill.exe /PID $process.Id /T /F 2>$null | Out-Null
                throw "$([IO.Path]::GetFileName($FilePath)) timed out after $TimeoutSeconds seconds."
            }
            $result = $output.GetAwaiter().GetResult()
            $errorText = $errors.GetAwaiter().GetResult()
        }
        if ($process.ExitCode -ne 0) {
            throw "$([IO.Path]::GetFileName($FilePath)) failed ($($process.ExitCode)): $errorText $result"
        }
        if ($errorText -and -not $StreamOutput) { Write-Verbose $errorText.Trim() }
        return $result.Trim()
    } finally { $process.Dispose() }
}

function New-SshContext {
    param([string]$KeyPath, [Security.SecureString]$Password, [switch]$Fresh)
    if (-not $Password -and -not $KeyPath) {
        $Password = New-Object Security.SecureString
        'root'.ToCharArray() | ForEach-Object { $Password.AppendChar($_) }
    }
    $options = @('-o', 'StrictHostKeyChecking=accept-new', '-o', 'UpdateHostKeys=no', '-o', 'ConnectTimeout=5',
        '-o', 'ServerAliveInterval=5', '-o', 'ServerAliveCountMax=3')
    $environment = @{}
    $directory = $null
    if ($KeyPath) {
        if (-not (Test-Path -LiteralPath $KeyPath -PathType Leaf)) { throw 'SSH key file does not exist.' }
        $options += @('-i', (Resolve-Path -LiteralPath $KeyPath).Path, '-o', 'IdentitiesOnly=yes')
    }
    if ($Password) {
        # OpenSSH for Windows supports SSH_ASKPASS. Password never enters argv or a script.
        $directory = Join-Path ([IO.Path]::GetTempPath()) ('workercam-ssh-' + [guid]::NewGuid().ToString('N'))
        [void](New-Item -ItemType Directory -Path $directory)
        $credentialPath = Join-Path $directory 'credential.xml'
        (New-Object Management.Automation.PSCredential('root', $Password)) | Export-Clixml -LiteralPath $credentialPath
        $helper = @'
$credential = Import-Clixml -LiteralPath $env:WORKERCAM_SSH_CREDENTIAL
[Console]::WriteLine($credential.GetNetworkCredential().Password)
'@
        [IO.File]::WriteAllText((Join-Path $directory 'askpass.ps1'), $helper)
        $powershellPath = Join-Path $PSHOME 'powershell.exe'
        if (-not (Test-Path $powershellPath)) { $powershellPath = Join-Path $PSHOME 'pwsh.exe' }
        [IO.File]::WriteAllText((Join-Path $directory 'askpass.cmd'),
            "@echo off`r`n`"$powershellPath`" -NoProfile -NonInteractive -ExecutionPolicy Bypass -File `"$directory\askpass.ps1`"`r`n")
        $environment = @{ SSH_ASKPASS = (Join-Path $directory 'askpass.cmd'); SSH_ASKPASS_REQUIRE = 'force';
            DISPLAY = 'workercam'; WORKERCAM_SSH_CREDENTIAL = $credentialPath }
        $options += @('-o', 'BatchMode=no', '-o', 'NumberOfPasswordPrompts=1', '-o', 'PreferredAuthentications=password')
    } else { $options += @('-o', 'BatchMode=yes') }
    if ($Fresh) {
        if (-not $directory) {
            $directory = Join-Path ([IO.Path]::GetTempPath()) ('workercam-ssh-' + [guid]::NewGuid().ToString('N'))
            [void](New-Item -ItemType Directory -Path $directory)
        }
        $options += @('-o', ('UserKnownHostsFile=' + (Join-Path $directory 'known_hosts')), '-o', 'GlobalKnownHostsFile=NUL')
    }
    return @{ Options = $options; Environment = $environment; Directory = $directory }
}

function Close-SshContext {
    param($Context)
    if ($Context -and $Context.Directory) {
        $path = [IO.Path]::GetFullPath($Context.Directory)
        $temp = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
        if (-not $path.StartsWith($temp, [StringComparison]::OrdinalIgnoreCase) -or
            [IO.Path]::GetFileName($path) -notmatch '^workercam-ssh-[a-f0-9]{32}$') { throw 'Invalid SSH temporary path.' }
        Remove-Item -LiteralPath $path -Recurse -Force
    }
}

function Invoke-MaixSsh {
    param($Context, [string]$Address, [string]$Command, [int]$TimeoutSeconds = 45)
    Invoke-NetworkProcess ssh.exe (@($Context.Options) + @('-T', "root@$Address", 'sh -s')) `
        -InputText ($Command + "`n") -Environment $Context.Environment -TimeoutSeconds $TimeoutSeconds
}

function Read-EnvText {
    param([string]$Text)
    $values = @{}
    foreach ($line in ($Text -split '\r?\n')) {
        if ($line -match '^\s*([A-Z][A-Z0-9_]*)\s*=\s*(.*?)\s*$') {
            if ($values.ContainsKey($Matches[1])) { throw "Duplicate configuration key: $($Matches[1])" }
            $values[$Matches[1]] = $Matches[2].Trim('"', "'")
        }
    }
    return $values
}

function Update-EnvText {
    param([string]$Text, [hashtable]$Values)
    $existing = Read-EnvText $Text
    $newline = "`n"
    if ($Text.Contains("`r`n")) { $newline = "`r`n" }
    foreach ($key in ($Values.Keys | Sort-Object)) {
        if ($existing.ContainsKey($key) -and $existing[$key] -ceq $Values[$key]) { continue }
        $pattern = '(?m)^[ \t]*' + [regex]::Escape($key) + '[ \t]*=[^\r\n]*'
        $line = "$key=$($Values[$key])"
        if ([regex]::IsMatch($Text, $pattern)) { $Text = [regex]::Replace($Text, $pattern, $line) }
        else { $Text = $Text.TrimEnd("`r", "`n") + $newline + $line + $newline }
    }
    return $Text
}

function Test-IPv4 {
    param([string]$Address)
    $ip = $null
    return ($Address -match '^\d{1,3}(\.\d{1,3}){3}$' -and
        [Net.IPAddress]::TryParse($Address, [ref]$ip) -and
        $ip.AddressFamily -eq [Net.Sockets.AddressFamily]::InterNetwork -and
        $ip.GetAddressBytes()[0] -gt 0 -and $ip.GetAddressBytes()[0] -lt 224 -and
        $ip.GetAddressBytes()[0] -ne 127 -and $Address -notlike '169.254.*')
}

function Set-HeadsetFirewallRule {
    param([string]$CameraIP)
    if (-not (Test-IPv4 $CameraIP)) { throw 'Firewall requires a valid camera IPv4 address.' }
    $displayName = 'MaixCAM headset UDP from camera'
    $settings = @{ Direction = 'Inbound'; Action = 'Allow'; Protocol = 'UDP';
        LocalPort = @('8004', '8005'); RemoteAddress = $CameraIP; Profile = 'Any'; Enabled = 'True' }
    $rules = @(Get-NetFirewallRule -PolicyStore PersistentStore -ErrorAction Stop |
        Where-Object DisplayName -eq $displayName)
    if ($rules.Count) {
        $rules | Set-NetFirewallRule @settings -ErrorAction Stop | Out-Null
    } else {
        New-NetFirewallRule -DisplayName $displayName @settings -ErrorAction Stop | Out-Null
    }
    Write-Host "Windows Firewall: inbound UDP 8004/8005 allowed from camera $CameraIP (all profiles)."
}

function ConvertTo-IPv4Number {
    param([string]$Address)
    $bytes = [Net.IPAddress]::Parse($Address).GetAddressBytes()
    return [uint64]$bytes[0] * 16777216 + [uint64]$bytes[1] * 65536 + [uint64]$bytes[2] * 256 + $bytes[3]
}

function Test-SameSubnet {
    param([string]$First, [string]$Second, [int]$PrefixLength)
    $size = [math]::Pow(2, 32 - $PrefixLength)
    return [math]::Floor((ConvertTo-IPv4Number $First) / $size) -eq [math]::Floor((ConvertTo-IPv4Number $Second) / $size)
}

function Assert-DockerNetworkRoute {
    param([string]$Address)
    if (-not (Test-IPv4 $Address)) { throw 'Docker route check requires a valid IPv4 address.' }
    $ids = @((Invoke-NetworkProcess docker.exe @('network', 'ls', '--quiet')) -split '\s+' | Where-Object { $_ })
    if (-not $ids.Count) { return }
    $networks = Invoke-NetworkProcess docker.exe (@('network', 'inspect') + $ids) | ConvertFrom-Json
    foreach ($network in $networks) {
        foreach ($config in $network.IPAM.Config) {
            $subnet = $config.Subnet -split '/'
            if ($subnet.Count -eq 2 -and (Test-IPv4 $subnet[0]) -and
                (Test-SameSubnet $Address $subnet[0] ([int]$subnet[1]))) {
                throw "Docker network '$($network.Name)' ($($config.Subnet)) overlaps Wi-Fi address $Address. Reconfigure that Docker network to a non-overlapping subnet, or remove it if unused, then rerun deployment. Stopping its containers does not remove the conflicting route."
            }
        }
    }
}

function Get-DeploymentInterfaces {
    $addresses = @(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction Stop)
    foreach ($adapter in @(Get-NetAdapter -ErrorAction Stop)) {
        if ($adapter.Status -ne 'Up' -or -not $adapter.HardwareInterface) { continue }
        $description = "$($adapter.Name) $($adapter.InterfaceDescription)"
        if ($description -match 'Docker|WSL|Hyper-V|VPN|Virtual|VMware|Tailscale|Loopback|Bluetooth') { continue }
        $kind = $null
        if ("$($adapter.PhysicalMediaType)" -match '802\.11|Wireless' -or $description -match 'Wi-Fi|Wireless|802\.11') { $kind = 'Wifi' }
        elseif ($description -match 'RNDIS|Remote NDIS|NCM|Sipeed|USB.*(Ethernet|Network|LAN)') { $kind = 'Usb' }
        if (-not $kind) { continue }
        foreach ($ip in $addresses | Where-Object InterfaceIndex -eq $adapter.ifIndex) {
            if (-not (Test-IPv4 $ip.IPAddress) -or $ip.AddressState -ne 'Preferred' -or $ip.SkipAsSource) { continue }
            [pscustomobject]@{ Kind = $kind; Index = [int]$adapter.ifIndex; Name = $adapter.Name;
                Address = $ip.IPAddress; PrefixLength = [int]$ip.PrefixLength }
        }
    }
}

function Get-UsbPeers {
    param($Interface, [string]$Hint)
    $candidates = @()
    if ($Hint) { $candidates += $Hint }
    $candidates += @(Get-NetNeighbor -InterfaceIndex $Interface.Index -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object State -in @('Reachable', 'Stale', 'Delay', 'Probe') | Select-Object -ExpandProperty IPAddress)
    $candidates += @(Get-NetRoute -InterfaceIndex $Interface.Index -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty NextHop)
    $size = [math]::Pow(2, 32 - $Interface.PrefixLength)
    $base = [uint64]([math]::Floor((ConvertTo-IPv4Number $Interface.Address) / $size) * $size)
    # Only bounded subnet discovery. Wider subnets require neighbors or -UsbPeerIP.
    if ($size -le 1024) {
        foreach ($offset in 1..([int]$size - 2)) {
            $number = $base + $offset
            $candidates += '{0}.{1}.{2}.{3}' -f (($number -shr 24) -band 255), (($number -shr 16) -band 255), (($number -shr 8) -band 255), ($number -band 255)
        }
    }
    @($candidates | Select-Object -Unique | Where-Object {
        (Test-IPv4 $_) -and $_ -ne $Interface.Address -and
        (Test-SameSubnet $_ $Interface.Address $Interface.PrefixLength) -and
        (ConvertTo-IPv4Number $_) -gt $base -and (ConvertTo-IPv4Number $_) -lt ($base + $size - 1)
    })
}

function Find-OpenSshPeers {
    param([string[]]$Addresses, [string]$LocalAddress)
    # Probe in parallel batches; bind to the USB interface, never a VPN route.
    for ($offset = 0; $offset -lt $Addresses.Count; $offset += 32) {
        $pending = @()
        try {
            foreach ($address in $Addresses[$offset..([math]::Min($offset + 31, $Addresses.Count - 1))]) {
                $client = New-Object Net.Sockets.TcpClient
                $client.Client.Bind((New-Object Net.IPEndPoint([Net.IPAddress]::Parse($LocalAddress), 0)))
                $pending += @{ Client = $client; Task = $client.ConnectAsync($address, 22); Address = $address }
            }
            $deadline = [datetime]::UtcNow.AddMilliseconds(600)
            while ([datetime]::UtcNow -lt $deadline -and @($pending | Where-Object { -not $_.Task.IsCompleted }).Count) {
                Start-Sleep -Milliseconds 20
            }
            foreach ($item in $pending) { if ($item.Client.Connected) { $item.Address } }
        } finally { foreach ($item in $pending) { $item.Client.Dispose() } }
    }
}

function Set-MaixWifi {
    param($Context, [string]$HostAddress, [string]$WifiSsid,
        [Security.SecureString]$WifiPassword, [string]$WifiMac)
    $source = [IO.File]::ReadAllText((Join-Path $PSScriptRoot '../maix/setup_wifi.py')).Replace("`r`n", "`n")
    $encoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($source))
    $settings = @{ssid=$WifiSsid;mac=$WifiMac}
    if ($WifiPassword) {
        $settings.password = (New-Object Management.Automation.PSCredential('wifi', $WifiPassword)).GetNetworkCredential().Password
    }
    $json = $settings | ConvertTo-Json -Compress
    $payload = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($json))
    $command = "python3 -c 'import base64,io,sys;sys.stdin=io.StringIO(base64.b64decode(sys.stdin.buffer.read()).decode(`"utf-8`"));exec(compile(base64.b64decode(`"$encoded`"), `"wifi-setup`", `"exec`"))' <<'WORKERCAM_WIFI'`n$payload`nWORKERCAM_WIFI"
    try { return (Invoke-MaixSsh $Context $HostAddress $command -TimeoutSeconds 120 | ConvertFrom-Json) }
    finally { $settings.Clear(); $json = $null; $payload = $null; $command = $null }
}

function Get-LaptopWifiSsid {
    param([int]$InterfaceIndex)
    $adapter = @(Get-NetAdapter -ErrorAction Stop | Where-Object ifIndex -eq $InterfaceIndex)
    if ($adapter.Count -ne 1) { throw 'Cannot identify the selected laptop Wi-Fi adapter.' }
    $output = & netsh.exe wlan show interfaces
    if ($LASTEXITCODE -ne 0) { throw 'Cannot read connected Wi-Fi SSID. Check Windows Wi-Fi/location permissions.' }
    $guid = ([guid]$adapter[0].InterfaceGuid).ToString()
    $blocks = ($output -join "`n") -split '(?m)^\s*GUID\s*:\s*'
    foreach ($block in $blocks) {
        if ($block.StartsWith($guid, [StringComparison]::OrdinalIgnoreCase) -and
                $block -match '(?m)^\s*SSID\s*: ([^\r\n]+)\r?$') {
            $ssid = $Matches[1]
            if ([Text.Encoding]::UTF8.GetByteCount($ssid) -le 32) { return $ssid }
        }
    }
    throw 'Selected laptop Wi-Fi has no readable connected SSID. Connect Wi-Fi and check Windows location permissions.'
}

function Assert-LaptopWifiSsid {
    param([string]$WifiSsid, [string]$PcIp)
    $interfaces = @(Get-DeploymentInterfaces | Where-Object { $_.Kind -eq 'Wifi' -and $_.Address -eq $PcIp })
    if ($interfaces.Count -ne 1 -or (Get-LaptopWifiSsid $interfaces[0].Index) -cne $WifiSsid) {
        throw 'WifiSsid must exactly match the connected laptop Wi-Fi SSID and PcIp must belong to that adapter.'
    }
}

function Select-LaptopWifi {
    param([array]$Interfaces, [string]$CameraAddress, [int]$InterfaceIndex)
    $route = @(Find-NetRoute -RemoteIPAddress $CameraAddress -ErrorAction Stop)
    $candidates = @($Interfaces | Where-Object { $_.Kind -eq 'Wifi' -and
        (-not $InterfaceIndex -or $_.Index -eq $InterfaceIndex) })
    $routeAddresses = @($route | Where-Object { $_.PSObject.Properties['IPAddress'] } | Select-Object -ExpandProperty IPAddress)
    $selected = @($candidates | Where-Object { $_.Index -in $route.InterfaceIndex -and $_.Address -in $routeAddresses })
    if ($selected.Count -ne 1) {
        throw "Cannot select a Wi-Fi route to $CameraAddress. Candidates: $($candidates | ConvertTo-Json -Compress). Use -WifiInterfaceIndex; correct VPN/Windows routes if needed."
    }
    return $selected[0]
}

function Test-HostUdpListeners {
    [CmdletBinding()]
    param([int[]]$Ports = @(8004, 8005))
    if ($env:OS -ne 'Windows_NT') { return $true }
    $hasGetNetUdp = [bool](Get-Command Get-NetUDPEndpoint -ErrorAction SilentlyContinue)
    foreach ($port in $Ports) {
        $bound = $false
        if ($hasGetNetUdp) {
            try {
                $endpoints = @(Get-NetUDPEndpoint -LocalPort $port -ErrorAction Stop)
                if ($endpoints.Count -gt 0) { $bound = $true }
            } catch {
                try {
                    $output = & netstat.exe -ano -p udp 2>$null
                    if ($output -match ":$port\s") { $bound = $true }
                } catch { }
            }
        } else {
            try {
                $output = & netstat.exe -ano -p udp 2>$null
                if ($output -match ":$port\s") { $bound = $true }
            } catch { }
        }
        if (-not $bound) { return $false }
    }
    return $true
}

function Confirm-HostUdpListeners {
    [CmdletBinding()]
    param(
        [string]$ProjectRoot,
        [int[]]$Ports = @(8004, 8005)
    )
    if ($env:OS -ne 'Windows_NT') { return }
    if (-not $ProjectRoot) { $ProjectRoot = (Split-Path -Parent $PSScriptRoot) }
    if (-not (Test-HostUdpListeners -Ports $Ports)) {
        $maintenance = Enter-ProjectMaintenance $ProjectRoot
        $success = $false
        try {
        Write-Host "Windows host UDP listener ($($Ports -join ', ')) missing; checking recording status and recreating container..."
        Stop-PcRuntime -CheckOnly
        $composeFile = Join-Path $ProjectRoot 'compose.yaml'
        & docker compose -f $composeFile up -d --force-recreate --no-deps server
        if ($LASTEXITCODE -ne 0) {
            throw 'Docker recreate failed while recovering UDP return listeners.'
        }
        if (-not (Test-HostUdpListeners -Ports $Ports)) {
            throw "Windows host UDP listener ($($Ports -join ', ')) remains missing after container recreation."
        }
        Write-Host "Recreated container; host UDP listeners verified ($($Ports -join ', '))."
        $success = $true
        } finally { Exit-ProjectMaintenance $maintenance $success }
    }
}

function Install-MaixCamera {
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
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$parsedIp = $null
if (-not [Net.IPAddress]::TryParse($PcIp, [ref]$parsedIp)) { throw 'PcIp must be the PC LAN IPv4 address.' }
if ($KeyPath -and $Password) { throw 'Use either -KeyPath or -Password.' }
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
    if (-not (Test-Path -LiteralPath (Join-Path $ProjectRoot $source) -PathType Leaf)) {
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
    $maintenance = Enter-ProjectMaintenance $ProjectRoot
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
        $content = [IO.File]::ReadAllText((Join-Path $ProjectRoot $source)).Replace("`r`n", "`n")
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
for name in ('.asoundrc', '.talkback_token', '.bluetooth_device', '.bluetooth_device.capture-volume'):
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

}

function Install-PcRuntime {
[CmdletBinding()]
param([switch]$Build, [switch]$CheckOnly, [switch]$Recreate, [switch]$NoCache)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $ProjectRoot
$maintenance = $null
$maintenanceSuccess = $false
try {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        throw 'Install Docker Desktop, select Linux containers, and open Docker Desktop first.'
    }
    Write-Host '[PC 1/5] Checking Docker Desktop Linux engine...'
    $engineType = & docker info --format '{{.OSType}}' 2>$null
    if ($LASTEXITCODE -ne 0 -or $engineType -ne 'linux') {
        throw 'Open Docker Desktop and wait for the Linux engine to be running, then try again.'
    }
    if (-not (Test-Path -LiteralPath .env -PathType Leaf)) {
        if ($CheckOnly) { throw 'Missing .env. Copy .env.example and configure the camera before deployment.' }
        $maintenance = Enter-ProjectMaintenance $ProjectRoot -StopOnly
        Copy-Item -LiteralPath .env.example -Destination .env
        $maintenanceSuccess = $true
        throw 'Created .env. Set MAIX_IP to your camera address, save the file, then run this command again.'
    }
    Write-Host '[PC 2/5] Validating configuration...'
    Write-Host 'TB3 release: update PC and camera together using scripts/deploy.ps1; older camera releases cannot accept talkback.'
    $composeOptions = @('compose', '-f', 'compose.yaml')
    $configuration = & docker @composeOptions config --format json
    if ($LASTEXITCODE -ne 0) { throw 'Compose configuration is invalid. Check .env.' }
    $service = ($configuration | ConvertFrom-Json).services.server
    if ($service.environment.RTSP_TRANSPORT -ne 'tcp' -or $service.environment.STREAM_MODE -ne 'video') {
        throw 'Set RTSP_TRANSPORT=tcp and STREAM_MODE=video in .env for this Docker deployment.'
    }
    $cameraCommand = @($service.command)
    $cameraIndex = [Array]::IndexOf($cameraCommand, '--maix-ip')
    if ($cameraIndex -lt 0 -or $cameraIndex + 1 -ge $cameraCommand.Count) {
        throw 'Compose command is missing --maix-ip for the camera firewall rule.'
    }
    Assert-DockerNetworkRoute $cameraCommand[$cameraIndex + 1]
    if ($env:OS -eq 'Windows_NT') {
        foreach ($listenerPid in @(Get-NetTCPConnection -LocalPort 8000,8554,8889 -State Listen -ErrorAction SilentlyContinue |
                Select-Object -ExpandProperty OwningProcess -Unique)) {
            $listenerProcess = Get-CimInstance Win32_Process -Filter "ProcessId = $listenerPid"
            if ($listenerProcess.Name -in @('python.exe', 'pythonw.exe', 'mediamtx.exe')) {
                throw 'A native media service owns a required port. Ask the installer to stop that project service before migrating to Docker.'
            }
        }
    }
    # Checks the project's container directly, so a different local HTTP server cannot pass.
    Write-Host '[PC 3/5] Checking port conflicts and recording status...'
    Stop-PcRuntime -CheckOnly
    if ($CheckOnly) { Write-Host 'PC preflight passed.'; return }
    Set-HeadsetFirewallRule $cameraCommand[$cameraIndex + 1]
    $maintenance = Enter-ProjectMaintenance $ProjectRoot
    New-Item -ItemType Directory -Force -Path recordings | Out-Null
    $upOptions = @('up', '-d', '--wait', '--wait-timeout', '120')
    if ($Build) { $upOptions += '--build' }
    if ($Recreate) { $upOptions += '--force-recreate' }
    Write-Host '[PC 4/5] Building/starting Docker service and waiting for container health...'
    if ($Build) { Write-Host 'The first build downloads images and dependencies and can take several minutes.' }
    if ($NoCache) {
        & docker @composeOptions build --no-cache server
        if ($LASTEXITCODE -ne 0) { throw 'Fresh Docker build failed; fix the error and rerun deployment.' }
        $upOptions = @($upOptions | Where-Object { $_ -ne '--build' })
    }
    & docker @composeOptions @upOptions server
    if ($LASTEXITCODE -ne 0) {
        throw 'Docker deployment failed. Run: docker compose logs --tail 80 server'
    }
    if ($env:OS -eq 'Windows_NT') {
        $portsToCheck = @(8004, 8005)
        if (-not (Test-HostUdpListeners -Ports $portsToCheck)) {
            Write-Host 'Windows host UDP 8004/8005 listener missing; checking recording status and recreating container...'
            Stop-PcRuntime -CheckOnly
            & docker @composeOptions up -d --force-recreate --no-deps server
            if ($LASTEXITCODE -ne 0) {
                throw 'Docker recreate failed while recovering UDP return listeners.'
            }
            if (-not (Test-HostUdpListeners -Ports $portsToCheck)) {
                throw 'Docker container started, but Windows host UDP listeners on port 8004/8005 are missing.'
            }
            Write-Host 'Recreated container; Windows host UDP 8004/8005 listeners verified.'
        }
    }
    Write-Host '[PC 5/5] Checking the operator page from Windows...'
    $operatorDeadline = (Get-Date).AddSeconds(30)
    do {
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8000/operator_test.html' -TimeoutSec 2
            $ready = $response.StatusCode -eq 200
        } catch { $ready = $false }
        if ($ready) { break }
        if ((Get-Date) -ge $operatorDeadline) {
            throw 'Docker started, but Windows cannot reach the operator page. Check Docker port forwarding and run: docker compose logs --tail 80 server'
        }
        Start-Sleep -Milliseconds 500
    } while ($true)
    Write-Host 'Operator UI verified: http://127.0.0.1:8000 (admin / admin)'
    Write-Host 'TCP video and separate microphone return on UDP 8004. Confirm live picture and sound in the browser.'
    $status = Invoke-MaintenanceApi $ProjectRoot
    if ($status.PSObject.Properties.Name -notcontains 'maintenance' -or $status.maintenance.owner -cne $maintenance.Owner) {
        Invoke-MaintenanceDocker @('compose', '-f', 'compose.yaml', 'stop', 'server') | Out-Null
        throw 'Operator does not honor the maintenance marker; left stopped.'
    }
    $maintenanceSuccess = $true
} finally { try { Exit-ProjectMaintenance $maintenance $maintenanceSuccess } finally { Pop-Location } }

}

function Stop-PcRuntime {
[CmdletBinding()]
param([switch]$CheckOnly)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $ProjectRoot
$maintenance = $null
$maintenanceSuccess = $false
try {
    if ($CheckOnly) { [void](Get-MaintenanceOperator $ProjectRoot) }
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
            if ($recordingStatus.recording -or
                ($recordingStatus.PSObject.Properties.Name -contains 'finalizing' -and $recordingStatus.finalizing)) {
                throw 'Stop the recording in the operator UI and wait for finalization before stopping or updating Docker.'
            }
        } elseif ($state -notin @('exited', 'created')) {
            throw "Operator container is $state; recording status cannot be verified. Inspect Docker logs before stopping or updating."
        }
    }
    if (-not $CheckOnly) {
        $maintenance = Enter-ProjectMaintenance $ProjectRoot -StopOnly
        & docker @composeOptions stop server
        if ($LASTEXITCODE -ne 0) { throw 'Docker could not stop the operator.' }
        Write-Host 'PC operator stopped. Saved recordings remain in the recordings folder.'
        $maintenanceSuccess = $true
    }
} finally { try { Exit-ProjectMaintenance $maintenance $maintenanceSuccess } finally { Pop-Location } }

}

Export-ModuleMember -Function *
