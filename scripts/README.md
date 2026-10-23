# Fresh-install

The only executable PowerShell script is `scripts/deploy.ps1`. Follow the
[Windows setup guide](../README.md) for prerequisites and the complete command.
`NetworkDeployment.psm1` contains the internal deployment functions; it is
loaded by the script and is not a separate setup command.

Every normal run discovers USB/Wi-Fi addresses, requires the laptop's SSID and
an explicit headset MAC, stops all running Docker containers, resets WorkerCam
settings, installs/reboots the camera, and builds/recreates the PC without cache.
Completed recordings and Bluetooth bonds remain. There is no application backup
or rollback. Failed installs retain maintenance; fix the reported cause and
rerun the same fresh-install command.

## Entry points and checks

Run from the project root in administrator PowerShell:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "& .\scripts\deploy.ps1 -WifiSsid 'YOUR_PC_WIFI_SSID' -HeadsetMac '6C:16:29:7B:00:D4' -WifiPassword (Read-Host 'Wi-Fi password' -AsSecureString)"
```

The same script supports `-DryRun` for read-only discovery. Supply
`-WifiInterfaceIndex`, `-UsbInterfaceIndex` or `-UsbPeerIP` only when automatic
selection is ambiguous. Dry run does not prove installation or media acceptance.

## Windows firewall and missing headset microphone audio

Setup refreshes inbound UDP8004/8005 for the camera's current Wi-Fi IP on all
Windows profiles. Missing UDP listeners permit one project-container recreation;
missing headset return permits one recording-safe PC stop/start.

Existing Docker subnets must not contain the laptop/camera Wi-Fi IPs. An unused
network can still reserve a conflicting route: e.g. `172.20.0.0/16` against an
iPhone hotspot at `172.20.10.x`. Setup reports its name and fails before camera
installation/build. Reconfigure its owning project, or remove it only if unused.

Final checks cover matching camera identity/SSID, TB3, headset connection, Docker
health and actual video/audio decoding. Open the browser and verify audible
speech in both directions; automation cannot confirm that people hear clearly.
