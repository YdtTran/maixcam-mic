# Final hardening paired redeployment

User authorized redeploying the completed 22/22 implementation tasks. Read
AGENTS.md, the remaining-tasks note and P526 deployment evidence first.
Preserved the existing dirty tree, separate desktop-setup proposal, headset
binding, network settings and saved recordings. No application repair or
OpenSpec archival was performed.

## Deployment

Initial Docker service was healthy; recording was idle, rotation zero and
maintenance null. Ran the existing maintenance-safe workflow:

```powershell
powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File .\scripts\deploy.ps1 -UsbInterfaceIndex 17 -UsbPeerIP 10.172.16.1 -WifiInterfaceIndex 18 -Force
```

Discovery confirmed camera 192.168.1.7, PC/return destination 192.168.1.4,
and camera USB 10.172.16.1. Configuration reported UNCHANGED. Maintenance
excluded capture while the PC stopped, camera installed/rebooted and Docker
rebuilt/recreated. Deployment completed successfully, including both stream
decodes, Windows HTTP, camera processes and TB3 compatibility checks.
The build reused the previously successful cached Python base digest.
Camera backup: `/root/workercam-backup-011259f220d846b6bfa769e878b227be`.
Raw output: `.runtime/hardening-final-redeployment.log`.

## Real workflow checks

- Chromium login and clear 768x432 video passed at 0 and 90 degrees; inspected
  the portrait screenshot. Browser reported no page errors.
- Talk start/stop signaling passed with a synthetic browser microphone. This
  does not establish audible delivery to the disconnected headset.
- Created and retained `20261021T152749Z_7c83659a.mp4`, 1,985,770 bytes.
  Finalized successfully; ffprobe confirms copied 768x432 H.264, 90-degree
  display matrix and three AAC tracks. Portrait playback, seeking to two
  seconds and return to clear live video passed.
- Native browser download passed with recording-file fetch and application
  Blob creation forbidden. Filename and size match; downloaded and original
  files have identical SHA256. Explicit byte range returned HTTP 206 with
  `bytes 10-29/1985770` and 20 bytes.
- 60.177-second Chromium continuity: 1,203 additional decoded frames
  (19.99 fps), increasing video/audio at every five-second sample, zero
  reported packet loss, and an unmuted playing audio element.

Evidence: `.runtime/hardening-final-live-ui*`,
`.runtime/hardening-final-live-{0,90,recording}.png` and
`.runtime/hardening-final-live-continuity*`. A first diagnostic ffprobe used
the wrong container directory `/recordings`; rerunning against the actual
`/app/recordings` mount passed.

## Final runtime and limits

Docker healthy; recording idle and not finalizing; no recording error or
metadata warnings; rotation/effective rotation zero; maintenance released.
Talk API available on TB3 without error. Headset remained **disconnected**
through the final check. Asked user to keep it powered on and disconnected
from other hosts. No Bluetooth reset, re-pairing or additional service restart
was attempted. Five-second return decode was silence (-91 dB mean and peak),
so browser audio transport is proven but actual headset capture is not.
Audible duplex acceptance remains pending; earlier P526 acceptance does not
establish acceptance of this rollout.

No full automated-suite rerun, older opt-in UDP fixture, long-duration,
physical latency or A/V synchronization trial. The implementation session
records the prior passing automated checks. Known rollback port-format defect
remains unresolved; recovery snapshots retained. Paired deployment and the
video/recording/download workflows passed; overall operational acceptance
remains qualified by the disconnected headset.
