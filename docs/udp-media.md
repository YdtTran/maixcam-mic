# UDP media prototype

The validation below records the original UDP prototype. Configurable RTSP
TCP/UDP support was added afterward; UDP remains the default and MediaMTX now
accepts both. See [transport configuration](rtsp-transport.md) and
[the comparison measurements](rtsp-measurements.md) for current behavior.

**Latest status (2026-10-10, approximately 19:19):** The operator runs natively
on Windows with explicit TCP/video flags. The Docker operator container is
stopped because Windows could not reach localhost 8000/8889 even after Desktop
restart and container recreation, despite internal HTTP 200. The native route
passed Windows HTTP 200, camera TCP packet reception, H.264 publication and
talkback API availability; browser playback and audible talkback were not
physically retested. ThingsBoard and PostgreSQL were restored after restart.
The user reports acceptable video and PC talkback latency; earbuds → MaixCAM →
PC audio remains unimplemented end to end. Earlier microphone checks below are
historical diagnostics, not evidence of feature completion. Use the
[current README startup instructions](../README.md#run-the-configured-stack)
and [session log](sessions/2026-10-10-rtsp-latency.md); current native PID/logs
are in `.runtime/operator-native.*`.

## Protocol map

| Path | Codec / format | Media transport | Signaling and ports |
|---|---|---|---|
| MaixCAM native `/live` to PC FFmpeg | Hardware H.264, copied | RTP/RTCP over UDP only | RTSP/TCP 8554 on camera; negotiated RTP/RTCP ports on both ends |
| Earbuds to MaixCAM | SCO PCM16 mono 8 kHz | Local Bluetooth HFP/SCO, BlueALSA | Existing Bluetooth service, unchanged |
| MaixCAM `/headsetmic` publication to PC MediaMTX | G.711 mu-law mono 8 kHz | RTP/RTCP over UDP only | RTSP/TCP 8554; PC UDP 8002/8003 |
| PC combined `/maix01` publication | H.264 copy + Opus mono 48 kHz, 20ms | RTP/RTCP over loopback UDP | RTSP/TCP 8554; UDP 8002/8003 |
| MediaMTX to admin interface | H.264 + Opus | WebRTC DTLS-SRTP/UDP | WHEP HTTP 8889; ICE UDP 8189; browser ephemeral UDP |
| Admin microphone to MediaMTX `/talkback` | Browser-negotiated WebRTC audio (normally Opus) | WebRTC DTLS-SRTP/UDP | Same-origin `/api/talkback/offer` proxies WHIP SDP to HTTP 8889; ICE UDP 8189 |
| MediaMTX `/talkback` to PC decoder | Negotiated audio, decoded to PCM16 mono 8 kHz | RTP/RTCP over loopback UDP | RTSP/TCP 8554; negotiated reader ports |
| PC to MaixCAM talkback receiver | PCM16 mono 8 kHz, 160 samples / 20ms | HMAC-authenticated custom TB2 UDP | Camera UDP 9002; PC ephemeral UDP |
| MaixCAM to earbuds speaker | PCM16 mono 8 kHz via ALSA | Local Bluetooth A2DP | Existing half-duplex profile switching |
| PC recorder | H.264 copy + AAC in MP4 | Loopback RTP/RTCP UDP, local file | RTSP/TCP 8554; download HTTP 8000 |
| Operator APIs and Bluetooth control | JSON / HTTP | TCP | Operator 8000; authenticated camera Bluetooth 8765 |

RTSP signaling still uses TCP. Every FFmpeg media path explicitly selects UDP. MediaMTX offers UDP only for RTSP and no WebRTC TCP listener. The browser checks the selected ICE candidate pair through `getStats()` before showing Online and labels the verified transport in Device Status. Interrupted playback retries after two seconds. API/recording controls and Bluetooth controls retain HTTP/TCP.

## Talkback and buffering

The UI captures an audio track and negotiates WHIP through the operator server. There are no HTTP audio batch uploads. MediaMTX accepts one publisher on `/talkback`; the PC serializes session setup/cleanup. Stop control carries a session ID so a delayed stop cannot terminate a newer session. On release, blur, navigation, failed ICE, or capture failure, tracks/peers stop and the WHIP resource is deleted. Decoder failure reports an error via `/api/talkback/status`; release and retry establish a fresh session.

The PC decoder resamples browser audio to 8 kHz mono PCM16. Its three-frame queue retains at most 60ms and discards frames older than 120ms, sending one 320-byte frame per 20ms tick. The camera microphone publisher drains capture backlog and keeps the newest full frame plus a partial next frame; it groups G.711 into 160-sample frames. FFmpeg/OS/WebRTC/BlueALSA still have their own buffering; these application limits do not imply a measured latency result.

TB2 retains a custom datagram format because the device already consumes PCM via ALSA and uses an authenticated pause/ack handshake. RTP sequence/timestamps alone would not replace access control; adding SRTP on this embedded receiver would require another validated runtime dependency. A future SRTP/RTP receiver can replace TB2 independently.

TB2 uses a network-order 24-byte header: `TB2`, one stop byte, 64-bit random session ID, 32-bit sequence number, 64-bit UTC timestamp in milliseconds. A PCM payload of at most 320 bytes follows, then a 16-byte truncated HMAC-SHA256 over header and payload. The token is never sent in the datagram. A stop has no payload and is sent three times for loss tolerance. TB1 is rejected. PC and camera must synchronize clocks within two seconds; packets outside that window are rejected. This authenticates data without encrypting PCM; use a trusted prototype LAN.

The camera retains a 40ms reorder window and at most six frames, rejects duplicate/already played frames, rejects frames over 120ms late or implausibly ahead, and rejects retired sessions/delayed stop packets. Its receive thread continues during BlueALSA profile switching, so stale queued speech is discarded after the pause acknowledgement. Nonblocking ALSA pipe writes prevent accumulated playback backlog. No packets for 500ms restore microphone capture, including lost stop packets. Persistent fixed-earbuds binding and reconnect remain in the Bluetooth service.

## Run and validate

On Windows, put MediaMTX v1.21.1 `mediamtx.exe` beside `app.py` and install FFmpeg/FFprobe on PATH. Run `python app.py --maix-ip <camera address>` after stopping any stack that owns 8000/8554/8889/8189. Open `http://127.0.0.1:8000/operator_test.html`. The UI starts while media retries, including unavailable earbuds/camera. Set `MAIX_IP` or pass `--maix-ip`; update the microphone startup template's `--target` to the PC LAN address.

For Linux Docker, use `docker compose -f compose.yaml -f compose.host.yaml up --build -d`. The base configuration includes RTP/RTCP port mappings. Host networking bypasses NAT source-port rewriting; host firewall rules must permit the protocol map's ports. Windows Docker Desktop bridge publication was tested and failed actual RTP delivery despite successful SDP/ICE negotiation. Use the native relay on Windows. [MediaMTX installation documentation](https://mediamtx.org/docs/kickoff/install) explains the RTSP UDP source-address/port requirement.

Before device deployment, run:

```text
python -m pc.check_camera_udp --maix-ip <camera address>
python -m unittest discover -s tests -v
cd frontend
npm test
```

`check_camera_udp` explicitly negotiates UDP and requires received video packets; DESCRIBE alone cannot pass. A connection timeout leaves capability unverified; a SETUP rejection such as 461 indicates the installed native server does not support that transport. If native MaixCAM UDP is unsupported, use a device-validated RTP publisher/RTSP server that can bind the existing hardware encoder, or a firmware/server update. That is a concrete deployment blocker; switching PC FFmpeg to TCP is not a migration fix.

For the opt-in integration fixture, start a separate native MediaMTX instance with a copy of `mediamtx.yml`: set `rtspAddress: :18554`, `webrtcAddress: :18889`, `webrtcLocalUDPAddress: :18189`; keep UDP 8002/8003; add a publisher path named `live`. Leave production services on their own ports. Then from PowerShell at the repository root:

```powershell
$env:UDP_INTEGRATION = '1'
python -m unittest discover -s tests -p test_udp_integration.py -v
```

This starts simulated H.264 camera and G.711 earbuds publishers, uses the actual `app.publisher_command` with isolated port substitutions, records MP4 through the real recorder, opens the compiled UI in real Chromium, verifies selected ICE UDP and decoded video, holds/release Talk through actual WHIP, and checks authenticated 20ms UDP frames and stop packets. It creates temporary recordings and cleans up its processes. Rebuild the compiled UI with `npm run build` before this test.

`upload_maix.ps1` now includes `pc/talkback_protocol.py` and backs up existing target files before replacing any. Deploy the microphone publisher, receiver, and protocol module together; keep PC/camera token values synchronized. Back up `/etc/rc.local` separately before installing its template. No device files were deployed during this implementation.

## Validation record (2026-10-10)

- Native Windows MediaMTX v1.21.1 + FFmpeg + Chromium: actual H.264/G.711 inputs through the PC publisher to H.264/Opus WHEP playback passed; selected ICE was UDP; actual WHIP talkback emitted 110 authenticated PCM frames of 320 bytes; stop received; MP4 decoded successfully. Inputs were simulated; no physical earbuds were involved.
- Docker image built; base and host-network Compose configurations parsed successfully. Windows Docker bridge test negotiated RTSP/WebRTC but no video arrived and the publisher timed out after 10 seconds. Linux host-network deployment is provided but not physically validated here.
- Python: 43 passed, one opt-in integration test skipped by default; that integration test passed separately. Playwright: 16 passed across source and compiled interfaces. These tests cover transport selection, bounded queues, jitter reordering, duplicates, stale/tampered packets, sessions, reconnects, and release during negotiation. The opt-in integration test is skipped in the default suite and was run separately.
- MaixCAM UDP probe to configured `192.168.1.7:8554/live` failed to connect. Installed native RTP/UDP support, physical video/microphone/talkback playback, profile switch timing, clock synchronization, physical A/V synchronization, and recording after device interruption remain unverified.
- End-to-end latency before/after: not measured. Once hardware is online, film an LED/time display and the admin monitor together at high frame rate; measure video delay over repeated trials. For audio, record the source click and speaker output on one recorder. Compare the previous TCP setup with this UDP setup under the same network, report median/p95, and separately measure first-speech delay after half-duplex profile switching. No latency improvement is claimed from transport alone.

The prototype retains the existing recording lifecycle: finalized files remain playable; an interrupted recorder reports inactive and requires a fresh recording. Stream and Bluetooth reconnection are automatic; seamless recovery within one MP4 and simultaneous SCO/A2DP audio require separate device validation.

## USB diagnostic fallback (follow-up verification)

Read-only SSH inspection of `ip -4 addr` confirmed `usb1 = 10.172.16.1/24`, `usb0 = 10.172.17.1/24`, and `wlan0 = 192.168.1.7/24`. Windows NCM and RNDIS adapters have `10.172.16.100` and `10.172.17.100`, respectively. SSH and Bluetooth control were reachable over both USB addresses. Wi-Fi SSH/Bluetooth are now reachable too; `netstat -lnt` on the device confirmed no RTSP listener on 8554. Native RTP/UDP support remains unverified until the RTSP service runs. This updates the earlier reachability result; no device configuration was changed.

`MAIX_USB_IP` / `--maix-usb-ip` default to `10.172.16.1`; use `10.172.17.1` if using RNDIS. The same configuration is passed through Compose. `GET /api/camera/diagnostics` and `python -m pc.camera_diagnostics` run bounded, concurrent TCP checks on SSH, RTSP signaling, and Bluetooth control. USB is checked when all Wi-Fi service checks fail. The admin interface provides a Diagnose camera button in Settings. These checks distinguish camera/network reachability from a missing RTSP service; they neither switch media routing nor claim UDP verification.

The fixed device-side USB address convention follows [Sipeed's screenless MaixCAM quick start](https://en.wiki.sipeed.com/maixpy/doc/en/README_no_screen.html); the concrete addresses above were verified on this device rather than assumed.

Follow-up validation: 48 Python tests passed (one opt-in media integration test skipped), 18 browser tests passed, compiled UI regenerated, Docker image rebuilt, and both Compose configurations validated.

## Deployed prototype (2026-10-10)

The PC prototype is running natively at `http://127.0.0.1:8000/operator_test.html` (prototype login `admin` / `admin`). The project Docker service was stopped to release its ports; unrelated containers were left running. Native MediaMTX, FFmpeg, and the operator API run under `app.py`; runtime PID/logs are in ignored `.runtime/pc.pid`, `pc-stdout.log`, and `pc-stderr.log`.

Updated camera programs and the shared TB2 module were uploaded over USB with existing-file backups in `/root/backup-20261010-132008`. Launcher app, app index, and `/etc/rc.local` were separately backed up in `/root/deployment-backup-20261010-1321`. The missing `/maixapp/auto_start.txt` was restored to `maix_rtsp`, the camera and background service templates were installed, and the camera was rebooted. RTSP, Bluetooth control, SSH, and UDP talkback services are now listening.

Physical-device checks: native camera RTP/UDP was explicitly verified with 91 H.264 packets; `/headsetmic` carried non-silent G.711/8kHz audio (mean -36.5dB, peak -16.6dB during a two-second check); fixed earbuds reported connected; combined media decoded to a 640x480 camera frame; a four-second MP4 containing H.264 video and AAC audio was finalized. A real WHEP peer decoded camera video and audio, and a real WHIP test using silent audio caused the camera microphone pause/ack handshake and an `aplay` process, then restored capture on stop. MediaMTX reported UDP ICE candidates. The test did not measure speaker sound quality or end-to-end latency.

The physical Wi-Fi UDP path shows packet loss and occasional corrupt video frames; ALSA reported startup underruns during the silent talkback check. These are prototype quality limits to tune with the device/network, not failures hidden by TCP fallback. No UI browser-control connection was available to open the page automatically; the URL above is ready for the user to open.

## UDP loss tuning (2026-10-10)

The deployed PC publisher now requests 4 MiB UDP socket buffers for both RTSP inputs and its output. MediaMTX also requests 4 MiB per UDP receive socket. Relay RTP payloads are capped at 1200 bytes in both FFmpeg and MediaMTX. Input reorder queues are explicitly bounded to 512 video packets and 128 microphone packets, with the existing 100 ms maximum reorder delay. Camera resolution, hardware encoder bitrate/frame rate, UDP transport, and USB diagnostic routing are unchanged. Buffer sizes absorb brief packet bursts rather than introducing a new playout delay. These options follow the [FFmpeg RTSP documentation](https://ffmpeg.org/ffmpeg-protocols.html#rtsp) and [MediaMTX configuration reference](https://mediamtx.org/docs/references/configuration-file).

Equal 30-second physical Wi-Fi observation windows logged 115 FFmpeg RTP gap events before tuning and 2 afterward (about 98% fewer reported gaps), with MediaMTX lost-packet warnings totaling 6 packets before and zero afterward. This is a short before/after comparison, not a network packet-loss percentage or a guarantee under other Wi-Fi conditions. The baseline contained a suspicious 65534-packet sequence jump, so its raw missing-packet total is not used as a loss-rate estimate. Runtime measurements are in ignored `.runtime/loss-before.json` and `.runtime/loss-after-buffers.json`; the tuned service logs are `.runtime/pc-tuned-stdout.log` and `.runtime/pc-tuned-stderr.log`.

A subsequent 45-second physical WHEP check decoded 1308 video frames and 2244 audio frames. The receiver reported 15202 video RTP packets and 2248 audio RTP packets, with zero lost packets on either track. During that window the camera input still reported three gap events totaling 12 missing packets; the local relay reported zero losses. These describe separate hops: clean WebRTC delivery does not recover packets already lost before the relay. All 48 Python tests passed; the opt-in isolated integration test was skipped in this run. No frontend code changed.

## Docker Desktop deployment (2026-10-10)

The prototype now runs in `maix-cam-server-server-1` using `compose.yaml` plus `compose.host.yaml`. Desktop host networking is enabled. Linux VM `net.core.rmem_max` and `net.core.wmem_max` were raised from 212992 to 4194304; without that change MediaMTX exited when requesting its larger UDP receive buffers. `start_docker.ps1` reapplies these limits before starting the container because a Desktop VM restart can reset them. Local `.env` stores camera/USB addresses, headset RTP port, and WebRTC advertised hosts; it is ignored by Git.

Desktop host forwarding rewrote incoming UDP source ports. The incoming camera headset RTSP publisher announced a different source port, so MediaMTX rejected its audio and timed out the session. An optional direct microphone RTP mode avoids this negotiation: MaixCAM `headset_mic_stream.py --target 192.168.1.4 --rtp-port 8004` sends 160-sample PCMU frames to UDP 8004, with RTCP on 8005; the PC supervisor's `--headset-rtp-port 8004` generates SDP and receives this as its audio input. The host Compose override selects this mode by default. Camera video still arrives over RTSP/RTP UDP, the PC publishes H.264/Opus `/maix01` locally, and browser playback/talkback remains WHEP/WHIP over UDP. The native RTSP microphone mode remains available by omitting both RTP-port options. The incoming RTP audio is unencrypted and unauthenticated, as with the previous headset RTP path; use the configured trusted LAN and scoped firewall rules.

Only the camera microphone script and its boot command were changed for this mode; backups are in `/root/docker-rtp-backup-20261010-080932`. The camera was rebooted after its RTSP server became unresponsive during repeated reconnect attempts. Container UDP video probing received 84 H.264 packets before that reboot; direct microphone probing received 82 G.711 packets. Physical Chromium playback subsequently decoded camera video, verified UDP ICE, connected WHIP talkback using a silent test source, and stopped cleanly; the fixed earbuds remained connected and camera capture resumed. A finalized 4.16-second host MP4 (`20261010T083304Z_3f880596.mp4`) contains 640x480 H.264 and AAC audio. Audible talkback quality and end-to-end latency were not measured.

Chromium without microphone permission advertised only an mDNS `.local` candidate and ICE timed out through Desktop. Granting microphone permission exposed usable IP candidates and the automated browser test passed. For the real UI, allow microphone permission for `http://127.0.0.1:8000` and reload, or briefly use Talk and allow the prompt before playback reconnects. The browser test uses an explicitly granted permission and a silent fake microphone, so it does not capture the PC's real microphone. Linux host networking has not been physically validated here. Wi-Fi/Docker scheduling still produces occasional upstream RTP gaps; the earlier native-Windows loss measurements are not measurements of this Docker deployment.

Post-change validation: 50 Python tests passed, one opt-in integration test skipped; the packet test checks actual RTP PCMU payload type, frame size, and 160-sample timestamp increments. All 18 frontend browser tests passed and the compiled page was regenerated. Docker image build, Compose validation, and complete decoding of the physical MP4 passed. See [the Docker run guide](docker-run-guide.md) for startup and diagnostics.
