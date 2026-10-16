# SCO startup MTU ordering repair — 2026-10-11

User requested a root-cause fix after a clean headset reconnect restored silent
PC-to-headset SCO talkback. Used the fix-code workflow, preserving unrelated
deployment-cleanup edits, PC Docker, TCP video, UDP8004 return and recording mode.

## Reproduced startup defect

A temporary boot probe sampled controller status, link inventory and process
ownership. Camera uptime in seconds from the original startup:

| Uptime | Controller | MTU | Capture / eSCO |
| --- | --- | --- | --- |
| 26.98 | down | 120:4 | neither |
| 33.60 | down | 120:4 | capture attempted |
| 38.52 | up | 255:4 | neither |
| 40.55 | up | 255:4 | capture opened |
| 41.28 | up | 255:4 | eSCO connected |
| 47.18 | up | 120:4 | existing capture/eSCO still open |

The boot template applied MTU before controller initialization and launched
capture concurrently with the connector. Power-up restored the hardware's
255-byte MTU; capture created a link before the connector's later override.
An existing SCO socket retains its negotiated size, so the eventual hciconfig
120:4 status was insufficient to prove that the active socket used that size.
This is a confirmed startup-order defect. Interrupted-system-call messages on
intentional Talk release alone do not prove the cause of silence.

## Repair

- Connector prepares the controller before starting BlueALSA: inspect power,
  power up if needed, reread the reset MTU, apply the override while retaining
  packet count, then verify both power and size.
- Explicit `--prepare-sco` performs one preparation attempt and route setup,
  then exits without starting services or the control endpoint.
- SCO boot retries synchronous preparation before launching the connector,
  duplex receiver or microphone sender. Preparation failure keeps clients from
  opening sockets against the wrong MTU. A2DP startup keeps its existing path.
- Regression tests simulate power-up resetting MTU, failed power-up, ineffective
  MTU changes and preparation CLI success/failure. A POSIX shell test executes
  the real template with stub services: failed preparation retries and none of
  the services starts prematurely.

## Deployment and validation

Camera files backed up as
`/root/bluetooth_audio.py.before-mtu-order-20261011` and
`/etc/rc.local.before-mtu-order-20261011`; the original uninstrumented startup
also remains at `/root/rc.local.before-sco-rootcause`. Updated connector and
startup installed with Python parse and shell syntax checks.

Fixed boot trace: controller down at MTU255 at uptime22.10; up at MTU120 at
26.08; capture first observed at51.80 and connected eSCO at52.55, both with
MTU120. No capture/eSCO was observed at255 during that boot. A 20-second
synthetic WHIP test connected with API error null, and **the user confirmed a
steady audible tone without a manual reconnect after reboot**.

Initial full Python suite:120 tests, four skipped. After the final verification
guard and shell test, final checks are recorded below. POSIX boot shell test
passed in the existing Docker container against the current source template;
the test uses temporary files and stub processes, not live audio services.

The temporary boot probe was removed from production startup; raw before/after
traces remain in ignored `.runtime/sco-boot-before.jsonl` and
`.runtime/sco-boot-after.jsonl`. Final production files installed and a second
clean reboot requested. No PC rebuild, branch switch or recording-mode change.
Long-term controller/radio quality and physical latency remain outside this
startup-order validation.

Final production reboot: connector PID615, duplex receiver PID616, microphone
sender PID617 and one SCO capture PID645. Controller up, connected eSCO state1,
MTU120:4. A further10-second WHIP tone connected with error null; SCO TX counters
rose from0 to2359 packets by the final snapshot. Capture PID645 remained stable.
This last test was automated; audible acceptance is the user's earlier explicit
confirmation on the first fixed reboot. PC container remained healthy and
Bluetooth status connected. Production module/template hashes match the current
source after newline normalization. Final full suite:121 tests, five skips
(four opt-in media/hardware tests plus POSIX shell on Windows); the POSIX shell
test separately passed in Docker. Scoped diff whitespace check passed.
