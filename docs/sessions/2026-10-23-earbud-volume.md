# MaixCAM earbud playback volume — 2026-10-23

The user requested louder MaixCAM earbuds or a feature to adjust their volume,
then clarified that the preceding microphone issue was already working. No
additional PC microphone-selection change was made in this task.

## Initial finding and implementation

Live BlueALSA mixer inspection showed both A2DP and SCO playback already at
100%, with SCO capture also unmuted at 100%. Increasing the existing hardware
mixer beyond its maximum is unavailable; implemented the requested volume
adjustment feature instead of adding software amplification.

- Settings → MaixCAM Earbuds now provides **Earbud playback volume**, 0–100%,
  and **Apply earbud volume**. Opening Settings reads the actual camera level;
  applying reports hardware readback, including quantized levels. Unavailable
  mixers show an error and disable the control. Changing selection clears old
  volume state before querying the new device.
- GET/POST `/api/bluetooth/volume` proxies through the existing camera client to
  `/bluetooth/volume`. Both HTTP boundaries validate bounded integer requests,
  rejecting booleans, extra fields, nulls and malformed bodies. Existing PC
  same-origin control checks remain in effect.
- Camera `BluetoothControl.volume` uses the selected, validated MAC and
  `amixer -D bluealsa:DEV=<MAC>` with the configured SCO/A2DP control. Updates
  explicitly target **playback** and unmute playback. Capture gain is untouched.
- Existing binding, Bluetooth profile, runtime defaults and the working Talk
  microphone selection are retained. No extra dependency or volume configuration
  file was added. Hardware volume/firmware may change across reconnect/reboot;
  no new persistence guarantee is made. Reopen Settings to read its current level.

## Automated checks

`python -m unittest tests.test_bluetooth_control tests.test_bluetooth_audio -v`:
36 passed. Checks cover device-scoped playback commands, ignoring capture levels,
actual rounded readback, both profiles, failed mixer reads, malformed/out-of-range
HTTP bodies through real local PC/camera test servers, and existing Bluetooth
lifecycle behavior.

`npm test`: type-check/build and all 46 source/compiled browser checks passed.
After a final state-reset refinement, rebuilt and reran the four affected
source/compiled volume cases; all passed. UI checks cover applying/reloading a
value without changing the headset binding and disabling unavailable mixers.
`git diff --check` passed.

An initial temporary deployment-runner generation command had a nested
PowerShell here-string parse error before execution; the runner was rewritten
and syntax-checked before it was launched. No runtime mutation occurred from
that rejected command.

## Deployment and actual verification

The camera USB SSH address timed out during a preflight read; Wi-Fi SSH at
192.168.1.7 succeeded using the already verified USB host-key alias. This update
required no Wi-Fi configuration change or camera reboot, so scoped deployment
used that verified Wi-Fi connection.

Under elevated PowerShell and owner-bound project maintenance, backed up
`bluetooth_control.py` and `bluetooth_audio.py`, validated source syntax,
installed both and restarted only the exact camera Bluetooth connector, reusing
its previous arguments. New connector PID 1161; camera control volume endpoint
returned 100. The BlueALSA daemon, microphone sender, Talk receiver and native
video launcher were not restarted. Backup:
`/root/workercam-volume-247b9ada24c5459c8aff97b9586d8a8a/previous`.

Rebuilt/recreated the PC with `deploy_pc.ps1 -Build -Recreate` under the same
maintenance owner. Exit 0, Docker healthy, Windows HTTP and host UDP listeners
passed; maintenance released. Raw transcript:
`.runtime/earbud-volume-deploy.log`.

A real browser opened Settings, read 100%, requested 50% and received 53% from
the hardware's 16 SCO levels. The slider displayed 53%; leaving and reopening
Settings read 53% again. Applying 100% returned and displayed 100%; the original
100% level was also restored in the helper's finally block. Screenshots were
captured and the final UI inspected:
`.runtime/earbud-volume-{53,100}.png`; results:
`.runtime/earbud-volume-ui.json`.

Final physical mixer: playback 15/15 (100%, unmuted), capture 15/15 (100%,
unmuted). Native video PID 292, Talk receiver PID 614 and microphone sender
PID 615 were preserved. `/headsetmic` decoded after PC rebuild. Final API
showed rotation 0, recording idle, no metadata warnings and maintenance null.

No claim of increased loudness above the original level: it was already at
hardware maximum. No new acoustic comparison, prolonged stability, reboot
persistence or software gain/clipping trial was performed.
