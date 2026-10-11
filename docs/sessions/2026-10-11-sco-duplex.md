# SCO full-duplex trial — 2026-10-11

## Request and branch

User asked to preserve the working branch, create a new branch, and persist
with SCO experiments. Created `experiment/sco-duplex` from clean `uplink-audio`
at `4e8aafb` (the recovery repairs were already committed). Prior Stage 1
worktrees were not deployed. Used pinned PuTTY access over USB; no credentials
or talkback token values appear here.

## Hardware and isolated trials

BlueALSA 4.1.1, BlueZ 5.68, EDIFIER X2 Plus, AIC SDIO controller (HCI vendor
RivieraWaves). HFP codec list contains CVSD only; mSBC is not compiled into this
daemon. Playback/capture are S16_LE, 8000 Hz, mono. eSCO was state1 at preflight.
Original controller SCO MTU255/count4; received SCO packets were120 bytes.

Existing microphone capture stayed open during local playback tests. Tone
was440Hz, initially peak1800, then4500 in PCM16 units; duration10 seconds.
Requested playback period20ms, buffer80ms; negotiated160/640 samples.

| Trial | Setting | Listener report / result |
|---|---|---|
| A | MTU255, quieter tone | No tone heard; aplay exit0 |
| B | MTU255, louder tone | No tone heard; aplay exit0 |
| C | Same plus HFP CIEV call/service/signal indicators | No tone heard; call indicators restored after test |
| D | MTU120, SCO link closed/reopened | Continuous tone, with existing capture open |
| E | MTU255 restored and link reopened | User first reported continuous with small drops |
| F | MTU120 restored and link reopened | User confirmed continuous in later bundled responses |
| G | Paced authenticated TB2 over USB,15 seconds | Continuous tone through actual receiver |
| H | Same feed over Wi-Fi | User: nearly the same as USB |

User later answered yes to a bundled E-silent/F-continuous question; this
conflicts with the earlier specific E report. Do not claim a decisive audible
255-vs120 A/B failure or that MTU alone caused the initial silence.

Trace B:629 TX packets of255 bytes, median gap18.78ms, max24.98ms,
160395 bytes over9.98s. Trace D:1333 TX packets of120 bytes, median7.48ms,
max17.84ms,159960 bytes over9.99s. Trace E again used255-byte TX packets.
These are host/controller packet timing, not acoustic latency measurements.

Wi-Fi TB2 trace:742 unique PCM frames out of750 sent, sequence0–749,
duration14.974s, arrival-gap median16.54ms / p95 47.08ms / max177.03ms;
12 gaps over80ms. Duplicated capture observations across interfaces were
deduplicated by session/sequence. Initial USB tcpdump missed the test due to
startup timing (0 captured); it cannot establish zero USB packet loss.

## Deployed implementation and real speech

Changed only camera connector and receiver:

- Connector opt-in `--sco-mtu 120` requires SCO playback and even size2–254.
  Inspects `hciconfig hci0`, retains packet count and changes MTU only when it
  differs. Default A2DP polling does not use this override. Does not reset a
  healthy connection; existing SCO sockets need explicit reopening.
- Receiver infers SCO with `--duplex`, or accepts explicit playback profile;
  rejects explicit A2DP/duplex. SCO uses raw PCM,20ms periods/80ms buffer.
- SCO playback uses20ms deadlines and fills missing packets with silence while
  a talk session remains active, preventing repeated short-buffer starvation.
  Stop/authentication/session retirement/idle timeout remain in place.
  Default A2DP player command and half-duplex pause remain unchanged.

First WHIP attempt returned409 during service transition. First successful
15-second WHIP tone connected and user confirmed playback plus audible return.
Receiver logged underruns during early Wi-Fi tests. ALSA's printed underrun
figures are diagnostic output, not verified acoustic dropout durations.
USB TB2 test added no underruns. After pacing deployment the first short cycle
logged one underrun; subsequent successful repeated cycles logged no new ones.
Intentional player termination prints Interrupted system call on release.

User tested browser speech and explicitly confirmed simultaneous operation:
"yes it does work simultaneously, but yes, the quality of maix to pc is worse."
This establishes audible duplex, with return quality still below talkback.
It does not establish lower latency or eliminate echo/dropouts.

Seven initial automated WHIP hold/release cycles connected with no PC status
error; cycle8 was rejected by the existing strict camera clock calibration.
Second run completed13 connected cycles, making20 successful cycles across
both runs. Failed attempt is retained in ignored logs. Clock guard was not
relaxed. Same capture PID3940 remained open throughout these cycles.

## Return-quality evidence

HCI RX status flags1/2 (possibly invalid/no data) coincide with zero payloads.
Trace B:614 status0,743 status1,45 status2. D:1220/46/117. E:0/353/1066.
A later10-second capture-only sample:617/635/63. These widely varying short
samples show impairment before PC RTP delivery; they do not isolate radio
interference, shared Wi-Fi/Bluetooth coexistence, firmware, or device behavior.

Six-second PC return samples during this work included58 exact-zero frames of
300. This is not an SNR score or proof of a specific cause. Earlier accepted
recovery samples were much better (13/298,2/300); conditions are not controlled.

Additional packet-size experiments:

- First120-byte local tone sample:736 status0 /645 status1 /9 status2.
  The60-byte stage exceeded the22-second outer test deadline. Cleanup restored
 120-byte MTU and capture, with no orphaned player/monitor.
- Retried with a35-second outer limit:60-byte tone completed in10.69s and
  had1266/10/2 RX statuses (0.94% flagged). Subsequent120-byte tone had
 841/401/145 (39.37% flagged). These are short, variable samples.
- Deployed60-byte route for an actual speech trial. A later12-second sample
  had937/372/278 statuses (40.96% flagged), and PC return319 exact-zero frames
  of599. User explicitly reported **both directions worse**. Restored120-byte
  route; do not adopt60 on the strength of its one clean trace.
- Same-link120-byte idle/silent-playback/idle comparison:871/32/160,
 458/665/28,691/321/19 RX status counts. Silent playback did not improve
  reception, so no persistent silent-player lifecycle was implemented.

Return radio/controller impairment remains unresolved. Narrowband CVSD also
limits fidelity, but packet flags show that bandwidth alone is not the entire
quality issue. Do not describe shorter MTU or buffering as a proven SNR or
physical latency improvement.

## Reconnect recovery and final acceptance

Disconnecting with capture open once timed out after25 seconds, leaving ACL
state5 and eSCO state8. A scoped manual hci0 reset, followed by restoring
MTU120, recovered audio. Closing capture before disconnect also recovered;
a manual connect encountered busy because the connector was already retrying.

Added opt-in `--recover-stuck-sco`: only the bound headset's SCO/eSCO state8
persisting30 seconds permits an hci0 reset. Unknown connection inventory or
any foreign device prevents resetting. Attempts have a60-second cooldown,
including failures; MTU is reapplied afterward. Default A2DP does not run this
guard. Regression tests cover these restrictions and failed resets.

The deployed guarded build recovered a normal live disconnect in27 seconds
without manual intervention. State8 did not recur in that trial, so the
automatic reset path has regression coverage but no live-trigger acceptance.

A final60-second WebRTC hold connected after a bounded retry of an initial
409 active-session response and ended without a PC status error. Camera
underrun messages still occurred, including printed values of6322.785,
42500.674,4850.739 and5161.989ms. These are ALSA diagnostics, not measured
acoustic gaps; this test does not establish uninterrupted long playback.

After restoring120-byte operation, the user accepted audible simultaneous
speech: "yes it is acceptable (hearable), but the quality from maix to pc still
bad, you can commit changes, before moving on". This checkpoint preserves that
accepted route; return quality and underruns remain unresolved.

## Validation, rollback and runtime

Python suite:101 tests, OK,2 opt-in integration skips. New coverage includes SCO
buffering/duplex, paced silence during packet gaps, invalid duplex/A2DP options,
MTU validation, preservation of packet count, no repeated MTU mutation, and
failure without route modification and scoped recovery safeguards. Camera
modules compiled.

`/maix01` still H.264 video-only; `/headsetmic` still PCMU,8000Hz mono.
PC operator had stopped before this session; `start_operator.ps1` restored
native TCP/video + UDP8004 asPID5440. No PC media code/configuration changed.
No recording was active. Camera video service was not restarted.

Final live camera processes: connectorPID2005 with SCO/MTU120/recovery options,
receiverPID829 with duplex/SCO, microphone senderPID3077 to192.168.1.4:8004,
and capturePID2093 with20ms periods/80ms buffer. No player remained after
release. Controller MTU120:4, eSCO and ACL state1 were verified. Final bounded
video probe decoded25 H.264 frames over two seconds. USB management access
timed out near the end; final inspection used working Wi-Fi SSH. The cause of
the USB management timeout is unknown.

Backups on camera:
- `/root/bluetooth_audio.py.before-sco-duplex-20261011`
- `/root/talkback_receiver.py.before-sco-duplex-20261011`
- `/root/.asoundrc.before-sco-duplex-20261011`

Boot `/etc/rc.local` stays A2DP/half-duplex. Added a separate uninstalled SCO
startup template. [Procedure and rollback](../sco-duplex.md) describe applying
MTU before capture and restoring the saved A2DP route. Keep repaired microphone
module and UDP8004 sender; do not restart video to change audio routes.

Raw scripts, RTP/PCM samples, btmon traces, tcpdump captures and test output
are ignored under `.runtime/sco-*`; camera traces are under `/tmp/sco-*`.
No numeric physical latency improvement claimed.
