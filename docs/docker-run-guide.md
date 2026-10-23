# Docker installation and recovery

Use the single [fresh-install script](../README.md). All deployment operations
run through `scripts/deploy.ps1`; component launchers have been removed.

## Requirements

- Windows: Docker Desktop Linux engine/WSL 2, Compose supporting `up --wait`,
  administrator PowerShell and Windows OpenSSH Client.
- Camera: MaixPy launcher at `/maixapp/apps`, Python 3, BlueZ, BlueALSA,
  FFmpeg, `arecord`, `aplay`, SCO utilities, USB networking and root/root SSH.
- Connect laptop to the desired Wi-Fi and keep USB attached for installation.

Setup generates `.env` from discovered addresses, configures the camera's PC
destination, installs SCO duplex/TB3, reboots the camera and builds the PC image
without cache. No host Python, Node or FFmpeg installation is required.
It overwrites the camera app at `/maixapp/apps/maix_rtsp` and `/etc/rc.local`;
use firmware prepared for WorkerCam. This is an application reinstall, not a
firmware flash. Completed recordings are retained; no application rollback.

## Network and firewall

| Connection | Required access |
| --- | --- |
| Browser → operator | PC loopback TCP 8000. |
| Browser → WebRTC signaling | PC loopback TCP 8889. |
| Browser ↔ WebRTC media | PC loopback UDP 8189. |
| Local diagnostics → relay | PC loopback TCP 8554. |
| PC → camera video | Camera TCP 8554, H.264 over RTSP/TCP. |
| Camera → PC microphone | PC UDP 8004/8005, published through Docker. |
| PC → camera talkback | Camera UDP 9002. |
| PC → camera status/clock | Camera TCP 8765. |
| Installer → camera SSH | Camera TCP 22. |

MediaMTX advertises `127.0.0.1` for the local browser and does not advertise
container-only interfaces. Camera microphone input is the host mapping that
accepts LAN traffic. On Windows Private networks, an administrator can allow the
known camera address (replace the example):

```powershell
New-NetFirewallRule -DisplayName 'WorkerCam microphone' -Direction Inbound -Action Allow -Protocol UDP -LocalPort 8004,8005 -RemoteAddress 192.168.1.7 -Profile Private
```

No router forwarding is needed. Do not expose the prototype API to the internet.
Remote browsers require separate authentication and HTTPS.

Earlier bridge failures involved RTSP's negotiated UDP path. This route uses TCP
for RTSP and fixed UDP microphone ports. It still needs physical verification on
the customer's PC; configuration changes do not establish a latency improvement.

## Diagnostics

```powershell
docker compose ps
docker compose logs --tail 80 server
```

Docker subnets must not overlap the Wi-Fi IPs. Stopped containers can leave
networks/routes behind. The installer reports conflicting network names;
reconfigure the owning project or remove the network if unused before retrying.

Finish recordings, fix the printed cause and rerun the same fresh-install
command. It replaces stale maintenance under the host lock. Do not start a
second camera capture process manually: the MaixPy launcher owns video startup.
Historical session commands describe older versions, not current entry points.
