# Proposal

## Why

The accepted camera/audio pipeline works, but the audit found reproducible failures in talkback recovery, persisted-state handling and legacy recording reporting, plus gaps in local HTTP trust and recording-safe deployment. Fix these before extending customer setup; remove only obsolete paths verified against current callers.

## What Changes

- Retain existing operator Origin checking and loopback publication; additional Host/Origin hardening is deferred by `remove-local-network-token-auth`.
- Make stop, update, camera reboot and rollback exclude new recording starts for the entire mutation window, and serialize competing deployment commands.
- Release failed or abandoned talkback sessions without requiring the browser to send Stop; preserve session ownership, clock calibration and TB3 framing, freshness and session checks.
- Isolate malformed optional camera-view and recording metadata so they cannot stop the operator or hide otherwise usable recordings; preserve invalid files and show actionable diagnostics.
- Report legacy capture failure and forced termination honestly, keeping failed output available for recovery without listing it as a successful saved recording.
- Download real recordings through the browser's native download path instead of fetching the entire video into an application Blob.
- Remove unused padding/SPS-cropping support for the superseded 480x640 camera pipeline, and move its RTSP integration fixture to the current 768x432 baseline.
- Align the installer's SSH instructions with the actual Windows OpenSSH implementation, coordinating this edit with the existing desktop-setup change.
- Preserve TCP/video monitoring, independent UDP8004 microphone return, SCO boot ordering, fixed headset identity, saved recordings, rotation semantics and the explicit legacy/A2DP fallbacks.
- Exclude framework migration, a frontend rewrite, remote-user authentication, new desktop packaging and changes to physical media timing. No new dependencies.

## Capabilities

### New Capabilities

- `local-operator-access`: Preserve existing local exposure defaults; additional authority/origin hardening is deferred.
- `recording-lifecycle`: Exclusive maintenance, truthful completion, tolerant metadata and native file downloads.
- `talkback-session-lifecycle`: Failure cleanup, abandoned-session recovery and protection from stale workers.

### Modified Capabilities

None. `openspec list --specs` returned no existing main specifications. The unimplemented `add-guided-desktop-setup` change remains separate; it must reuse the resulting recording-maintenance contract rather than add a second one.

## Impact

- `pc/operator_server.py`, `pc/talkback.py`, and their focused Python tests.
- `deploy_pc.ps1`, `stop_docker_pc.ps1`, `run_all.ps1`, `deploy_maix.ps1`, `scripts/deploy.ps1`, shared deployment helpers and mock-based PowerShell tests.
- `frontend/src/main.tsx`, browser download/failure tests, and `maix/video_rtsp.py` with `tests/test_camera_rotation.py`.
- README/deployment/recovery documentation; no media protocol, customer data migration or dependency changes.
- Detailed evidence and verification limits are in `audit.md` beside this proposal. This change plans source updates only; implementation and any live deployment require a later apply request.
