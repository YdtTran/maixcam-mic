# PC-to-Maix talkback repair — 2026-10-11

## User report and diagnosis

The user reported PC-to-Maix talkback unavailable after the operator startup
repair. PC status had `available=true` with an interruption error; native logs
showed successful browser WHIP publication and a TCP RTSP talkback reader.
Headset remained connected and one receiver listened on UDP9002. Tokens matched
without displaying their values. Historical camera logs contained PCM-not-found
errors; a new silent talkback test did not change that log or pause capture.

A timestamp exchange over an established SSH session measured camera time
2.16946 seconds ahead of Windows, with an 8.8ms exchange RTT. TB2 rejects packets
whose timestamp differs by more than 2,000ms. This explains the failure to accept
the PC's packets. NTP checked the camera and adjusted it by only -0.121 seconds;
Windows Time was stopped. Query/resync reported the stopped service, and starting
it failed for lack of service access. No Windows clock or service settings changed.

## Repairs

- Camera `bluetooth_control.py` exposes `/bluetooth/clock` behind existing token
  authentication. It avoids slow Bluetooth queries on this route.
- PC calibrates once per talk session, accounting for half the request RTT.
  A monotonic anchor produces camera-time timestamps for PCM and stop packets
  even if Windows later adjusts its wall clock. Calibration rejects invalid or
  slow responses. Older camera code returning 404 retains the previous requirement
  for synchronized system clocks. Authentication and packet-age limits are intact.
- Both native supervisor and standalone operator wire this calibration into the
  talkback relay.
- After clock calibration restored playback, a longer device test exposed a
  temporary full nonblocking playback pipe being treated as a failed player.
  Receiver now drops that frame rather than restarting audio and toggling capture.
  Its regression test failed before the fix, then passed.
- Normal session release clears the interruption status after workers finish.
  The browser closes ICE before posting stop, which previously could leave a
  stale decoder EOF error. Old-session stop requests do not clear current errors.
- A repeated silent device test still reported ALSA underruns. Isolated PC
  loopback capture identified a pacing defect: Windows rounded relative 20ms
  waits to about 31ms (measured mean 30.78ms), so only 379 frames arrived during
  a twelve-second run. Absolute sender deadlines now compensate for timer
  rounding without sending catch-up bursts after long stalls. The corresponding
  coarse-timer regression failed with 63 frames in two simulated seconds before
  the fix. A real repeated test delivered 570 frames during the same twelve-second
  window, including startup negotiation; no interpacket gaps exceeded 100ms.

## Deployment and validation

Backups on camera:

- `/root/bluetooth_control.py.before-talkback-clock-20261011`
- `/root/talkback_receiver.py.before-backpressure-20261011`

Uploaded and compiled both changed camera modules. Restarted only connector
PID3846 (now PID1260) and receiver PID580 (now PID1481). BlueALSA, video and the
microphone supervisor remained running. During NTP diagnosis, starting S49ntp
created duplicate time-sync PID1067; removed that newly created process and
restored its PID file to the original daemon PID538. Original time sync remains.
No boot script, headset profile or ALSA route changed.

Restarted the native operator for PC changes; final PID9128 uses TCP/video with
independent PCMU return on UDP8004. Docker operator remains stopped. Docker image
rebuilt with current PC code; a future Docker launch must recreate its container.

- Full Python suite: 89 tests, OK, two opt-in integration skips. Includes clock
  calibration, authentication, unchanged stale-packet rejection, stop timestamps,
  standalone startup, full-pipe handling, coarse timer pacing and normal-release
  status regressions.
- Real Chromium with fake silent microphone: H.264 decoded, selected ICE UDP,
  independent PCMU return received, WHIP talkback started and stopped successfully.
- Silent hardware test after receiver repair: WHIP stayed connected; camera
  acknowledged capture pause and used the same aplay PID1504 at samples 3, 6, 9
  and 12 seconds. Log size stayed 30,734 bytes during the hold, with no new
  playback failures. Release removed pause/ack and resumed arecord PID1561.
- Expected `aplay` interrupted-system-call log appeared on intentional player
  termination after release. It is distinct from the repaired full-pipe failure.
- Final device check after sender pacing fix: one aplay PID1937 at all four
  hold samples, log size constant at 31,154 bytes throughout the hold (no new
  underruns or playback errors), and capture resumed as arecord PID1996 on
  release. Talkback status returned available with error=null afterward.

Ignored evidence includes `.runtime/talkback-after-repair.log`,
`.runtime/talkback-final-check.log`, `.runtime/talkback-repair-all-tests.log`,
`.runtime/talkback-paced-check.log`, `.runtime/talkback-repair-browser.png`
and Docker build output.

## Limits

Tests used silent synthetic microphone input; intelligible audible speech at
the earbuds and physical latency still require user observation. Legacy A2DP
talkback pauses headset capture during the hold; SCO duplex was not enabled.
Video configuration and independent return architecture remain as accepted.
