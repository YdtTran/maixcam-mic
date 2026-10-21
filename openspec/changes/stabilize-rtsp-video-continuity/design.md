# Design

## Context

See `proposal.md` for motivation and scope, and `specs/rtsp-video-continuity/spec.md` for the behavioral contract.

Live diagnostics on MaixCAM (`10.172.16.1` / Wi-Fi `192.168.1.7`) and the PC Docker container (`maix-cam-server-server-1`) isolated three interacting failure modes behind the post-deployment video freezes:

1. **Kernel TCP `Send-Q` bloat + 2-second `sendall()` timeout in `maix/video_rtsp.py`:**
   - `VideoClient.handle()` sets `self.request.settimeout(2)` and uses `self.frames = queue.Queue(maxsize=2)` to bound application queuing.
   - However, Linux TCP auto-tuning expands `SO_SNDBUF` on `:8554` so `Send-Q` reaches 133–241 KB (`FIN-WAIT-1 0 132981` observed in `strace`/`ss`). Because MaixCAM shares a single AIC8800 2.4 GHz radio/SDIO bus across Wi-Fi TCP video (~1.5–2 Mbps at 12–13 fps) and active Bluetooth eSCO (`hci0`, `MTU 120:4`), brief wireless coexistence stalls (`rto: 0.88s–2.15s`) pour 15–20 encoded frames into the kernel TCP buffer instead of triggering `Queue(maxsize=2)` eviction.
   - Once `Send-Q` fills, a 2.0-second stall causes `ppoll(POLLOUT, 2000ms) = 0 (Timeout)`, raising `socket.timeout` (`OSError`) inside `self.request.sendall()`. `VideoClient.handle()` catches `OSError` and closes the socket (`shutdown(SHUT_WR)` + `close()`), truncating the in-flight RTP packet (`[h264] error while decoding MB ...`) and leaving 33–133 KB in `FIN-WAIT-1` `Send-Q` that continues transmitting over Wi-Fi for 5+ seconds while the next FFmpeg process tries to reconnect.
   - In addition, `VideoServer.publish()` currently evicts the oldest frame from `client.frames` on `queue.Full` without notifying `VideoClient` that a reference frame was skipped, and `send_frame()` invokes `self.request.sendall()` once per 1200-byte RTP fragment (~10–25 syscalls per frame).

2. **Premature 10-second publisher kill loop in `app.py`:**
   - `app.py` checks `now - publisher_started >= 10` and `not path_available("maix01")`. When FFmpeg reconnects while the previous `FIN-WAIT-1` socket is still draining over Wi-Fi, TCP handshake + `DESCRIBE`/`SETUP`/`PLAY` + waiting up to 2.5 seconds for the next 30-frame GOP IDR keyframe + FFmpeg input probing (`-analyzeduration 1000000 -probesize 1000000`) can take ~10 seconds.
   - At 10.0 seconds, `app.py` sends `SIGTERM` to FFmpeg right as it opens the output RTSP connection to MediaMTX, producing `Could not write header for output file #0 (incorrect codec parameters ?): Immediate exit requested` every 10 seconds.

3. **Unsafe manual camera video restarts & missing Windows UDP8004 listener detection:**
   - `/maixapp/apps/maix_rtsp/main.py` is supervised by `/maixapp/apps/launcher/launcher_daemon` (`PID 291`). Sending `SIGINT` and manually starting a second `python3 /maixapp/apps/maix_rtsp/main.py` over SSH races hardware MMF/ISP teardown (`cvi-vi`, `cvi-vpss`, `/tmp/isp_fifo`), causing `camera read timeout` and `RuntimeError: : Value is NULL: camera read failed`.
   - On Windows Docker Desktop, stopping and starting the container can occasionally leave UDP port `8004` unbound on the Windows host (`8005` bound, `8004` absent) until the container is recreated.

## Goals / Non-Goals

**Goals:**
- Prevent transient 2.4 GHz Wi-Fi/SCO stalls from severing the camera RTSP/TCP connection or corrupting H.264 framing.
- Ensure application-level frame dropping (`Queue(maxsize=2)`) engages before kernel TCP buffers accumulate multi-second backlogs, and resynchronize on the next IDR keyframe after any drop.
- Eliminate the 10-second FFmpeg publisher `SIGTERM` death loop in `app.py`.
- Detect and recover missing Windows host UDP `8004`/`8005` listeners during PC deployment.
- Define a deterministic step-by-step workflow to complete and archive all active OpenSpec changes (`stabilize-rtsp-video-continuity`, `remove-local-network-token-auth`, `harden-runtime-and-trim-obsolete-code`, `add-guided-desktop-setup`).

**Non-Goals:**
- Switching live video from RTSP/TCP to UDP or changing the 768x432 90° CCW camera rotation baseline.
- Modifying the TB3 talkback protocol, SCO MTU boot ordering, or multistream recorder format.
- Adding third-party dependencies on the camera or PC.

## Decisions

### 1. Coalesce per-frame RTSP writes, bound `SO_SNDBUF`, and extend write timeout in `maix/video_rtsp.py`

In `VideoClient`:
- Configure `TCP_NODELAY = 1` and bound `SO_SNDBUF` (e.g., `65536` bytes, which Linux doubles to 128 KB ceiling or keeps tight enough for ~2–3 keyframes while preventing 240+ KB bloat) and set `self.request.settimeout(10.0)` (matching `mediamtx.yml` `writeTimeout: 10s`) once play starts, while keeping a short timeout (`2.0s`) or non-blocking `select` for initial RTSP control commands.
- In `send_frame()`, assemble all interleaved `$ + channel + length + RTP header + payload` packets (and any due RTCP Sender Report) for the frame into a single `bytearray`/`bytes` buffer and invoke `self.request.sendall(frame_bytes)` once per frame instead of 10–25 times per frame.
- Represent each client in `VideoServer.clients` as the `VideoClient` instance (or a lightweight state wrapper holding `frames` queue + `dropped` flag) rather than a bare `Queue`. When `VideoServer.publish()` evicts an older frame from a full client queue (`queue.Full`), mark `client.waiting_keyframe = True` under lock so the client skips subsequent P-frames until the next IDR keyframe (`nal_unit_type == 5`) and prepends `sps` and `pps`.

*Alternatives considered:*
- *Increasing `settimeout` alone without bounding `SO_SNDBUF` or resetting `waiting_keyframe`:* Would prevent the 2-second disconnect, but multi-second video lag would remain trapped in the kernel TCP buffer and any eventual queue drop would feed P-frames with missing reference frames to FFmpeg.
- *Switching to non-blocking partial writes per RTP packet:* Risks dropping mid-frame RTP fragments, which breaks RTSP interleaved framing (`$ + channel + 2-byte length`) and causes FFmpeg demuxer errors. Once a frame starts writing to the TCP stream, its interleaved framing must remain atomic.

### 2. Increase PC publisher startup grace period in `app.py` to 20 seconds

Change `PUBLISHER_STARTUP_GRACE_SECONDS = 20` (up from `10`) in `app.py`'s main supervision loop:
- `check_stream = now - publisher_started >= 20 and now - last_health_check >= 2`
- If `publisher.poll() is not None` (FFmpeg actually exited on connection refused or timeout), `app.py` still reconnects as soon as `now >= next_retry_at` (`2` seconds). Only the forced kill of a *still-running* FFmpeg process waiting for `/maix01` to appear is relaxed from 10s to 20s.

*Alternatives considered:*
- *Reducing FFmpeg `-analyzeduration` / `-probesize` to zero:* Risky for H.264 copy over RTSP when SPS/PPS/IDR arrival is delayed by up to one GOP. Increasing the watchdog grace window for a still-running process costs nothing on fast startups and prevents killing slow Wi-Fi handshakes.

### 3. Verify Windows host UDP 8004/8005 listeners in deployment scripts

In `deploy_pc.ps1` (and shared helpers in `scripts/NetworkDeployment.psm1` used by `scripts/deploy.ps1`):
- After `docker compose up -d` and container health verification, inspect Windows host UDP endpoints (`Get-NetUDPEndpoint -LocalPort 8004, 8005` or `netstat -ano -p udp`) when `RETURN_AUDIO_PORT` is configured (default `8004`).
- If port `8004` or `8005` is missing on the Windows host while the container is running and recording/finalization are idle, run `docker compose up -d --force-recreate --no-deps server` once and re-verify both UDP listeners and HTTP health before succeeding.

### 4. Enforce `launcher_daemon`-safe camera recovery and step-by-step OpenSpec completion flow

- Document in `docs/rtsp-transport.md`, `docs/docker-run-guide.md`, and `scripts/README.md` that `/maixapp/apps/maix_rtsp/main.py` is owned by `launcher_daemon` (`PID 291`); recovery when the camera video service is unresponsive must use a recording-safe normal camera reboot (or `deploy_maix.ps1 -Reboot` / `scripts/deploy.ps1`), never a raw SSH `SIGINT` + manual `python3 /maixapp/apps/maix_rtsp/main.py` spawn while `launcher_daemon` is active.
- Sequence the four OpenSpec changes so edits to overlapping files (`maix/video_rtsp.py`, `deploy_pc.ps1`, `scripts/deploy.ps1`, `docs/docker-run-guide.md`) never conflict:
  1. **Step 1 (`stabilize-rtsp-video-continuity`):** Implement `maix/video_rtsp.py`, `app.py`, and Windows UDP listener verification; run unit/integration tests; redeploy PC + camera via `scripts/deploy.ps1`; run a 60-second sustained live browser continuity check (video frames advancing continuously without `FIN-WAIT-1` drops, UDP8004 return audio decoded, TB3 Talk working, rotation 0/90° and recording/playback verified).
  2. **Step 2 (Close & Archive `remove-local-network-token-auth` + `stabilize-rtsp-video-continuity`):** Record the verified live evidence in `docs/sessions/` and `AGENTS.md`, then archive both completed changes.
  3. **Step 3 (`harden-runtime-and-trim-obsolete-code`):** Apply tasks 1–8 on top of the stabilized `maix/video_rtsp.py` and deployment scripts (including removing obsolete `pad_nv21`/`crop_encoder_padding` in Task 7), run full test suites, redeploy while idle, verify live workflows, and archive.
  4. **Step 4 (`add-guided-desktop-setup`):** Apply tasks 1–7 reusing the hardened maintenance lock and stabilized runtime, verify on target hosts, and archive.

## Risks / Trade-offs

- **Setting `SO_SNDBUF` too small could truncate bursty keyframes** → Use `65536` bytes (Linux kernel doubles `setsockopt(SO_SNDBUF, 65536)` to `131072` bytes internal sk_buff accounting, ~60–80 KB effective payload), which comfortably holds a full 768x432 IDR keyframe while preventing 240+ KB multi-second queues.
- **10-second socket write timeout could keep a dead reader thread alive for up to 10s** → `VideoServer` is a `ThreadingTCPServer` where each reader has its own daemon thread and `Queue(maxsize=2)`; a blocked reader thread only drops its own queued frames and never blocks `cam.read()`, `encoder.encode()`, or new reconnecting readers.
- **Container recreate on missing Windows UDP 8004 adds ~5–10s when Docker Desktop drops the port** → Only triggered when the Windows host UDP listener is actually missing and recording is idle, preventing silent post-deployment microphone-return outages.

## Migration Plan

1. Implement `maix/video_rtsp.py`, `app.py`, and `deploy_pc.ps1` / `scripts/NetworkDeployment.psm1` changes with regression tests in `tests/`.
2. Run `python -m unittest discover -s tests -v`, `npm test` in `frontend/`, and `docker compose config --quiet`.
3. When authorized to deploy, verify recording/finalization are idle, run `scripts/deploy.ps1 -UsbInterfaceIndex 17 -UsbPeerIP 10.172.16.1 -Force`, and verify 60 seconds of uninterrupted browser video + return audio + TB3 talkback + recording before archiving `remove-local-network-token-auth` and `stabilize-rtsp-video-continuity`.
