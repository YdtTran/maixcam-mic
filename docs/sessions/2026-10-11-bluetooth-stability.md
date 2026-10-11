# 2026-10-11 Bluetooth disconnect/reconnect investigation

User reported unstable Bluetooth and clarified actual disconnect/reconnect,
then instructed use of the USB IP for repairs. Keep accepted latency and media
settings. Windows key-only SSH failed on Wi-Fi and USB. The documented pinned
PuTTY login succeeded at USB 10.172.16.1; no credentials were changed. Earlier
notes about unavailable camera access referred only to the key-only attempts.

Device evidence: EDIFIER X2 Plus selected/fixed; BlueALSA 4.1.1, BlueZ 5.68.
One Bluetooth connector, one talkback receiver, one microphone sender and one
SCO arecord process. BlueALSA listed A2DP/SBC playback (48kHz/stereo), SCO/CVSD
playback and capture (8kHz/mono). Actual ALSA config retained A2DP output and
SCO input. Existing logs showed br-connection-unknown, br-connection-busy,
connect timeouts, and talkback PCM-not-found errors. These historical errors
confirm reconnect/profile failures but do not establish why the radio drops.

Read-only monitoring sampled connected=true and both stream paths available
for 15 samples. A 35-second btmon trace did not contain a disconnect event.
No numeric latency or audio intelligibility measurement was performed.

Confirmed code defects: each healthy poll unnecessarily called adapter power,
pairable and trust mutations; failed info queries were treated as an unpaired
device; unsuccessful reconnects always retried at five seconds. Added three
regressions, observed them fail, then fixed these behaviors. A healthy/trusted
connection now receives status-only Bluetooth queries; failed status queries
do not trigger pairing; reconnect delay backs off 5/10/20/30 seconds and
returns to five-second polling on success. Audio routing defaults remain intact.
This corrects reconnect handling, not a proven cause of every physical drop.

Validation: ten focused connector tests passed. Full Python suite: 77 tests,
75 passed, two opt-in integration skips. No frontend code changed.

Deployment: backed up /root/bluetooth_audio.py and /root/.asoundrc to matching
`.before-stability-20261011` files, uploaded/compiled new connector, verified
the exact old PID579 command, and restarted only that connector. New PID3846
uses the same fixed headset. BlueALSA PID625, microphone PID581/arecord3227,
talkback PID580 and camera video were not restarted. No boot script change
was needed: it already starts /root/bluetooth_audio.py. PC app remains TCP/video
with separate return on UDP8004, recordings video-only. Ten post-deployment
samples from 00:09:23 through 00:09:57 all reported connected=true and both
stream paths available. Real Chromium decoded H.264 and received PCMU with
the audio element playing; talkback status reported available. No fresh
reconnect error appeared in the short post-deployment connector log check.

Ignored local evidence: `.runtime/bluetooth-health.jsonl`,
`.runtime/bluetooth-after-stability.jsonl`. Camera btmon evidence remains
`/tmp/headset-stability.btsnoop` and `/tmp/headset-stability.txt`. Longer physical
stability trials and disconnect reason capture during a recurrence remain pending.
