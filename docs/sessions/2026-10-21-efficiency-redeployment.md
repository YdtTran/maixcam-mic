# Camera efficiency paired redeployment and live verification

Final result: both devices redeployed successfully after the repairs below.
Live video, audio, Talk, rotation and recording/playback passed short checks;
the user confirmed both audio directions audible. CPU idle targets were not
achieved, and recording decode emitted timestamp warnings. No archival performed.

The user approved redeployment of the whole pipeline after automated task 4.1
passed. Authorization includes both PC and MaixCAM deployment and live checks.

Ran the planned command:

```powershell
powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File scripts/deploy.ps1 -UsbInterfaceIndex 17 -UsbPeerIP 10.172.16.1 -Force
```

It exited 3 during read-only discovery: MaixCAM authenticated over USB but had
no active Wi-Fi IPv4 address. No installation, reboot, PC rebuild, configuration
update or rollback occurred. Raw output: ignored
`.runtime/efficiency-live-deployment.log`.

## Diagnosis and final observed state

- USB SSH works at 10.172.16.1 on interface 17. Camera `wlan0` is up but
  unassociated, with no IPv4 address or Wi-Fi route. Radio is not blocked.
- Existing wpa_supplicant and DHCP client are running. Saved network is
  `P526_5G`; it was absent from the camera scan. PC is on `HCMUT-MEETING`,
  which the camera can see. No passwords or wireless configuration were read
  into logs or changed.
- Requested reassociation with the existing saved network; command returned OK
  but no Wi-Fi address was available. Asked the user to connect the camera to
  the PC's reachable Wi-Fi using its screen before resuming.
- Existing PC container is restarting; logs show camera TCP connection timeout
  at the previous 192.168.1.7:8554 address. Operator HTTP is unavailable.
  No container restart was initiated by this attempt.

These were initial observations, superseded by the authorized recovery below.

## Network recovery and live startup repair

The user supplied the Wi-Fi password and explicitly requested SSH setup of
`HCMUT-MEETING`. Configured it without logging the password. Initial
`wpa_cli save_config` failed because updates were disabled; enabling
`update_config` allowed saving. On reboot, `/etc/init.d/S30wifi` restored the
old profile from `/boot`. Saved the new configuration to
`/boot/wpa_supplicant.conf` and retained private prior configuration backups under
`/root/`. Final reboot automatically rejoined the network at 10.127.15.230.
Laptop Wi-Fi is 10.127.9.237; USB endpoint/interface remained unchanged.

The existing PC was restarting with PID 0 between attempts, exit 1, HTTP refused,
and logs showing failure before recorder construction in `app.run`. Stopped
that failed container directly so the guarded deployment could proceed.

The first camera install exposed a real startup regression in
`/maixapp/tmp/last_run.log`: the launcher invokes `main.py auto_start`, which
the new argparse interface rejected. Added an optional positional argument
restricted to `auto_start` in `maix/rtsp_av.py`. Added a regression test which
failed before the fix and passed afterward. Camera suite: 15 tests, two skips.
Full Python rerun: 180 tests, eight skips, exit 0 (55.151 seconds); log in
`.runtime/efficiency-post-fix-python.log`.

That failed install timed out and attempted automatic rollback; rollback itself
reported `services.server.ports.[]: invalid ip address`. Exit 6; PC remained
stopped. Recovery snapshot `34097e03156e4525ab0db0ba6f192883` is retained.
This rollback defect is unresolved. A retry while USB was still rebooting
exited 2 without mutation; the next full forced deployment succeeded.

## Successful deployment and real workflows

The exact forced command above completed with exit 0. Camera rebooted into the
corrected native-bound application; Docker built/recreated and became healthy;
actual video and headset-return decoding, settings/process checks and TB3 APIs
passed. Final snapshot: `.runtime/deploy-backups/9749f479038e4b818718f247bb689536/`
and `/root/workercam-backup-9749f479038e4b818718f247bb689536`.
Raw successful deployment log: `.runtime/efficiency-live-deployment-final.log`.
Fixed earbuds, SCO, TCP/video and multistream configuration were preserved.

- Actual Chromium login and 768x432 camera picture worked. Both 0/90-degree
  rendering, portrait recording playback and return to live had visible image
  pixels; no page errors. Screenshots inspected, including the first recording.
- A 60.180-second browser observation decoded 22 to 1,211 video frames
  (1,189 additional frames, about 19.8 fps), increasing at each five-second
  sample. PCMU audio bytes increased 11,040 to 479,680. Both streams reported
  zero packets lost throughout. The first diagnostic attempt sampled before
  the first decoded video frame and failed; fixed the temporary observer to
  wait for video dimensions before measurement. This was a diagnostic startup
  wait issue; the subsequent complete observation passed.
- Real browser WHIP Talk started and stopped via TB3. Headset connected on
  eSCO with MTU 120:4. User confirmed: "Headset is on; both directions audible".
  A six-second independent return decode had 48,160 samples, mean -27.3 dB,
  peak -4.8 dB. These are levels, not intelligibility or latency measurements.
- Retained `20261021T010453Z_16555cc3.mp4` (6.58 seconds, 2,281,688 bytes).
  Then recorded with Talk active and retained
  `20261021T010711Z_60cf73cb.mp4` (7.12 seconds, 2,780,812 bytes). Both contain
  768x432 H.264 with a 90-degree display matrix and three AAC tracks.
  The second recording received both worker and operator audio; all three
  decoded audio tracks contain nonzero samples. Portrait playback and return
  to live passed. Browser fake microphone supplied operator test audio;
  human speech acceptance is the user's separate confirmation above.

## Performance and remaining limits

Camera has one video process and one each of the audio services. Video process
maps contain no NumPy/OpenCV; no camera FFmpeg process exists. Printk console
level is 4 and Wi-Fi power save is off. Video VSZ was about 99,552 KiB
(97.2 MiB); video process CPU 22–30% in final short samples, with 0% I/O wait.

The planned 55–65% idle CPU target did **not** pass: early concurrent deployment
samples showed 0–2%, Talk/load samples 0%, and final samples after automated
Talk stopped showed 23% and 17%. Syslog/kernel/Wi-Fi activity remained visible;
these observations do not isolate its cause or establish a controlled
before/after CPU comparison. Console printk filtering does not stop kernel log
collection. Do not claim the proposal's full CPU savings.

FFmpeg recording decode exited 0 but emitted repeated non-monotonic DTS warnings
from the null output muxer, including with passthrough frame timing. Browser
playback was clear. The warnings' cause and impact remain unproven; do not claim
a warning-free media validation or long-duration A/V synchronization result.

Final PC is healthy, headset connected, Talk available with no API error,
recording/finalization idle with no recording error, manager/effective rotation
0. Saved recordings and snapshots retained. No physical latency measurement,
long-duration stability claim, speculative CPU repair or rollback-format fix.
The prior intermittent camera freeze did not recur during this 60-second check;
its historical root cause is not established by this pass.

Further raw evidence is ignored under `.runtime/efficiency-live-*` (continuity,
UI, recording validation, duplex, return levels and top snapshots). Automated
tasks remain 6/6; performance acceptance remains qualified. No changes archived.
