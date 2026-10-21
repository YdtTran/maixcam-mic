# Tasks

## 1. Align the pending plans with the confirmed scope

- [x] 1.1 Update the two pending changes' proposal/design/spec/task text to follow this decision: remove new-release token adoption/preservation requirements and defer additional Host/Origin hardening, while retaining unrelated reliability/setup work and historical audit evidence. Verify both changes pass strict OpenSpec validation and no unrelated tasks are marked complete.

## 2. Remove the runtime token and packet signature

- [x] 2.1 Remove token arguments, HMAC signing/verification and token imports in the shared protocol; use the TB3 marker with the existing 24-byte header. Verify round-trip PCM/stop, 344-byte maximum, stale/malformed/odd/oversized packet rejection and explicit TB1/TB2 rejection in focused protocol tests.
- [x] 2.2 Remove token state/CLI reads from PC talkback and camera receiver, updating every caller and integration fixture. Verify sender pacing, queue bounds, retired sessions, stale browser stop, SCO duplex and A2DP pause/ack tests still pass with token-free packets.
- [x] 2.3 Remove the Bluetooth shared-token header/check and camera connector token flag/read. Add the talkback protocol version to existing control responses and reject incompatible calibration clearly; verify no-header status/clock/scan/select, invalid bodies/actions, fixed-device refusal, clock skew and timeout cases without token fixtures.
- [x] 2.4 Make both PC entry points initialize camera control/talkback without a token file. Verify absent, malformed and mismatched legacy token files have no startup effect, retained calibration is wired, normal network failures are visible and obsolete token CLI arguments are absent from help.
- [x] 2.5 Update `docs/architecture.md`, its diagram where needed, and maintained talkback/UDP/audio guides for TB3 and token-free HTTP; verify header sizes, endpoint names and example arguments match code, preserving historical deployment sections as dated evidence.

## 3. Remove deployment prerequisites and preserve old-release recovery

- [x] 3.1 Remove token creation/validation/upload from `deploy_pc.ps1`, `deploy_maix.ps1` and `scripts/deploy.ps1`, and remove the active Compose token mount. Verify existing deployment/dry-run/idempotence fixtures work without creating a token and Compose configuration resolves without a token file; retain useful progress output and existing non-token preflights.
- [x] 3.2 Separate optional legacy recovery files from the new camera install list, capture the old runtime configuration/image and retain any old token privately for rollback. Verify fixtures restore an old token-mounted image using the captured old configuration rather than the edited new Compose file, with no token content in logs.
- [x] 3.3 Handle missing/malformed legacy recovery material without blocking normal token-free deployment. Verify fresh/no-token upgrades pass while rollback fixtures explicitly report unavailable old-release talkback recovery instead of claiming a complete restore.
- [x] 3.4 Add TB3 compatibility verification to combined deployment and clear mixed-version guidance for direct entry points. Verify partial camera/PC activation fails final verification and attempts compatible-pair recovery; retain recording/finalization checks, expected process counts, SCO ordering and real video/headset-return checks.
- [x] 3.5 Remove obsolete active token files only after compatible new-release verification, retaining recovery copies and ignore protection. Verify old running services keep their files until replacement, failed cleanup cannot prevent new startup, and no recordings/SSH/Bluetooth pairing data are removed.
- [x] 3.6 Update root README, `scripts/README.md` and installer/recovery guides to remove token-copy/setup steps and explain the one-time paired update. Verify maintained commands no longer take token parameters and the admin login, SSH preparation and recording-safe procedures remain documented.

## 4. Verify the complete no-token path

- [x] 4.1 Update the isolated headset/UDP media fixtures to collect TB3 without secrets and exercise real WHIP-to-packet speech/stop delivery. Run those isolated integrations and verify accepted audio frames, session stops, unchanged independent return and playable recording output without touching production ports/devices.
- [x] 4.2 Run `python -m unittest discover -s tests -v`, `npm test` in `frontend` and `docker compose config --quiet`. Verify no failures, report skipped cases, and confirm both browser builds retain admin login and normal recording/rotation workflows.
- [x] 4.3 Search maintained runtime/configuration/docs/tests for `.talkback_token`, token CLI flags, `X-Control-Token`, HMAC and TB2 references. Verify remaining references are limited to deliberate legacy recovery, rejection tests, historical evidence or explicit migration instructions; confirm there is no replacement shared secret, auth-mode flag or new package dependency.
- [x] 4.4 Review the diff against the spec and record source/test results in a dated session note linked from AGENTS.md. Verify changes stay within token removal and do not implement the deferred hardening, rewrite the login or claim live/audible acceptance without evidence.

## Workflow follow-up

- Source implementation and tracked automated checks are complete. Subsequent user-authorized live deployment exposed video continuity failures; normal reboot restored a working run but the intermittent camera fault remains unresolved. See `docs/sessions/2026-10-20-token-free-live-verification.md` before treating this release as accepted or archiving it.
- If both devices are later redeployed, complete the coordinated update and manual picture/listen/Talk/recording checks before discarding old active token files. Retain private rollback snapshots and report actual final runtime state.
