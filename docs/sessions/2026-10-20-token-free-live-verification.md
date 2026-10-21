# Token-free live redeployment and verification — 2026-10-20

## Authorization and completion criterion

After defining successful redeployment and a working real system as the
completion criterion, the user requested: "Verify it". This authorized the
paired deployment and live workflow checks. Automated tests remain supporting
evidence; they do not override the live failures below.

## Deployment and recovery

- Read-only preflight found the camera at Wi-Fi 192.168.1.7 / USB 10.172.16.1,
  and PC Wi-Fi 192.168.1.4. Updated the ignored `.env` through discovery; fixed
  earbuds binding, TCP/video, SCO and multistream settings were preserved.
- The secondary USB endpoint reported a changed SSH host key. No trust data
  was changed; the verified primary USB endpoint/interface 17 was selected.
- The running old container used bind mounts from another checkout. Its
  recordings directory was empty; this checkout's 67 existing files were
  retained. The old token remained readable inside Docker although its original
  host token path was unavailable. Recovery capture now falls back to `docker cp`
  for retained token/recordings binds when original host paths disappear.
  Eighteen focused mock deployment/recovery checks passed after implementation,
  including retained-container material; this was not treated as live acceptance.
- Ran `powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File
  scripts/deploy.ps1 -UsbInterfaceIndex 17 -UsbPeerIP 10.172.16.1`.
  Captured the old image/configuration and private matching legacy token in
  `.runtime/deploy-backups/881497a78479412fbd52fddddb4b1147/` and camera backup
  `/root/workercam-backup-881497a78479412fbd52fddddb4b1147`.
  Recovery metadata reported legacy recovery available, without displaying secrets.
- Old PC stopped while idle, camera installed/rebooted, PC image built/recreated
  healthy. Both running sides and installed protocol payload verified TB3.
  The wrapper completed its actual video/return checks and removed obsolete active
  PC/camera token files, retaining recovery copies. A later exact rerun reported
  unchanged/verified with no install, reboot or image build.
- Headset was initially off/disconnected; the user turned it on and it reconnected.
  Follow-up media checks exposed missing return despite the wrapper's short pass.
  Scoped microphone pause/ack/resume restored observed camera UDP8004 output;
  container capture still saw none and Windows had no UDP8004 listener (8005
  existed). Recording-safe PC stop/start did not suffice. Recreating only this
  project's PC container restored both mappings and browser microphone return.
  No firewall rules, pairing data, video transport or audio architecture changed.
  Firewall inspection was denied; no privileged workaround was used.

## Real workflows that passed

- Actual Chromium admin login, clear physical 768x432 live video over UDP WebRTC.
- Real G.711 headset-return WebRTC audio received and a 15-second FFmpeg return
  decode completed after forwarding recovery.
- Real WHIP Talk session with TB3 calibration and clean stop. The user separately
  confirmed manually hearing PC speech through the headset when pressing Talk.
  This is audible PC-to-headset acceptance; audible return intelligibility was
  not separately confirmed.
- Live 0/90-degree picture/canvas pixels were nonblack, rotation locked while
  recording, and the original 0-degree selection was restored afterward.
- UI created `20261020T151235Z_0f13d2dc.mp4`; 837274 bytes, 6.6 seconds, copied
  768x432 H.264 with 90-degree rotation plus three AAC tracks. FFmpeg decoded it;
  actual portrait canvas playback and return to live displayed clear pixels.
  No browser page errors were observed during that workflow. Recording retained.

## Live failure that prevents completion

Short deployment/media/UI passes did not establish continuity. Follow-up logs
showed repeated PC FFmpeg video publisher loss/reconnection and unavailable
`maix01`. A 30-second real-browser check failed: decoded frames progressed from
1 to 10 to 16 across ten seconds, then stopped increasing at the next sample.
A scoped video-only SIGINT/replacement stopped the original camera process and
started exactly one replacement; its log then reported `camera read timeout`
and `RuntimeError: : Value is NULL: camera read failed`, and it exited. The
next browser could not obtain video within 30 seconds. The PC watchdog's
"Immediate exit requested" publisher errors do not by themselves identify the
original cause. No causal link to token removal is established; camera/video
source was unchanged by that change.

A normal camera reboot was requested while recording/finalization were idle to
restore the supported launcher/driver startup path, keeping the PC/UDP mappings
running. Final post-reboot observations are recorded below. No speculative
video-code rewrite, transport switch or Bluetooth re-pairing was performed.

## Final state

Normal boot restored video and headset connectivity. Final Chromium observation
passed 30 seconds of continuous video: decoded frames at five-second intervals
were 1, 64, 123, 181, 248, 305, 370 (about 12 fps). Final independent headset
return decoding passed, both Windows UDP8004/8005 mappings were present, and
TB3 Talk was available without error. The operator was idle, not finalizing,
rotation 0; the 6.6-second verification recording was retained. Active token
files were absent on PC and camera, with private recovery copies retained.

The current run works after deployment and recovery. Overall acceptance is
still qualified by the observed intermittent video freezes/read failure:
normal reboot restored service but did not establish or repair its root cause.
Do not treat the earlier short wrapper/test passes as proof of reliability.
No physical latency or long-duration stability claim.
Raw logs/screenshots are ignored under `.runtime/token-live-*` and
`.runtime/token-camera-read-failure.log`; private snapshots stay ignored.
