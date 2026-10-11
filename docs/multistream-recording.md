# PC multistream recording

Implemented as an opt-in extension. The live TCP/video monitoring route,
MaixCAM firmware, Bluetooth transport, headset RTP receiver and talkback relay
are unchanged. The default recorder remains the existing `legacy` recorder.
Physical A/V synchronization and VLC acceptance have **not** been measured.

## Enable and roll back

After stopping the current recording and waiting for finalization, stop the
native operator with `./stop_operator.ps1`. Start the extension with:

```powershell
.\start_operator.ps1 -RecordingMode multistream
```

The helper rejects a running operator with a different recording mode instead
of replacing it. The direct equivalent, retaining the current media settings:

```powershell
python app.py --maix-ip 192.168.1.7 --rtsp-transport tcp --stream-mode video --return-audio-port 8004 --recording-mode multistream
```

For rollback, stop recording, wait for finalization, stop the operator and run
`./start_operator.ps1 -RecordingMode legacy`. No camera rollback is necessary.
`--recording-mode` is independent of `--stream-mode`; do not change live stream
mode to `combined` to enable this feature. No MediaMTX configuration change or
new Python dependency is required. FFmpeg must support `alimiter`'s `latency`
option; the tested build is FFmpeg 9.0.1 on Windows.

## Architecture and output

```text
/maix01    → FFmpeg H.264 copy → staged video.mkv ────────────┐
/headsetmic → retrying FFmpeg decoder → bounded PCM queue ─┐ │
/talkback   → retrying FFmpeg decoder → bounded PCM queue ─┤ │
                                                       │ │
                PC monotonic 20 ms coordinator          │ │
                → worker.pcm + operator.pcm + silence ←─┘ │
                                                         │
Stop → close inputs → offline FFmpeg AAC encoding/mux ←───┘
     → <id>.partial.mp4 → atomic rename to <id>.mp4
```

The MP4 has H.264 video copied without re-encoding, default mono AAC `Mixed
conversation`, mono AAC `Worker microphone`, and mono AAC `Operator microphone`.
All audio is 48 kHz, 96 kbit/s per track. Both `title` and `handler_name` are set;
only the mixed audio track has the default disposition. In VLC select tracks
through Audio → Audio Track. Browsers generally play only the default track.

An FFmpeg input pointed at an absent RTSP path exits at input opening. Optional
`-map 0:a?` does not make the input optional or add it dynamically later. An
isolated MediaMTX test confirms this behavior. Each audio reader therefore
retries independently every 500 ms after exit, including absent publishers,
process failures and the end of a talkback session. Its RTSP I/O timeout is two
seconds. New sessions open new decoders; no new input is added to video capture.

## Timestamp alignment and limits

Recording zero is a PC `time.monotonic()` sample. Audio files contain exactly
960 signed 16-bit mono samples per 20 ms tick. Each decoder converts to 48 kHz
PCM; the coordinator consumes at most one block per tick, supplies silence for
missing blocks and counts duration from total samples. Wait durations do not
accumulate into the recording clock. A scheduler stall fills missed ticks with
silence rather than playing old speech in a compressed burst.

Independent RTP origins are never compared. Audio is scheduled by **decoded PCM
arrival on the PC**, not its source RTP timestamp or capture time. The queue is
bounded to five 20 ms blocks (100 ms); overflow drops the oldest block, and data
older than 120 ms is discarded. A decoder reconnect clears the old queue and
joins the existing timeline at its new arrival time. No timestamp is reset in
the recording. Faster sources shed blocks; slower sources produce silence. This
bounds accumulated drift but can cause discontinuities; this first version does
not implement adaptive drift resampling or reconstruct audio lost in transport.

Video uses FFmpeg `-use_wallclock_as_timestamps 1 -copyts` and a fixed negative
`-output_ts_offset` equal to the PC wall-clock sample taken at recording zero.
Thus video packet reception times are mapped onto the same recording origin
without decoding video. Initial RTSP negotiation, probing and waiting for a
decodable keyframe remain an initial video offset, rather than moving audio to
the first video frame. This assumes the current low-delay H.264 source; B-frame
sources have not been validated. Bursty arrival and millisecond Matroska
timestamp quantization may produce FFmpeg timestamp corrections; inspect logs.
These options follow the official [FFmpeg timestamp documentation](https://ffmpeg.org/ffmpeg-all.html).

The monotonic/wall-clock bridge is checked every tick. A discrepancy greater
than 250 ms stops capture and finalizes with an error rather than rebasing
tracks. Smaller clock slews, PC scheduling, transport buffering, decoder
startup and source-side capture/playback delays remain timing uncertainties.
Audio probing is limited to 100 ms, but this is not a guarantee of startup time;
retry latency, ICE publication and codec buffering add delay. Audio preceding a
decoder's first output cannot be recovered. Decoded arrival timing and video
packet arrival timing are different points in their respective pipelines.
**Aligned file timestamps are not evidence of physical A/V synchronization.**

## Mixing, disk space and lifecycle

Both continuous audio files enter `amix` with equal weights and normalization:
each voice contributes half its amplitude. An `alimiter` with 0.95 limit,
automatic gain disabled and latency compensation protects the mix. Individual
tracks retain their original levels. A real encode/decode test checks correlated
full-scale sine inputs for mixed-track clipping. This does not repair clipping
already present in a source.
Filter behavior is documented in [FFmpeg's audio filter reference](https://ffmpeg.org/ffmpeg-filters.html#amix).

Temporary PCM costs 192,000 bytes/s total, approximately 691 MB/hour, plus staged
video. During finalization both staged media and the final MP4 occupy disk.
Successful capture/finalization removes staging media; diagnostic logs and the
manifest remain. Capture or finalization errors retain staging media. Monitor
free disk space for long recordings; disk exhaustion ends capture and recovery
may be incomplete. PCM is buffered by Python; an abrupt crash may lose its tail.

Stop is asynchronous: the API returns `recording: true, finalizing: true` and
the UI disables recording controls until completion. Capture stops first; AAC
encoding takes place offline. No `-shortest` truncates tracks when a publisher
disappears. Output is bounded by the stopped sample timeline. Video receives
`q`, then a bounded wait, then forced termination if necessary. Forced shutdown
is reported and staging retained. Video loss ends the recording and attempts
finalization automatically; audio loss supplies silence and continues video.
Application shutdown waits for finalization before stopping MediaMTX. Long
recordings may take minutes to finalize, and forced app/process termination
cannot guarantee recovery. A new recording is rejected until finalization ends.

The coordinator does not restart a failed **video capture** within a recording;
it finalizes that recording. Audio decoder restarts are supported continuously.
A PC application restart creates a new recording origin, never silently appends
to an interrupted recording. Interrupted captures require explicit recovery.

## Commands, diagnostics and recovery

Exact argument arrays are generated by `video_command`, `decoder_command` and
`mux_command` in `pc/multistream_recording.py`. Video capture uses RTSP/TCP for
the accepted configuration; both audio readers always use local RTSP/TCP.
The final mux reads only local files, splits each audio input into isolated and
mixed branches, and maps video plus the three AAC outputs. See the implementation
for the complete filter graph and stream metadata arguments.

`<id>.ffmpeg.log` records capture/finalize commands, FFmpeg warnings and a health
snapshot every five seconds. `<id>.capture/headsetmic.log` and `talkback.log`
record decoder attempts, connection times and errors. `<id>.json` records sample
duration, dropped blocks, silence/audio block counts, scheduler gaps and errors.
`/api/recordings/status` exposes mode, finalizing state, audio counters and errors.
The staging manifest preserves recording origins and media format for recovery.

For interrupted capture, leave the staging directory intact. From the repo root,
generate a recovered MP4 (use a different output name from the original):

```python
from pathlib import Path
import subprocess
from pc.multistream_recording import mux_command

stage = Path("recordings/<id>.capture")
worker, operator = stage / "worker.pcm", stage / "operator.pcm"
duration = min(worker.stat().st_size, operator.stat().st_size) // 1920 * .02
subprocess.run(mux_command(stage / "video.mkv", worker, operator,
                          stage.parent / "recovered.mp4", duration), check=True)
```

Recovery requires a readable video staging file and PCM files. This command
preserves the staged video offset and limits both audio streams to complete
common PCM blocks. A truncated Matroska tail may be recoverable with warnings;
an empty video file cannot produce a valid four-track MP4. Check with ffprobe
and VLC before deleting any staging media. Manually named recovery files are
not listed by the UI's recording-ID filter.

## Validation

```powershell
python -m unittest discover -s tests -v
$env:MULTISTREAM_INTEGRATION='1'
python -m unittest discover -s tests -p test_multistream_integration.py -v
Remove-Item Env:MULTISTREAM_INTEGRATION
cd frontend
npm test
```

Integration tests launch their own MediaMTX and publishers on isolated ports.
They cover absent inputs, late publication, silence during gaps, two operator
sessions and worker reconnects, all four streams, sample duration, monotonic
video timestamps, unchanged encoded H.264 slice bytes, complete decoding,
automatic finalization on video loss, and clipping protection. These tests do
not touch the production camera or running operator. Unit tests also cover
partial PCM reads, queue overflow, producer drift, scheduler stalls, wall-clock
steps, failed mux recovery and protection while finalizing. Browser tests cover
the finalizing state for both source and packaged interfaces.

Inspect a real result:

```powershell
ffprobe -v error -show_streams -show_format -of json recordings/<id>.mp4
ffmpeg -v error -i recordings/<id>.mp4 -map 0 -f null -
```

Hardware acceptance still requires VLC track selection and a physical flash/click
trial. Place a synchronized flash/click stimulus in camera view and near the
worker microphone; repeat near the beginning and end of a longer recording,
and after a headset reconnect. For operator audio, place the same stimulus near
the operator microphone while it is visible to the camera and Talk is active;
repeat across two Talk sessions. Extract the separate tracks and compare the
physical flash frame with the click waveform onset. Record signed audio-minus-
video offsets, frame/sample resolution, startup/reconnect conditions, duration,
number of trials and variability in a session log. Reject ambiguous stimuli.
Measure both tracks independently before evaluating the mixed track; do not
substitute RTP timestamps, file start times or browser buffering statistics.
