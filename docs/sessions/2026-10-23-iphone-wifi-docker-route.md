# iPhone hotspot deployment recovery — 2026-10-23

User reported a complete fresh deployment on `iPhoneYdt` failing with an unhealthy
PC container. The camera install/reboot and Docker build had completed.

## Proven cause and recovery

- Container startup repeatedly timed out probing camera RTSP at
  `172.20.10.7:8554`. Windows could open that same TCP endpoint.
- Docker network inspection found the unused `n8n_default` network reserving
  `172.20.0.0/16`, overlapping the iPhone hotspot (`172.20.10.2` laptop,
  `172.20.10.7` camera). The WorkerCam network itself used `172.18.0.0/16`.
- Saved network inspection to `.runtime/iphone-n8n-network-before.json`, verified
  its attached-container map was empty, then removed only `n8n_default`.
  A new one-shot container immediately connected to camera TCP; the existing
  restart loop then reached healthy startup. No Docker volumes were removed.
- Released retained maintenance owner `2e5efb14c8274202b579e4ad819d4e81`
  using `scripts/recover_maintenance.ps1` after verifying the running service.
- Initial browser verification decoded video but received no audio. Subsequent
  logs showed headset publication loss, and Windows lacked UDP8004 (8005 existed).
  Used the existing maintenance lock and idle checks for one scoped Compose
  stop/start. Both host UDP listeners passed afterward; maintenance released.

## Changes and checks

Added `Assert-DockerNetworkRoute`, reusing IPv4/subnet and child-process helpers.
Combined deployment checks the laptop before switching Wi-Fi/resetting runtime,
then checks the discovered camera before installation. PC deployment checks its
configured camera before mutation, including check-only mode. Conflicts fail
with the network name/subnet and guidance to reconfigure it or remove it if
unused. The scripts do not automatically delete other projects' networks.

- All 30 `test_network_deployment.py` checks passed. Enhanced the new overlap
  test to cover multiple newline-separated network IDs; focused rerun passed.
- Actual helper calls on Windows PowerShell 5.1 passed for both hotspot IPs.
- Compose validation and `git diff --check` passed.
- FFmpeg decoded three seconds each of `/maix01` and `/headsetmic` before the
  later audio publication loss; that initial decode did not prove continuity.
- After scoped stop/start, real Chromium received H.264 768x432 and PCMU audio
  at all four samples across 15.047 seconds: 300 additional decoded frames
  (~19.94fps), audio bytes increased from 28,000 to 148,480, zero reported lost
  packets, audio unmuted/playing, no page errors. Screenshot visually confirmed
  clear live video. Evidence: `.runtime/iphone-wifi-live-continuity.{mjs,json,png}`.
- Bluetooth status reported the selected headset connected; TB3 Talk available
  without error. Final recording idle, rotation zero, maintenance null, Docker
  healthy. No camera changes or complete fresh reinstall were needed in recovery.

Audible duplex, Talk speech, new recordings and prolonged stability were not
retested. Restarting n8n with another overlapping subnet can reintroduce the
route conflict; configure that project's network before bringing it back.
