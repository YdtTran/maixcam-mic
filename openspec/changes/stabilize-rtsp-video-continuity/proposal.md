# Proposal

## Why

Live verification of the token-free TB3 release exposed periodic RTSP/TCP video freezes and FFmpeg reconnect loops: on MaixCAM's shared 2.4 GHz Wi-Fi and Bluetooth eSCO radio, kernel TCP `Send-Q` buffering swells to 133–241 KB during brief wireless coexistence stalls until `VideoClient`'s 2-second write timeout closes the socket (`FIN-WAIT-1`), while the PC supervisor's 10-second startup grace window repeatedly kills reconnecting FFmpeg publishers (`Immediate exit requested`). Resolving this video continuity defect, preventing unsafe manual camera restarts against `launcher_daemon`, and verifying Windows host UDP8004/8005 port mappings are required to reach true operational completion and unblock the remaining OpenSpec changes in a controlled sequence.

## What Changes

- Coalesce per-frame interleaved RTP/RTCP writes, enable `TCP_NODELAY`, bound `SO_SNDBUF`, and extend the client write timeout to 10 seconds in `maix/video_rtsp.py` so transient 2.4 GHz Wi-Fi/SCO coexistence stalls do not accumulate 200+ KB kernel backlogs or sever active RTSP sessions after 2 seconds.
- Reset `waiting_keyframe = True` whenever `VideoServer.publish()` evicts an unsent frame from a full client queue (`Queue(maxsize=2)`), ensuring congested readers drop stale P-frames at the application layer and resume cleanly on the next IDR keyframe with repeated SPS/PPS rather than decoding broken references or truncated RTP packets.
- Increase the FFmpeg publisher startup grace period in `app.py` from 10 seconds to 20 seconds so `rtsp_path_available("maix01")` health checks do not send `SIGTERM` (`Could not write header for output file #0: Immediate exit requested`) while FFmpeg is waiting for an IDR keyframe and completing RTSP input probing over Wi-Fi.
- Verify Windows host UDP `8004` and `8005` listeners in `deploy_pc.ps1` and `scripts/deploy.ps1` after container start, automatically recreating the project container once if Docker Desktop fails to bind the host UDP return port.
- Document and enforce `launcher_daemon`-safe camera video recovery (normal camera reboot or launcher-managed restart rather than raw SSH `SIGINT` plus manual `python3 /maixapp/apps/maix_rtsp/main.py` while MMF/ISP pipes are held) and require a sustained 60-second live video/audio continuity check before declaring deployment acceptance.
- Establish the step-by-step completion flow across the four active OpenSpec changes (`stabilize-rtsp-video-continuity`, `remove-local-network-token-auth`, `harden-runtime-and-trim-obsolete-code`, and `add-guided-desktop-setup`), preserving TCP/video monitoring, independent UDP8004 headset return, SCO duplex ordering, TB3 talkback, 768x432 rotation, and multistream recording.

## Capabilities

### New Capabilities

- `rtsp-video-continuity`: Bounded RTSP/TCP frame delivery with keyframe-aligned queue eviction, tolerant publisher startup supervision, verified host UDP return-audio port mappings, and `launcher_daemon`-safe camera video recovery.

### Modified Capabilities

None. `openspec list --specs` returns no existing main specifications. This change directly unblocks operational acceptance of `remove-local-network-token-auth` and coordinates with Task 7 of `harden-runtime-and-trim-obsolete-code` (which removes legacy 480x640 padding helpers from `maix/video_rtsp.py`).

## Impact

- Camera: `maix/video_rtsp.py` (`VideoServer`, `VideoClient`).
- PC runtime: `app.py` (publisher startup grace window and health check timing).
- Deployment & verification: `deploy_pc.ps1`, `scripts/deploy.ps1`, `scripts/NetworkDeployment.psm1`, and operational recovery documentation (`docs/rtsp-transport.md`, `docs/docker-run-guide.md`, `scripts/README.md`).
- Tests: `tests/test_camera_rotation.py`, `tests/test_rtsp_transport.py`, `tests/test_start_scripts.py`, `tests/test_network_deployment.py`.
- No new dependencies, no protocol breaking changes, and no live code edits or deployments in this planning step.
