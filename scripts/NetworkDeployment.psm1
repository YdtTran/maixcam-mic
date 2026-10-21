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
    param([string]$ProjectRoot, [switch]$StopOnly, [string]$RecoverOwner)
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
        if (Test-Path -LiteralPath $marker) {
            $saved = Get-Content -LiteralPath $marker -Raw | ConvertFrom-Json
            if (-not $RecoverOwner -or $saved.owner -cne $owner) {
                throw "Maintenance marker retained. Use scripts/recover_maintenance.ps1 with its recorded owner after inspecting recovery state."
            }
        } elseif ($RecoverOwner) { throw 'No maintenance marker to recover.' }
        $state = Get-MaintenanceOperator $ProjectRoot
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
    param([string]$KeyPath, [Security.SecureString]$Password)
    $options = @('-o', 'StrictHostKeyChecking=yes', '-o', 'UpdateHostKeys=no', '-o', 'ConnectTimeout=5',
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
        $options += @('-o', 'BatchMode=no', '-o', 'NumberOfPasswordPrompts=1')
    } else { $options += @('-o', 'BatchMode=yes') }
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

function Save-PreviousRuntime {
    param($Container, [string]$Backup)
    # Inspect the existing container: the edited Compose file cannot recover old mounts.
    $environment = @{}
    foreach ($entry in $Container.Config.Env) {
        $key, $value = $entry -split '=', 2
        $environment[$key] = $value
    }
    $volumes = @()
    $legacyReady = $true
    $tokenDigest = $null
    foreach ($mount in $Container.Mounts) {
        $source = $mount.Source
        if ($mount.Destination -eq '/app/.talkback_token') {
            $legacyReady = $false
            $saved = Join-Path $Backup '.talkback_token'
            if (Test-Path -LiteralPath $source -PathType Leaf) {
                Copy-Item -LiteralPath $source -Destination $saved
            } else {
                # Docker can retain a readable bind after its original checkout disappears.
                try { Invoke-NetworkProcess docker.exe @('cp', "$($Container.Id):/app/.talkback_token", $saved) | Out-Null }
                catch { Write-Warning 'Legacy runtime token could not be saved; old-release talkback recovery may be unavailable.' }
            }
            if (Test-Path -LiteralPath $saved -PathType Leaf) {
                $value = [IO.File]::ReadAllText($saved).Trim()
                if ($value -match '^[0-9a-fA-F]{32}$') {
                    $sha = [Security.Cryptography.SHA256]::Create()
                    try { $tokenDigest = [BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($value.ToLowerInvariant()))).Replace('-', '').ToLowerInvariant() }
                    finally { $sha.Dispose() }
                    $legacyReady = $true
                }
                $source = $saved
            }
        }
        if ($mount.Destination -eq '/app/recordings' -and -not (Test-Path -LiteralPath $source -PathType Container)) {
            $source = Join-Path $Backup 'recordings'
            [void](New-Item -ItemType Directory -Path $source)
            Invoke-NetworkProcess docker.exe @('cp', "$($Container.Id):/app/recordings/.", $source) | Out-Null
        }
        if ($mount.Type -eq 'volume') { $source = $mount.Name }
        $volume = @{ type = $mount.Type; source = $source; target = $mount.Destination; read_only = -not $mount.RW }
        if ($mount.Type -eq 'bind') { $volume.bind = @{ create_host_path = $false } }
        $volumes += $volume
    }
    $ports = @()
    foreach ($property in $Container.HostConfig.PortBindings.PSObject.Properties) {
        $port, $protocol = $property.Name -split '/'
        foreach ($binding in $property.Value) {
            $ports += @{ target = [int]$port; published = $binding.HostPort; host_ip = $binding.HostIp; protocol = $protocol }
        }
    }
    $service = @{ image = $Container.Image; command = @($Container.Config.Cmd); entrypoint = $Container.Config.Entrypoint
        environment = $environment; volumes = $volumes; ports = $ports
        working_dir = $Container.Config.WorkingDir; user = $Container.Config.User
        restart = $Container.HostConfig.RestartPolicy.Name; init = $Container.HostConfig.Init
        logging = @{ driver = $Container.HostConfig.LogConfig.Type; options = $Container.HostConfig.LogConfig.Config }
        stop_grace_period = '2m' }
    if ($Container.Config.Healthcheck) {
        $health = $Container.Config.Healthcheck
        $service.healthcheck = @{ test = @($health.Test); interval = "$($health.Interval)ns"; timeout = "$($health.Timeout)ns"
            start_period = "$($health.StartPeriod)ns"; retries = $health.Retries }
    }
    $configuration = @{ name = 'maix-cam-server'; services = @{ server = $service } }
    $named = @{}
    foreach ($mount in $Container.Mounts) {
        if ($mount.Type -eq 'volume') { $named[$mount.Name] = @{ external = $true; name = $mount.Name } }
    }
    if ($named.Count) { $configuration.volumes = $named }
    $path = Join-Path $Backup 'rollback.compose.json'
    [IO.File]::WriteAllText($path, ($configuration | ConvertTo-Json -Depth 20))
    return @{ Path = $path; LegacyReady = $legacyReady; TokenDigest = $tokenDigest }
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
        & (Join-Path $ProjectRoot 'stop_docker_pc.ps1') -CheckOnly
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

Export-ModuleMember -Function *
