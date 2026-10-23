# Working earbud microphone volume — 2026-10-23

The user reported that setting volume to zero still allowed audio, then
explicitly clarified: MaixCAM earbud microphone was still audible on the laptop.
The existing `/bluetooth/volume` and UI slider target earbud **playback** only;
the preceding +50% capture gain had no adjustable UI. This was the proven
direction mismatch, rather than a failed microphone mixer write.

## Changes

Added separate **Earbud microphone volume** and **Apply microphone volume**
controls in the physical worker Actions card, reusing the existing volume
component. Existing playback control retains its purpose. Demo workers expose
neither control. The new `/api/bluetooth/capture-volume` proxies to camera
`/bluetooth/capture-volume`; both HTTP boundaries validate integer 0–100 and
reject extra/malformed fields just like playback.

The camera atomically saves `/root/.bluetooth_device.capture-volume`. The mic
sender rereads it alongside selection every 0.5 seconds. PCM scaling precedes
both RTP and RTSP encoding: 0 produces exact silence, 50 multiplies raw capture
by 0.75, and 100 retains the preceding 1.5 gain. Signed S16 saturation remains.
Missing state defaults to 100; invalid/unreadable state sends silence until
corrected. Normal service restarts preserve the file; the hard-fresh installer
resets it with the other camera settings. No mixer, Bluetooth binding, PC input
selection or old recording content is changed by this setting.

## Automated verification

Focused Python checks: 42 passed. Full `python -m unittest discover -s tests -q`:
225 tests ran, eight skipped, otherwise OK (92.6 seconds). `npm test` built the
frontend and passed all 52 source/compiled browser checks. `git diff --check`
passed. Coverage includes persisted zero, invalid saved state, live rereads,
nonzero input becoming silent at zero, both encoding paths, HTTP validation,
independence from playback, demo worker exclusion and unavailable endpoints.

The new reread test initially indexed its next-volume list before the final
KeyboardInterrupt; fixed this test-helper ordering and reran successfully.

## Deployment and live evidence

Under owner-bound maintenance, backed up/replaced camera
`bluetooth_control.py` and `headset_mic_stream.py`; restarted only the Bluetooth
connector and microphone sender with their previous arguments. The first
attempt checked HTTP readiness after only three seconds, received connection
refused and restored both previous modules/processes. Read-only follow-up
confirmed the old endpoint was working. Extended the runner to poll actual
readiness, recovered the same maintenance owner and deployed successfully.

Successful backup:
`/root/workercam-capture-volume-3a71806d0df94717b6f71363b06691df/`.
Connector PID 2772; microphone sender PID 2773. Talk receiver/BlueALSA were
preserved. Camera 172.20.10.7, return target 172.20.10.2:8004. No camera reboot,
network or firewall change. Safely stopped the idle PC with the module helper,
rebuilt/recreated Docker, verified health/Windows host UDP listeners and released
maintenance. Runner/log: `.runtime/deploy-capture-volume.ps1`,
`.runtime/capture-volume-deploy.log`.

Real Chromium UI changed 100→0→50→100 and verified camera API readback. At zero,
eight Web Audio measurements all had peak=0 and RMS=0 while video/audio packet
counters continued increasing with zero reported loss. At 50 and 100, received
mic signal was nonzero. Playback was never written by the verification. The
zero state reloaded after switching away from/back to the physical worker.
Screenshots visually show clear video and separate microphone/playback controls.
Artifacts: `.runtime/verify-capture-volume.mjs`,
`.runtime/capture-volume-live.json`, `.runtime/capture-volume-{0,50,100}.png`.

The initial recording sample contained nonzero worker audio. Logs show
additional volume POSTs from another browser during that trial, so that file
does not establish muted recording behavior. Retained it as
`20261023T080237Z_43d137c4.mp4`. Repeated the recording with explicit volume
readback throughout: all 32 observations were zero. Finalized
`20261023T080606Z_ea70f88c.mp4` decoded 340,992 samples per audio track; worker,
mixed and operator tracks all had peak=0. The controlled verifier exits on any
competing volume change and restores microphone level to 100. Its first ad hoc
invocation incorrectly sent `{}` to the bodyless recording-start API and was
rejected before recording; corrected to an empty POST. Script:
`.runtime/verify-muted-recording.py`.

Final microphone volume returned to 100; recording idle, rotation zero,
maintenance null, headset connected and Docker healthy. Playback remains under
the user's separate control. Audible user acceptance, prolonged endurance and
reboot persistence were not tested. High input at 100 can clip; amplification
also increases noise. Multiple browsers share the same camera setting, so
another operator can change the level after it is applied.
