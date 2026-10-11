# Audio recovery and capture cadence — 2026-10-11

## User report

Both audio directions failed while video still worked. After scoped recovery,
user confirmed both directions worked and PC-to-Maix talkback worked perfectly,
but Maix-to-PC return had substantial noise and jitter. Keep A2DP output,
half-duplex, TCP/video and video-only recording.

## Evidence and recovery

Initial Bluetooth info: EDIFIER X2 Plus connected=yes, no stale pause markers.
PC native app23848 retained TCP/video and UDP8004 return. MediaMTX15768 and
video FFmpeg23436 were not restarted. PC /headsetmic decoded RTP but contained
only silence: six-second sample mean/peak -91dB. Camera arecord restarted.
Direct isolated arecord exposed "Unable to install hw params" at 8kHz mono.

A single Bluetooth disconnect/reconnect and a scoped BlueALSA restart did not
restore capture. New BlueALSA log exposed "Couldn't establish SCO link:
Operation timed out". User power-cycled earbuds and removed competing device
connections; capture still timed out before the controller reset.

hcitool con showed eSCO handle384 state8 while ACL remained established.
hciconfig hci0 reset cleared that connection; existing connector reconnected.
Afterward eSCO state1 and nonzero returned sound: eight-second decoded sample
mean -32.0dB, peak -2.7dB. User confirmed audible return, then both directions.
This establishes recovery after reset, not the original trigger for the stuck
transport. No automatic reset/reconnect lifecycle logic was added.

## Minimal software repairs

Talkback live test logged "headset microphone did not pause for talkback".
Receiver had a two-second acknowledgment deadline; microphone stop_process
can spend two seconds waiting before killing a stuck arecord. New regression
with acknowledgment at2.1s failed before the fix. Receiver now allows three
seconds. A second regression checks bounded failure and marker cleanup.
Authentication, sequencing, jitter buffering and stale packet limits unchanged.

Uploaded current microphone module because installed older version suppressed
arecord errors. Retained original target192.168.1.4 and UDP8004 arguments.
Deployed receiver and microphone worker only; PC services stayed running.

After sound returned, six-second decoded return had 252 exactly zero PCM frames
of300 (84%), with a periodic pattern. Earlier negotiated ALSA capture period
was125ms; sender sends20ms and trims bursts to newest complete frame. This
combination explains regular synthetic silence. Requested arecord period20ms
and buffer80ms, without changing codecs, RTP, TB2 or playback settings.

Restarted only microphone worker for that setting. First PC probe during
publication reconnect returned404; subsequent probe succeeded. Six-second
decoded return then had13 exact-silence frames of298 (4.36%). This is a continuity
metric from short samples, not a physical latency measurement or acoustic
noise/SNR comparison. Occasional RTP loss/jitter warnings remain.
After the capture-period change, user reported "much smoother, but not as good
as the quality send from pc to maix". This confirms audible improvement with
residual quality limitations. A second six-second sample after a user Talk
cycle had2 exact-silence frames of300 (0.67%). No new BlueALSA error log growth;
capture reopened asPID3183 and eSCO remained state1. These are short checks,
not a long-term reliability guarantee or quantified noise measurement.

## Validation and runtime

Full Python suite after final changes:91 tests, OK, two opt-in integration skips.
Camera modules compiled. Receiver synthetic WHIP/TB2 check after pause fix held
one A2DP aplay PID2768 at3/6/9/12-second samples without new playback failures.
Release restored capture. Interrupted-system-call output on intentional player
termination is expected.

User confirmed real A2DP talkback worked perfectly before capture-period change.
A2DP configuration and receiver remain the same after that change.
ffprobe on /maix01 decoded19 H.264 video frames during a short bounded check;
no audio track. User also confirmed video works.

Current camera: BlueALSA2407, connector2414, receiver2696, microphone3077.
Active capture command includes --period-time20000 --buffer-time80000.
PC app23848, MediaMTX15768 remain unchanged. /etc/rc.local unchanged.
No SCO playback adoption, --duplex, persistent SCO or video/recording changes.

Backups:
- /root/talkback_receiver.py.before-pause-recovery-20261011
- /root/headset_mic_stream.py.before-audio-recovery-20261011
- /root/headset_mic_stream.py.before-period-recovery-20261011

To roll back periods only: release Talk, stop the inspected single microphone
worker, restore the before-period backup, restart the same microphone command
with target192.168.1.4 and --rtp-port8004. Do not restart video or BlueALSA.
For full module rollback use corresponding earlier backups and inspected worker
PIDs. Investigate transport state before concluding software rollback can repair
a stuck controller link.

Ignored diagnostic scripts in .runtime/; camera btmon traces under
/tmp/audio-recovery-btmon.txt, /tmp/audio-current-btmon.txt and
/tmp/capture-btmon.txt. /root/bluealsa-recovery.log exposes audio daemon errors.
Tokens were not displayed or copied into session notes. User requested committing
the deployed repairs and regression coverage on uplink-audio; the earlier
scenario branches are unchanged.
