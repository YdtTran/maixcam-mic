# Earbud microphone capture gain — 2026-10-23

The user confirmed everything was working and requested approximately 50% more
volume from the MaixCAM earbud microphone. This request concerns capture,
independent of the existing Live Workers earbud playback slider.

## Change and checks

Live BlueALSA inspection found SCO capture already at 15/15 (100%, unmuted).
Playback was 14/15 (93%) and was preserved. Added fixed 1.5 amplitude gain
(about +3.5 dB) to captured S16LE frames before both direct RTP and explicit
RTSP encoding. `audioop.mul` uses saturation; the standard-library fallback
matches its rounding and signed 16-bit bounds. Silence remains silence. Live
listening and future worker recording tracks receive the increased signal;
existing recordings are untouched. No new dependency, setting or UI was added.

`python -m unittest tests.test_headset_return tests.test_headset_mic_stream
tests.test_udp_media -q`: 25 tests passed. Coverage includes positive/negative
gain, clipping bounds, silence, RTP capture payload and RTSP PCM output. The
expanded RTSP test initially inspected the last spawned process (now arecord);
corrected it to inspect the first FFmpeg call and reran successfully.
`git diff --check` passed.

## Scoped live deployment

Used existing `NetworkDeployment.psm1` maintenance and OpenSSH helpers, without
running the hard-fresh reinstall. Under owner-bound maintenance, backed up the
single camera module, parsed and checked the new gain on the camera, installed
it atomically and restarted only `/root/headset_mic_stream.py`, preserving its
arguments. Old sender PID 615 became 1675; new arecord PID 1678. Bluetooth
connector PID 613, Talk receiver PID 614 and BlueALSA PID 627 remained running.
Camera address 172.20.10.7; return target 172.20.10.2:8004. No PC rebuild,
camera reboot, network reconfiguration or headset reconnect was needed.

Backup: `/root/workercam-capture-gain-97c21369af6f4e8a924f24b854a7112c/`.
Installed module SHA256:
`bf10aac5e089a67f94896f4947395f58af34f57d9043fac1950e68186e6caff9`.
The updated source is used for subsequent fresh installs too.

Real Chromium login, unmuted listening and 15-second continuity passed:
768x432 video advanced from 23 to 322 decoded frames; PCMU audio bytes advanced
from 17,920 to 138,560; both reported zero packet loss and no page errors.
Browser audio meter measured nonzero signal after its initial empty sample
(approximately -65.5 to -69 dB RMS in the sampled environment). This is delivery
evidence, not a controlled speech loudness comparison. Inspected screenshot
shows clear live video, headset connected and microphone online. Artifacts:
`.runtime/capture-gain-live.{mjs,json,png}`; scoped runner:
`.runtime/raise-capture-gain.ps1`.

Final Docker healthy; camera reports headset connected and TB3; capture remains
100%, playback remains 93%; rotation zero, recording idle, maintenance null.
No new Talk/recording/reboot endurance trial or audible user acceptance was
performed. Amplification also increases background noise; loud input can clip.
