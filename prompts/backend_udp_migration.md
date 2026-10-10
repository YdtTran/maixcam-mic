Implement a low-latency UDP media pipeline in this repository. Follow AGENTS.md, inspect the current implementation first, and preserve unrelated edits. Use generic component names such as earbuds, PC relay, and admin interface; retain MaixCAM-specific names.

Current architecture:
- MaixCAM video: native maix.rtsp server, consumed by app.py using RTSP/TCP.
- Earbuds microphone: BlueALSA SCO capture, 8 kHz mono PCM; maix/headset_mic_stream.py encodes G.711 μ-law and publishes /headsetmic over RTSP/TCP.
- app.py combines camera video and earbuds audio, converts audio to Opus, and publishes /maix01 to MediaMTX.
- Browser playback already uses WebRTC/WHEP.
- Browser talkback sends 100 ms PCM batches through HTTP POST.
- pc/talkback.py forwards PCM over UDP port 9002 to maix/talkback_receiver.py.
- Talkback playback uses A2DP and temporarily pauses earbuds microphone capture.
- MaixCAM has a persistent fixed-earbuds binding with automatic reconnect. Preserve it.

Objective:
Move network media transport to UDP and reduce buffering while retaining playback, recording, talkback, and reconnect behavior.

Requirements:
1. Verify that the installed MaixCAM RTSP server supports RTP/UDP negotiation. Test it explicitly; do not assume native RTSP implies UDP support.
2. Migrate camera ingestion and earbuds microphone publication to RTSP with RTP/RTCP over UDP. Keep RTSP control/signaling on TCP.
3. Update every affected publisher, receiver, startup script, MediaMTX setting, and Docker UDP port mapping. Check pc/run_publisher.ps1 as well as app.py. Avoid unintended TCP media fallback.
4. Keep browser playback on WebRTC with UDP media. Verify the selected ICE transport at runtime.
5. Replace browser talkback’s HTTP audio uploads with WebRTC audio to the PC relay. Make only the frontend changes necessary for this transport migration.
6. Evaluate RTP/UDP for PC-to-MaixCAM talkback. Preserve token-based access control or provide equivalent protection; do not expose tokens. Add sequence numbers, timestamps, bounded jitter buffering, and stale-packet dropping if retaining a custom UDP protocol.
7. Use small audio frames, targeting 20 ms initially. Bound queues and discard stale audio rather than accumulating delay.
8. Preserve hardware video encoding and avoid video transcoding where compatible. Verify audio codec compatibility and preserve audio/video synchronization.
9. Preserve current half-duplex behavior initially. Treat simultaneous HFP/SCO microphone and playback as a separate change requiring device validation.
10. Keep HTTP APIs and Bluetooth control on their existing transports. Migrate media paths, not every TCP connection.
11. Preserve recording functionality and automatic recovery after camera, earbuds, or network interruption.
12. Do not claim a latency improvement solely because transport changed. Measure end-to-end latency before and after where hardware permits.

Validation:
- Add meaningful regression tests for transport configuration, packet handling, queue limits, and reconnect behavior.
- Run the Python suite and relevant browser tests.
- Rebuild pc/operator_test.html if frontend code changes.
- Validate Docker configuration and actual UDP reachability.
- Perform available MaixCAM hardware checks, including video, earbuds microphone, talkback, and recording.
- Clearly distinguish automated checks, physical-device checks, and anything unverified.

Deliver:
- Working implementation and updated documentation.
- A protocol map showing each media path, codec, transport, and port.
- Test results and measured latency where available.
- Concrete remaining blockers if a native MaixCAM feature is unsupported.

Complete local implementation and verification before deploying. Back up device files before any authorized MaixCAM deployment.
