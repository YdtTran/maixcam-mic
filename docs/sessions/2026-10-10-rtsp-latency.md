# Session log: RTSP transport and latency — 2026-10-10

Times below are local Asia/Saigon (UTC+7) where stated. This log records the
session's final state; [AGENTS.md](../../AGENTS.md) is the project's current-state
index, and [the measurement report](../rtsp-measurements.md) contains detailed
tables and limitations.

## Requests and constraints

The user asked to clarify the WebRTC data flow, assess a proposed RTSP/TCP
architecture, and implement configurable TCP/UDP transport with minimal changes.
Requirements included verifying camera TCP support, retaining WHEP/WHIP and
sequenced UDP talkback, independent video/audio/combined modes, comparable
transport diagnostics, and preserving the working UDP fallback.

The user provided a physical stopwatch filmed by MaixCAM with its original and
delayed image simultaneously visible on the PC. Their initial reading was
00:04:29.57 versus 00:04:19.34, or 10,230 ms. They reported similar delay in
video-only mode. The dashboard was open in Microsoft Edge. No synchronized
flash/click audio source was available. Neither UDP nor microphone processing
was to be assumed the cause.

## Implemented work

- Added `RTSP_TRANSPORT=tcp|udp` / `--rtsp-transport` and
  `STREAM_MODE=video|audio|combined` / `--stream-mode` to the PC supervisor.
  Updated relevant FFmpeg ingestion/publication, recorder and RTSP talkback
  decoder transport selection. Kept existing codec/buffer/queue parameters.
- MediaMTX accepts both RTSP transports. Camera TCP startup checks receive actual
  video packets before replacing the existing stack. A failed check aborts.
- Added matching microphone publisher transport and configurable RTSP port.
  Direct RTP audio remains UDP and is rejected in TCP audio/combined mode to
  avoid mislabeling mixed transport tests. Video-only ignores the audio input.
- Added isolated transport/mode diagnostics, browser WHEP statistics, FFmpeg
  timestamp processing metrics, desktop stopwatch capture/manual summaries,
  and arrival-versus-PTS drift tracing. No production browser interfaces changed.
- Updated configuration, tests and documentation. Existing unrelated working-tree
  edits were preserved; no commit was made during this session.

Relevant tools: `pc/check_camera_udp.py`, `pc/measure_transport.py`,
`pc/measure_video_latency.py`, `pc/read_stopwatch.ps1`, `pc/measure_timing.py`,
and `frontend/scripts/measure-webrtc.mjs`. Windows OCR was attempted but rejected
the stopwatch digits; saved simultaneous captures were read manually.

## Trials and recovery

Isolated hardware pilots ran in UDP/TCP/TCP/UDP order with matching microphone
RTSP publication, separate video/audio/combined modes, 15-second requested
durations and unchanged encoder defaults. The first three batches completed.
The final UDP video's camera source stalled; that partial result is excluded.
Final UDP audio completed; combined failed the actual camera packet check.

During recovery the camera reported native capture/resource errors and required
reboot. This does not establish a transport cause. The original auto-start camera
and direct RTP microphone publication were restored; the microphone transport
test used a separate temporary device file instead of overwriting production.

The integration fixture initially failed WebRTC media reception. Binding its
ICE UDP socket to all interfaces rather than loopback and advertising interfaces
resolved the fixture issue. Actual decoded media, not signaling alone, then
passed in TCP and UDP. This was a diagnostic fixture correction.

## Physical measurements and observations

Each physical run captured 20 simultaneous snapshots at five-second intervals.
Unclear digits, startup/reconnection and hand occlusion were excluded.

| Condition | Accepted | Median / p95 |
|---|---:|---:|
| Recovered UDP combined baseline | 13 | 1,710 / 1,980 ms |
| UDP video-only, approximately 18:35–18:37 | 12 | 175 / 200 ms |
| TCP video-only, approximately 18:38–18:40 | 7 | 230 / 240 ms |

The original 10.23 seconds was not reproduced. Combined baseline delay increased
approximately 5.26 ms/s; video-only endpoints were essentially stable. Sequential
30-second UDP timing traces showed −0.91 ms/s at camera output and +4.80 ms/s at
combined relay output. These trace slopes describe relative drift, not absolute
latency, and do not separate FFmpeg from MediaMTX.

The combined baseline preceded the PC image rebuild. Wi-Fi conditions were
ambient, not controlled or measured; short pilots and few clear TCP samples limit
comparisons. The final desktop layout changed, invalidating the original ROIs;
those captures were excluded. Edge playback was visible after restoration, but
an additional headless production receiver failed its received-media check and
produced no usable statistics. Physical audio latency and A/V sync remain unknown.

The user later clarified that both video and audio sometimes felt much faster
during scenario changes, specifically just before restoration at 18:38–18:40.
That interval matches TCP video-only. The video observation agrees with the
stopwatch pilot. Its publisher had no microphone track, so the perceived lower
audio delay cannot yet be attributed to that scenario.

## Final user decision and runtime state

After an initial restoration of normal UDP combined operation, the user asked
to return to the 18:38–18:40 scenario, keep it, and update the README. The final
configuration is **TCP video-only**, saved locally in ignored `.env`:

```dotenv
RTSP_TRANSPORT=tcp
STREAM_MODE=video
```

Applied with:

```powershell
$env:RTSP_TRANSPORT='tcp'
$env:STREAM_MODE='video'
docker compose -f compose.yaml -f compose.host.yaml up -d
```

Verified the running container's two configuration values and received 91 H.264
packets in a three-second explicit TCP probe of `/maix01`. Microphone monitoring
and recording audio are excluded. The existing camera microphone service remains
in place, unused by video-only FFmpeg. WHEP viewing, WHIP talkback and TB2 UDP
relay remain available. Do not automatically restore UDP combined: the user will
investigate better audio latency separately.

## Validation and evidence

- `python -m unittest discover -s tests -v`: 63 run, 62 passed, one opt-in
  integration test skipped in the default suite.
- Separate opt-in real-media integration passed in TCP and UDP: decoded WHEP
  H.264 over UDP ICE, WHIP audio, authenticated TB2 datagrams, and decoded MP4.
- Frontend `npm test`: build and 18 browser tests passed.
- Compose configuration validation, Docker build and `git diff --check` passed.
- Raw physical evidence and accepted CSVs: `.runtime/physical-udp-baseline`,
  `.runtime/physical-udp-video`, `.runtime/physical-tcp-video`, and summaries.
- Transport logs: `.runtime/transport-final-20261010-*` and
  `.runtime/transport-comparison-summary.json`; earlier failed attempts retained
  but excluded. Timing traces: `.runtime/timing-camera-udp` and
  `.runtime/timing-relay-udp`.

## Open work for a future audio investigation

### Subsequent user clarification (2026-10-10)

The user reports that current video latency and talkback from the PC are
acceptable. Earbuds → MaixCAM → PC audio remains unimplemented end to end.
Existing microphone code and previously observed service publication are not
evidence that this complete user-facing path is implemented. The remaining work
is to implement and validate that microphone path while preserving accepted
video and talkback operation. This clarification is a user status report, not a
new physical audio latency measurement. Only project notes were updated in this
follow-up; no code, services or runtime configuration were changed.

### Operator page access failure after startup (2026-10-10)

The user could not open the operator page and asked whether MaixCAM needs another
program. Their typed URL contained `operaator_test.html`; the correct filename
is `operator_test.html`. A separate Windows access failure was reproduced even
with the correct URL: curl reported connection refused on localhost TCP 8000
and 8889. The operator page returned HTTP 200 from inside the container; logs
showed actual TCP-interleaved camera packets and one H.264 track on `/maix01`.
MaixCAM was already providing video and did not need a duplicate process.

Docker Desktop's saved host-networking setting was enabled and the operator
container used host mode. A short-lived all-interface HTTP listener on port
18000 was also unreachable from Windows. Recreating only the operator container
with `docker compose -f compose.yaml -f compose.host.yaml up -d --force-recreate
server` did not resolve access: the internal HTTP check still passed and the
Windows check still failed. Docker Desktop host forwarding is suspected; the
precise cause is not established. No listener binding or media mode was changed.
ThingsBoard and PostgreSQL were also running in Docker, so a Desktop restart
was proposed for user approval before interrupting those unrelated services.

The user authorized the restart. `docker desktop restart` completed and
`start_docker.ps1` reapplied the VM buffer limits. Windows still could not reach
8000/8889 after restart and a further operator-only recreation. ThingsBoard and
PostgreSQL did not automatically return, so `docker start tb-postgres` and
`docker start thingsboard` restored both; PostgreSQL reported healthy.

At approximately 19:19, the operator container was stopped and the supported
native Windows stack was started hidden with explicit
`python -u app.py --maix-ip 192.168.1.7 --rtsp-transport tcp --stream-mode video`.
Its process PID and stdout/stderr are saved under `.runtime/operator-native.*`.
Windows curl then returned HTTP 200 for `/operator_test.html`; the talkback API
reported `available: true`, WebRTC transport and no error. Logs verified camera
TCP packets and one published H.264 track on `/maix01`. No camera processes,
tokens, `.env`, or media code were changed. Native Windows is the current
operator runtime; stop it before restarting the Docker operator. Browser video
and audible talkback have not been physically retested after this workaround.
Docker Desktop host forwarding remains unresolved; restart alone did not fix it.

The user then requested associated documentation updates. README, the Docker
run guide, transport guide, frontend README, measurement report, UDP deployment
history and AGENTS.md now identify the native TCP/video workaround, correct
operator URL, startup requirements, mutually exclusive PC stacks and unresolved
Docker localhost access. Earlier microphone diagnostics are distinguished from
the user's pending earbuds audio feature. Documentation checks covered local
links, the changed instructions and `git diff --check`; no code or services were
changed during this documentation update.

### Windows startup scripts updated (2026-10-10)

The user requested running-script fixes. Added `start_operator.ps1` for the
working native route: safely reads only camera/transport/mode settings from
`.env`, defaults to TCP/video, checks prerequisites, optionally rebuilds the
frontend, stops only the project's Docker operator when needed, starts hidden
with PID/log files, and requires Windows HTTP 200 before reporting success.
It reuses an existing matching operator and works with an unavailable Docker
engine. Audio/combined experiments require explicit direct `app.py` use.

Added `stop_operator.ps1`, which refuses to interrupt an active recording and
uses the existing supervisor process matching to stop native project services.
Fixed that matcher to recognize video-only FFmpeg publishers (which lack the
Opus option); a regression test excludes recording and unrelated camera jobs.
`start_docker.ps1` now rejects simultaneous native operation and checks actual
Windows HTTP access after Compose startup. A failed access check points to the
native helper rather than printing a successful operator URL. This does not
resolve the underlying Docker host-forwarding issue.

Validation: all three PowerShell scripts parsed; real stop/start and repeated
startup passed, Windows HTTP returned 200, `/maix01` published H.264, and the
talkback API reported available. The Docker/native conflict guard and simulated
unavailable-Docker native startup passed. Mocked PowerShell regression checks
cover Docker HTTP success/failure and recording shutdown protection. The first
recording test needed an explicit success output after its expected caught error
to avoid PowerShell returning exit code 1; the corrected test passed.
`python -m unittest discover -s tests -q`: 67 run, 66 passed, one opt-in media
integration skipped. Script documentation and `git diff --check` were updated/
checked. Native TCP/video is left running through the new helper, with the
operator container stopped; ThingsBoard/PostgreSQL and camera services were not
restarted during these script tests. No physical latency or audible talkback
remeasurement was performed.

Keep current video operation stable. Identify the actual audio heard during the
fast interval before drawing conclusions. Once authorized, compare video-only
and combined modes with the same transport, measuring immediately after restart
and over longer intervals. Check input timestamp alignment, buffering and
interleaving; compare direct camera, relay RTSP and Edge with consistent physical
timer/player settings. Arrange a synchronized flash/click source before claiming
audio end-to-end or physical A/V sync results. Target at least 20 clear physical
samples per condition and reverse trial order. No major redesign or buffer tuning
has been justified by the current evidence.
