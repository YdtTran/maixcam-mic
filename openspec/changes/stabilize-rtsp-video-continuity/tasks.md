# Tasks

## 1. Harden MaixCAM RTSP/TCP frame delivery and keyframe recovery

- [x] 1.1 Update `maix/video_rtsp.py` to set `TCP_NODELAY`, bound client `SO_SNDBUF` (`65536`), extend the playing client write timeout to `10` seconds, and coalesce all interleaved RTP/RTCP packets for a frame into a single `sendall()` call; verify unit tests in `tests/test_camera_rotation.py` confirm coalesced frame delivery, unchanged RTP packetization, and tolerance of >2s simulated write stalls under 10s.
- [x] 1.2 Track per-client frame-drop state in `VideoServer.publish()` so evicting an unsent frame from a full client queue (`Queue(maxsize=2)`) sets `waiting_keyframe = True` for that client; verify unit tests confirm dropped P-frames withhold subsequent non-keyframes until the next IDR keyframe (`nal_unit_type == 5`) and prepend current SPS/PPS.

## 2. Relax PC publisher startup supervision and verify host UDP return ports

- [x] 2.1 Increase the FFmpeg publisher startup grace period in `app.py` from `10` seconds to `20` seconds while retaining fast restart when `publisher.poll()` reports process exit; verify tests in `tests/test_rtsp_transport.py` confirm a running publisher taking 10–18s to publish `/maix01` is not terminated prematurely and an exited or >20s stalled publisher is restarted.
- [x] 2.2 Add Windows host UDP `8004`/`8005` listener verification (and single-project container recreate when a listener is missing while idle) to `deploy_pc.ps1` and `scripts/NetworkDeployment.psm1`, and document `launcher_daemon`-safe camera video recovery in `docs/rtsp-transport.md`, `docs/docker-run-guide.md`, and `scripts/README.md`; verify mock deployment tests in `tests/test_start_scripts.py` and `tests/test_network_deployment.py` cover missing UDP listener recovery.

## 3. End-to-end automated verification

- [x] 3.1 Run `python -m unittest discover -s tests -v`, `npm test` in `frontend/`, and `docker compose config --quiet`; verify all checks pass with zero regressions and record any expected environment skips.

## Workflow follow-up

- **Phase 1 — Live deployment & sustained continuity verification for `stabilize-rtsp-video-continuity` + `remove-local-network-token-auth`:**
  - When authorized, verify recording/finalization are idle and run `powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File scripts/deploy.ps1 -UsbInterfaceIndex 17 -UsbPeerIP 10.172.16.1 -Force`.
  - Verify single-instance camera processes (`PID` under `launcher_daemon` for `maix_rtsp/main.py`, `bluetooth_audio.py`, `talkback_receiver.py`, `headset_mic_stream.py`), Windows UDP `8004`/`8005` listeners, and a sustained 60-second browser check showing continuous decoded video frame progression without camera `FIN-WAIT-1` disconnects or PC `Immediate exit requested` logs, plus working UDP8004 headset return, TB3 Talk, 0°/90° rotation, and multistream recording/playback.
  - Record live verification results in `docs/sessions/` and `AGENTS.md`.
- **Phase 2 — Archive completed token-free and continuity changes:**
  - Once Phase 1 live verification passes, archive `remove-local-network-token-auth` and `stabilize-rtsp-video-continuity` (`openspec archive`).
- **Phase 3 — Apply, verify, and archive `harden-runtime-and-trim-obsolete-code`:**
  - Apply tasks 1–8 of `harden-runtime-and-trim-obsolete-code` (talkback session cleanup, malformed metadata resilience, recording-safe maintenance locks across scripts, honest legacy recording status, native browser downloads, removal of unused 480x640 `pad_nv21`/`crop_encoder_padding` in `maix/video_rtsp.py`, and OpenSSH doc alignment).
  - Run automated tests, redeploy while idle, verify affected live workflows (picture, listening, Talk recovery, rotation, recording/download, maintenance lock), record evidence, and archive `harden-runtime-and-trim-obsolete-code`.
- **Phase 4 — Apply, verify, and archive `add-guided-desktop-setup`:**
  - Apply tasks 1–7 of `add-guided-desktop-setup` on top of the hardened runtime and maintenance contract, run tests, verify USB-first setup and daily launch on target hosts, and archive.
