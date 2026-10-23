# Remove earbud playback volume — 2026-10-23

User explicitly requested removing **Earbud playback volume**, leaving normal
PC→MaixCAM Talk delivery. The separate working microphone volume remains.

Removed the playback slider/button and its `/api/bluetooth/volume` proxy,
client action, camera `/bluetooth/volume` route and mixer method. Removed the
now-unused BluetoothControl playback-profile argument and its caller argument;
the actual audio connector/receiver profile selection is unchanged. Simplified
the shared UI to microphone-only and updated current usage documentation/tests.
No Talk transport, encoder, PCM volume, headset binding or recording change.

`python -m unittest tests.test_bluetooth_control tests.test_bluetooth_audio
tests.test_headset_return -q`: 52 passed. `npm test`: build/type-check and all
50 source/compiled browser checks passed. Tests cover retired GET/bodyless POST
404 at both HTTP servers, UI absence/no retired requests, retained microphone
zero/reload and existing Talk/connector behavior. `git diff --check` passed.
Full Python suite was not rerun for this removal.

Under existing owner-bound maintenance, backed up/installed
`bluetooth_control.py` and `bluetooth_audio.py`, restarting only the Bluetooth
connector with its previous arguments. New connector PID 3926; mic sender 2773,
arecord 2781, Talk receiver 614 and BlueALSA 627 preserved. Backup:
`/root/workercam-remove-playback-4306b50d627048caad5fee61dabde9f3/`.
Safe PC stop, Docker rebuild/recreation, health and Windows host UDP checks
passed; maintenance released. No camera reboot, headset reconnect, mixer write,
network/firewall change or fresh reinstall. Runner/log:
`.runtime/remove-playback-deploy.ps1`, `.runtime/remove-playback-deploy.log`.

Real Chromium login confirmed no playback slider/button and an enabled retained
microphone slider. Retired PC GET/POST endpoints and camera GET returned 404.
Fifteen-second real video/audio continuity passed at 768x432, with nonzero mic
samples and zero reported packet loss. Real Talk hold/release established
WebRTC/TB3 and returned available with no error. Its synthetic outgoing track
was disabled to avoid playing test tones; this proves signaling, not audible
speech. Inspected screenshot shows clear video and only microphone volume.
Artifacts: `.runtime/verify-remove-playback.mjs`,
`.runtime/remove-playback-live.{log,json,png}`.

Final Docker healthy, headset connected, microphone volume 100, physical SCO
playback/capture 100% and unmuted, recording idle, rotation zero and maintenance
null. No new recording/reboot/endurance or audible Talk acceptance trial.
