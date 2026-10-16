# Independent earbuds microphone return

The new path is SCO capture → PCM16/8 kHz/mono → G.711 mu-law RTP
(payload type 0, 160 samples/20 ms, 172-byte packets) → PC UDP 8004
(RTCP 8005) → independent FFmpeg codec-copy receiver → MediaMTX
`/headsetmic` via RTSP/TCP → separate browser WHEP audio element.
`/maix01` remains TCP video-only and the legacy recorder remains video-only.
The optional [multistream recorder](multistream-recording.md) consumes the
independent audio paths without changing live video.

The receiver is opt-in in `app.py` with `--return-audio-port 8004`.
`compose.yaml` enables independent return on UDP 8004; use `deploy_pc.ps1` for PC deployment.
Use video mode with this option. The older `--headset-rtp-port` option is
for the combined publisher and does not enable this independent service.
Do not run the RTSP camera `/headsetmic` publisher alongside this RTP receiver:
they would compete for the same MediaMTX path.

The browser derives `/headsetmic/whep` on the same origin as the configured
video WHEP URL. It starts muted. **Enable audio** unmutes the separate audio
element; microphone reconnect affects only that peer. Navigation/logout closes
both receivers and deletes their WHEP sessions. Connection status means network
connectivity, not proven speech: the camera sender generates silence when no
headset is selected, capture fails, or the legacy talkback pause is active.

## Verified here and pending on hardware

**Current SCO follow-up (2026-10-11):** The experimental branch now has audible
full duplex confirmed by the user, with return quality still below talkback.
It uses explicit SCO playback timing and a controller MTU workaround. See the
[SCO trial guide](sco-duplex.md) and [session evidence](sessions/2026-10-11-sco-duplex.md).
The historical deployment limitations below describe earlier sessions.

Direct PC deployment subsequently succeeded: see [the deployment log](sessions/2026-10-10-headset-deployment.md).
The native operator now runs TCP/video plus UDP8004 return from the existing
camera sender. Real Chromium decoded video and received PCMU with its audio
element playing. Received audio was very quiet; intelligible speech and SCO
duplex remain pending. Camera files could not be updated because SSH root
authentication still failed on the requested retry.

Verified with synthetic local media: actual PCMU RTP received and copied into
MediaMTX, Chromium WHEP video plus independent inbound audio, WHIP negotiation
and talkback UDP delivery, video decoding after stopping the RTP source, and
a finalized recording with only a video track. This is not an audible headset
test or a physical latency measurement. Unit tests cover missing RTP restart,
startup failure, capped retry delay, codec/SDP matching, and explicit duplex.
Browser tests cover microphone error/reconnect/muting and independent video.

SSH batch authentication to `root@192.168.1.7` failed. Installed BlueZ/BlueALSA
versions, active PCM devices, headset duplex, audible quality, physical video
latency, echo, audio delay/dropouts/drift and real Bluetooth recovery remain
unverified. The production stack was not restarted or reconfigured. A final
HTTP check on port 8000 was refused, with no MediaMTX/FFmpeg processes present;
the native operator is currently stopped despite the earlier session notes.

## 1. Inventory MaixCAM before changing services

Run on MaixCAM as root; save output, without displaying the talkback token:

```sh
uname -a
bluetoothctl --version
bluetoothd --version
bluealsa --version
bluealsa --help
ps -ef | grep -E 'bluealsa|bluetoothd|headset_mic_stream|talkback_receiver|bluetooth_audio|arecord|aplay'
MAC=$(cat /root/.bluetooth_device)
bluetoothctl info "$MAC"
arecord -L
aplay -L
cat /root/.asoundrc
command -v bluealsa-cli
bluealsa-cli list-pcms
```

If `bluealsa-cli` is absent, inspect D-Bus instead:

```sh
dbus-send --system --print-reply --dest=org.bluealsa /org/bluealsa org.freedesktop.DBus.ObjectManager.GetManagedObjects
```

Expect headset Handsfree/Headset UUIDs and a capture and playback SCO PCM;
UUIDs alone do not prove working capture. Use `bluealsa-cli info PCM_PATH`
on paths from `list-pcms` when supported, and inspect sample rate, channels,
codec, and mode. A2DP output plus SCO input in `.asoundrc` is the current
repository default. Its BlueALSA startup requests `a2dp-source`, `hfp-ag`,
`hsp-ag`; if a daemon already exists, that code does not change its profiles.
Check the actual daemon arguments and installed `--help` capabilities.

For typical headsets both directions must use SCO/HFP for simultaneous audio.
Do not switch the live profile solely on that expectation. See the upstream
[BlueALSA HFP/HSP guide](https://github.com/arkq/bluez-alsa/wiki/Using-BlueALSA-with-HFP-and-HSP-Devices)
and [profile coexistence discussion](https://github.com/Arkq/bluez-alsa/issues/394).

## 2. Capture locally without a second capture owner

From `ps`, identify the existing microphone sender PID. Save its exact command
line and startup configuration for restoration. Set `MIC_PID` to that numeric
PID, then stop only that sender (not video, Bluetooth connector or talkback).
If a service manager restarts it, stop that service instead. Verify no `arecord`
remains. Commands below use the existing selected MAC:

```sh
kill -TERM "$MIC_PID"
ps -ef | grep -E 'headset_mic_stream|arecord'
MAC=$(cat /root/.bluetooth_device)
arecord -D "bluealsa:DEV=$MAC,PROFILE=sco" -t wav -f S16_LE -r 8000 -c 1 -d 10 /tmp/earbuds-mic.wav 2>/tmp/earbuds-capture.log
cat /tmp/earbuds-capture.log
ffmpeg -hide_banner -i /tmp/earbuds-mic.wav -af volumedetect -f null -
```

Speak and tap the earbuds mic during capture. Expect a ~160 KB WAV, nonzero
levels and identifiable speech when copied to Windows and played. File size or
PCM availability alone is insufficient. All-zero audio/`mean_volume: -inf`
means silence; `PCM not found` suggests missing profile/PCM; `Device or resource
busy` suggests another owner; disconnect/timeouts suggest profile/SCO failure.
Do not fix these by launching additional capture processes.

Repeat the same capture command while holding the existing browser **Talk**
button and speaking in both directions. This is a diagnostic trial: existing
talkback uses A2DP and may conflict with SCO. Log failures and restore the saved
sender immediately afterward. Legacy microphone pause/ack may make talkback
refuse to start while that sender is stopped; such a refusal proves neither
duplex nor hardware failure.

With the sender still stopped and talkback released, test SCO duplex locally:

```sh
ffmpeg -v error -f lavfi -i 'sine=frequency=440:sample_rate=8000' -t 10 -ac 1 -c:a pcm_s16le /tmp/sco-tone.wav -y
aplay -D "bluealsa:DEV=$MAC,PROFILE=sco" /tmp/sco-tone.wav 2>/tmp/sco-playback.log &
PLAY_PID=$!
arecord -D "bluealsa:DEV=$MAC,PROFILE=sco" -t wav -f S16_LE -r 8000 -c 1 -d 10 /tmp/sco-duplex.wav 2>/tmp/sco-duplex.log
wait "$PLAY_PID"
cat /tmp/sco-playback.log /tmp/sco-duplex.log
ffmpeg -hide_banner -i /tmp/sco-duplex.wav -af volumedetect -f null -
```

Expect audible tone in earbuds AND recorded speech. Silence, a successful
`aplay` exit, or an available SCO PCM does not prove both directions worked.
Record the results before deciding whether to change talkback playback.

## 3. Deploy return audio and optionally verified duplex

From Windows, after authenticated SSH/SCP is available:

```powershell
scp maix/headset_mic_stream.py maix/bluetooth_audio.py maix/talkback_receiver.py root@192.168.1.7:/root/
```

On MaixCAM, restart the single saved microphone service with this command,
using the PC LAN IPv4 address in place of `192.168.1.4` if it changed:

```sh
nohup python3 /root/headset_mic_stream.py --target 192.168.1.4 --rtsp-transport udp --rtp-port 8004 </dev/null >>/root/headset-mic-stream.log 2>&1 &
tail -n 30 /root/headset-mic-stream.log
```

Update that service's existing persistent startup entry to the same arguments.
Keep only one sender. The camera RTP transport is independent of TCP video.
At first keep the existing A2DP talkback: microphone return is intentionally
silent during Talk because its pause/ack protection remains enabled.

Only after the local SCO duplex trial succeeds, stop the existing Bluetooth
connector and talkback receiver by their inspected PIDs/service names. Restart
those two services with these options, retaining the synchronized token file:

```sh
nohup python3 /root/bluetooth_audio.py --playback-profile sco </dev/null >>/root/bluetooth-audio.log 2>&1 &
nohup python3 /root/talkback_receiver.py --duplex </dev/null >>/root/talkback-receiver.log 2>&1 &
```

Update their existing persistent entries after validation. `--duplex` bypasses
the capture pause; it requires `bt_output` routed to SCO. Both options must be
used together. To roll back, stop those two processes and restart their saved
commands without these options; the connector restores A2DP output and talkback
restores capture pause. No camera video service should be stopped.

On Windows, stop recording in the UI, then:

```powershell
.\stop_docker_pc.ps1
.\deploy_pc.ps1 -Build
docker compose exec server cat .runtime/headset-return.ffmpeg.log
docker compose exec server ffprobe -v error -rtsp_transport tcp -show_streams rtsp://127.0.0.1:8554/headsetmic
docker compose exec server ffprobe -v error -rtsp_transport tcp -show_streams rtsp://127.0.0.1:8554/maix01
```

Expect `pcm_mulaw`, 8000 Hz, mono on `/headsetmic`, and H.264 only on `/maix01`.
Open `http://127.0.0.1:8000/operator_test.html`, sign in and click **Enable audio**.
Allow inbound UDP 8004/8005 from the camera through the Windows LAN firewall;
if needed, run this scoped rule once in an elevated PowerShell:

```powershell
New-NetFirewallRule -DisplayName 'MaixCAM headset RTP' -Direction Inbound -Action Allow -Protocol UDP -LocalPort 8004,8005 -RemoteAddress 192.168.1.7 -Profile Private
```

Container logs: `.runtime/headset-return.ffmpeg.log` and one previous attempt; capture
errors appear in `/root/headset-mic-stream.log`. Receiver publication loss after
a 15-second startup grace triggers retries of 2/4/8/16/30 seconds, capped at 30;
health checks run every 5 seconds. Healthy publication resets backoff. Closing
the operator stops this child too. A silent but alive sender is not restarted.
Docker can opt in with `RETURN_AUDIO_PORT=8004` and `STREAM_MODE=video`; the
known Windows Docker forwarding problem remains unresolved.

## 4. Hardware acceptance matrix

1. Video alone: start with `-ReturnAudioPort 0`, record at least 30 clear physical
   stopwatch samples using [the measurement guide](rtsp-transport.md).
2. Return alone: with operator running, decode `/headsetmic` independently:
   `ffmpeg -rtsp_transport tcp -i rtsp://127.0.0.1:8554/headsetmic -t 10 -c:a pcm_s16le .runtime/return-check.wav`.
   Listen for speech; compare a shared physical click to the received sound.
3. Video plus return: repeat stopwatch samples with the same desktop, camera,
   lighting and network, alternating enabled/disabled trials. Compare median,
   p95, dropouts and reconnects. Do not use connection setup time as latency.
4. Both audio directions: only with verified SCO duplex enabled, hold Talk while
   the worker speaks. Verify simultaneous speech and video; use PC headphones
   to reduce acoustic echo. Browser capture echo cancellation cannot guarantee
   worker-side cancellation. Listen for echo and packet loss artifacts.
5. Run for 10 minutes, sampling physical audio/video delay at start/middle/end;
   check accumulating delay rather than only startup. No latency target has been
   verified by the synthetic tests.
6. Stop only the microphone sender, then restart its saved command. Video must
   keep decoding while microphone status retries, and return must recover without
   restarting video. `bluetoothctl disconnect "$MAC"`, then
   `bluetoothctl connect "$MAC"`: expect capture errors/silence followed by
   speech recovery, with video uninterrupted. The fixed-headset connector may
   reconnect automatically, so record actual disconnected duration.
7. Record and inspect MP4 with `ffprobe -show_streams`: expect video only.

Automated checks from Windows repository root:

```powershell
python -m unittest discover -s tests -v
$env:HEADSET_INTEGRATION='1'
python -m unittest discover -s tests -p test_headset_integration.py -v
Remove-Item Env:HEADSET_INTEGRATION
Set-Location frontend
npm test
```

The integration fixture owns isolated ports and never restarts the live stack.

## Future synchronized recording

Add a separate recorder consuming `/maix01` and `/headsetmic`, copying H.264 and
encoding audio as AAC for MP4. Independent streams need a shared clock/RTCP
mapping or a physically measured alignment offset; simply adding two FFmpeg
inputs does not establish synchronization. Define microphone-loss behavior
(silence insertion, continuity, reconnect and bounded queues), validate flash/
click alignment and drift across long trials, and keep recorder failures
isolated from the live publishers. This implementation adds no return audio to
recordings.
