# Proposal

## Why

The user prioritizes easy, reliable deployment on a trusted local Wi-Fi network. The shared `.talkback_token` adds file generation, copying, validation, Docker mounting and mismatch recovery across the PC and camera without being wanted for this deployment model.

## What Changes

- Remove the shared-token requirement from PC startup, camera Bluetooth services and talkback playback. Missing, malformed or mismatched old token files no longer disable these features.
- Remove token generation, validation, synchronization, upload and active Docker mounting from deployment. No replacement secret, fixed key, authentication toggle or new dependency.
- Remove `X-Control-Token` checks/headers and the talkback packet authentication signature.
- **BREAKING:** Replace authenticated TB2 talkback packets with a distinct token-free TB3 format. Update the PC sender and camera receiver together; reject mixed protocol versions rather than treating old signature bytes as audio.
- **BREAKING:** Remove the token CLI parameters and token constructor/function arguments throughout internal callers and tests. Update current commands and documentation instead of retaining unused compatibility flags.
- Preserve the existing admin/admin prototype login, SSH credentials/host verification, fixed headset binding, Bluetooth pairing keys, packet bounds/freshness/sequence checks, camera clock calibration, safe recording checks and backups.
- Preserve TCP/video, independent UDP8004 headset return, SCO startup order, rotation and multistream recordings.
- Provide a coordinated update/rollback procedure that retains old token material privately only when needed to restore the previous token-based release. Do not delete credentials out from under a running old installation.
- Defer the earlier audit's proposed additional Host/Origin hardening. Keep the existing operator Origin check and loopback publication; removing working checks that do not obstruct deployment is outside this change.

## Capabilities

### New Capabilities

- `trusted-lan-device-control`: Token-free device control and talkback, deployment without pairing-secret files, compatible audio validation and coordinated release migration.

### Modified Capabilities

None. `openspec list --specs` returns no main specifications. Two pending changes contain conflicting token-preservation requirements: `harden-runtime-and-trim-obsolete-code` and `add-guided-desktop-setup`. This proposal supersedes their token requirements and defers new access hardening; their remaining reliability/setup work stays separate. Reconcile their planning text during application so future work does not reintroduce token provisioning.

## Impact

- PC: `app.py`, `pc/operator_server.py`, `pc/talkback.py`, `pc/talkback_protocol.py`, `pc/bluetooth_client.py`.
- Camera: `maix/talkback_receiver.py`, `maix/bluetooth_control.py`, `maix/bluetooth_audio.py`; deployed protocol copy and launcher payload.
- Deployment: `compose.yaml`, PC/camera PowerShell entry points, `scripts/deploy.ps1`, backup/rollback handling, fixtures and related tests.
- Documentation: customer README, installer/network/architecture/audio guides and diagrams where they describe current token use; historical evidence remains historical.
- No third-party package is required solely by token authentication, so this removes code/configuration dependencies, not an installed library. No frontend login rewrite or live deployment is authorized by this proposal.
