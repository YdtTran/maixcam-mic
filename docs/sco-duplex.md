# SCO full-duplex trial

Branch `experiment/sco-duplex` starts from the accepted recovery commit
`4e8aafb` on `uplink-audio`. The live trial uses SCO/CVSD for both directions,
with explicit 20 ms playback periods / 80 ms buffers and a 120-byte SCO MTU
override. Playback uses raw PCM and feeds silence at 20 ms deadlines during
packet gaps in an active session, avoiding repeated buffer starvation.
TCP/video, independent PCMU return on UDP8004, and video-only
recordings keep their existing paths. A2DP/half-duplex remains the default.

The MaixCAM BlueALSA 4.1.1 build lists only CVSD for HFP; mSBC is absent.
The available PCM is S16_LE, 8000 Hz, mono. SCO permits simultaneous audio;
it does not provide A2DP's bandwidth or establish lower physical latency.
See the upstream [BlueALSA HFP/HSP guide](https://github.com/arkq/bluez-alsa/wiki/Using-BlueALSA-with-HFP-and-HSP-Devices).

## Apply a reversible trial

Release Talk. Inspect the single connector, receiver, and microphone processes
and save their exact command lines. Back up `/root/bluetooth_audio.py`,
`/root/talkback_receiver.py`, `/root/.asoundrc`, and `/etc/rc.local` before
uploading these branch modules. Do not restart video or the PC operator.

Stop the inspected connector and receiver only. Close capture using the
existing pause/ack handshake (allow at least three seconds for acknowledgment).
Wait until no `aplay` or `arecord` owns SCO and `hcitool con` has no SCO link.
Do not start a second capture owner.

```sh
hciconfig hci0 scomtu 120:4
nohup python3 /root/bluetooth_audio.py --fixed-mac 6C:16:29:7B:00:D4 --playback-profile sco --sco-mtu 120 --recover-stuck-sco </dev/null >>/root/bluetooth-audio-sco.log 2>&1 &
```

Verify `/root/.asoundrc` routes `bt_output` to `profile "sco"` at 8000 Hz,
mono, then start the receiver:

```sh
nohup python3 /root/talkback_receiver.py --duplex --playback-profile sco </dev/null >>/root/talkback-receiver-sco.log 2>&1 &
```

Remove the pause marker to reopen the existing capture. Verify its command
retains `--period-time 20000 --buffer-time 80000`, and that `hciconfig hci0`
reports `SCO MTU: 120:4`. Changing MTU alone does not update existing sockets:
the audio link must close and reopen. The connector checks/restores the opt-in
MTU after a controller reset, but does not automatically reset a healthy link.
Optional `--recover-stuck-sco` watches only `hci0`: a bound headset SCO link
remaining in state8 for30 seconds permits a scoped adapter reset, with a
60-second cooldown. A failed/unknown link inventory or any other device on the
adapter prevents reset. The override is reapplied before reconnect. This can
recover a controller that otherwise remains stuck, but audio is unavailable
during recovery. Prefer closing all SCO clients before a deliberate disconnect.

This workaround is specific to the inspected controller; it is not a generic
Bluetooth recommendation. It retains the controller's reported packet count.

The optional [SCO startup template](../maix/background_services.sco.rc.local)
sets MTU before capture. It is **not installed by the live trial**. Install it
only after speech, repeated holds/releases, return recovery and reboot testing
are acceptable. Save the actual original `/etc/rc.local`; the generic A2DP
template may differ from the deployed camera's RTP arguments.

## Acceptance

1. Wear earbuds and use PC headphones. Listen to a local continuous SCO tone
   while the one existing capture remains open.
2. Hold browser Talk while speaking in both directions. Verify microphone
   return stays audible during Talk, then after release. Compare speech
   clarity, clipping, gaps, and echo against the accepted A2DP setup.
3. Run 20 holds/releases and a long hold. Inspect `aplay` ownership, capture
   PID continuity, receiver errors, and return samples. Network status or a
   zero `aplay` exit does not establish audible success.
4. Test a scoped Bluetooth reconnect, then verify both speech directions and
   uninterrupted video. Inspect SCO state before using an adapter reset.
5. Keep a prolonged session and measure physical latency with a shared acoustic
   stimulus if numeric latency claims are needed.

## Roll back

Release Talk and stop the inspected SCO connector and receiver. Restore their
backed-up modules and managed ALSA config. Close capture through pause/ack,
wait for SCO to close, restore `hciconfig hci0 scomtu 255:4`, and restart the
saved connector/receiver commands without `--playback-profile sco`,
`--sco-mtu`, `--recover-stuck-sco`, or `--duplex`. Remove pause/ack markers to resume capture.
For this camera those commands were:

```sh
nohup python3 /root/bluetooth_audio.py --fixed-mac 6C:16:29:7B:00:D4 </dev/null >>/root/bluetooth-audio.log 2>&1 &
nohup python3 /root/talkback_receiver.py </dev/null >>/root/talkback-receiver.log 2>&1 &
```

Keep the repaired microphone module and its current UDP8004 sender command.
If startup was subsequently changed, restore the saved actual `/etc/rc.local`.
Do not restart video, MediaMTX or recording to change the Bluetooth route.

Detailed results: [SCO trial session](sessions/2026-10-11-sco-duplex.md).
