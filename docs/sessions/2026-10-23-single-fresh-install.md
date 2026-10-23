# One fresh-install script — 2026-10-23

User requested rewriting README and retaining exactly one fresh-install script,
removing unnecessary scripts. Kept the existing `scripts/deploy.ps1` command.

## Changes

- Deleted `run_all.ps1`, `deploy_maix.ps1`, `deploy_pc.ps1`,
  `stop_docker_pc.ps1`, and `scripts/recover_maintenance.ps1`.
- Moved required camera installation, PC build/health verification and
  recording-safe stop bodies into `scripts/NetworkDeployment.psm1` as
  `Install-MaixCamera`, `Install-PcRuntime`, and `Stop-PcRuntime`.
  The combined installer and UDP recovery call these functions directly.
- Removed the child-PowerShell dispatcher and its now-unused timeout parameter.
  Kept existing stage output, validations, firmware staging, maintenance locking,
  firewall/UDP checks, hard-fresh defaults and failure behavior.
- Rewrote root README in Vietnamese around one complete fresh-install command,
  Windows prerequisites, recording preservation and the stop-all/reset effects.
  Updated current technical guides and AGENTS build instructions; dated session
  records and OpenSpec implementation history retain their historical filenames.
- Adapted isolated tests to exercise internal functions with mocked external
  operations. Added an inventory assertion that only the one deployment `.ps1`
  remains in the root/scripts surface. Removed the redundant run_all wrapper test.

## Verification

- Focused component checks: 21 tests ran, one skipped, no failures.
- Focused deployment checks: 29 tests passed.
- Full Python suite: 221 tests ran, eight skipped, no failures. Evidence:
  `.runtime/single-deploy-python.log`.
- Windows PowerShell 5.1 parser accepted the script and module. Diff whitespace
  checks passed; current docs/code have no retired-script call sites.
- Actual elevated read-only `scripts/deploy.ps1 -WifiSsid iPhoneYdt
  -HeadsetMac 6C:16:29:7B:00:D4 -DryRun` returned exit 0. Discovered laptop
  172.20.10.2, camera 172.20.10.7, USB peer 10.172.17.1 and expected camera MAC.
  Evidence: `.runtime/single-deploy-dryrun.{log,exit}`.

At that checkpoint no full fresh reinstall had been run. The user subsequently
authorized running the entire workflow; the live result follows.

## Authorized full redeployment

Ran elevated Windows PowerShell 5.1 using the sole entry point:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\deploy.ps1 -WifiSsid 'iPhoneYdt' -HeadsetMac '6C:16:29:7B:00:D4'
```

The camera was already on the required SSID, so no Wi-Fi password was needed.
Both attempts reset configuration, installed/rebooted the camera and rebuilt the
PC without cache. The first reached a healthy container but exposed a regression
in the moved stop function: module strict mode rejected absent optional
`finalizing` while checking idle recording status during missing-UDP recovery.
Changed that read to guard property presence, matching the shared maintenance
API helper. Added a regression exercising `{recording:false}` with no
`finalizing`. All 22 focused component tests passed (one skipped); the final full
Python suite ran 222 tests, eight skipped, no failures. Evidence:
`.runtime/single-deploy-final-python.log`.

Reran the complete installer from the beginning. It replaced the failed
maintenance marker under the host lock, reinstalled/rebooted camera and rebuilt
PC without cache. Final build took 61.4 seconds; startup, Windows HTTP, host UDP,
camera configuration/identity, headset connection, TB3 and both media decoding
checks passed. It printed `Deployment completed successfully.` and exited 0.
Transcripts: `.runtime/single-deploy-live.{log,exit}` (first failure) and
`.runtime/single-deploy-retry.{log,exit}` (successful full rerun).

The successful installer warned that final obsolete-token cleanup over USB SSH
timed out. Subsequent read-only Wi-Fi SSH confirmed no `/root/.talkback_token`;
the local obsolete token is absent too. No further cleanup or service restart
was needed. Intermittent USB SSH reachability remains a qualified observation.

Actual browser verification passed:

- Clear live H.264 768x432 at 0/90 degrees; Talk start/stop with TB3 available.
- Seven-second recording `20261023T074118Z_6f5ed36f.mp4`: H.264 768x432,
  90-degree display matrix and three AAC tracks. Portrait playback, seeking to
  two seconds, native download, HTTP206 byte range and return to live passed.
- Recording and download: 2,415,286 bytes, matching SHA256
  `25e860f9f82b5495b8d2d642a847ec401bedcee9d1722b822a81e401e22f19f3`.
- Real Chromium continuity: 60.120 seconds, 1,201 additional decoded frames
  (~19.98fps), increasing video frames and audio bytes at every five-second
  sample, zero reported lost packets, audio unmuted/playing, no page errors.
- Independent three-second return decode: 24,000 samples, 18,519 nonzero,
  peak 1,756. This confirms microphone data, not intelligible audible speech.

Evidence: `.runtime/single-deploy-live-ui-result.json`,
`.runtime/single-deploy-live-{0,90,recording}.png` and
`.runtime/single-deploy-live-continuity.{mjs,json,png}`. Portrait screenshot
was visually inspected. Final Docker healthy, headset connected, Talk available,
rotation zero, recording idle and maintenance null. User audible acceptance for
this deployment is still pending; long hardware stability and latency untested.
