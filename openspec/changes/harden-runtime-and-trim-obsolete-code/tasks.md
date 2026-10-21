# Tasks

## 1. Preserve existing local access defaults

- [x] 1.1 Verify the existing operator Origin check, loopback publication and prototype login remain unchanged; additional Host/Origin hardening is deferred by `remove-local-network-token-auth`.

## 2. Recover failed talkback sessions

- [x] 2.1 Make worker/session cleanup identity-bound and idempotent in `pc/talkback.py`; verify failed decoder spawn and lost media release the WHIP resource and permit a new offer without browser Stop.
- [x] 2.2 Reap decoder/workers outside shared locks and preserve failure diagnostics; verify bounded cleanup, no self-join, and delayed old cleanup/Stop cannot clear new ownership or send a stop packet for the new session.
- [x] 2.3 Update `docs/headset-return-audio.md` with retry/recovery behavior; run talkback, UDP protocol and Bluetooth clock tests to confirm TB3 framing, freshness, calibration and bounded queues remain intact.

## 3. Isolate malformed optional metadata

- [x] 3.1 Validate saved camera-view JSON in `RecordingManager` with safe rotation-zero fallback and preserved original data; verify truncated JSON, arrays, null, missing rotation and invalid values do not prevent startup, while valid persisted angles still restore.
- [x] 3.2 Validate per-recording metadata shape and duration without aborting the recording list; verify malformed/array/null/nonfinite values leave valid media listed with unknown duration and no original files are deleted.
- [x] 3.3 Surface separate actionable metadata warnings in status/UI and document recovery; verify source/compiled UI shows the warning without falsely reporting capture failure and clears it after a valid view replacement.

## 4. Exclude recording during all maintenance mutations

- [x] 4.1 Add owner-bound maintenance acquisition/release and persisted marker checks under `RecordingManager`'s existing lock; verify capture/finalization refuse acquisition, maintenance refuses start, foreign owners cannot release it, and recreating the manager retains exclusion.
- [x] 4.2 Add project-scoped mutation locking and shared maintenance helpers for nested Windows scripts; verify competing processes cannot both mutate and check-only/dry-run do not leave a lock marker or modify settings.
- [x] 4.3 Integrate maintenance across `deploy_pc.ps1`, `stop_docker_pc.ps1`, `run_all.ps1`, `deploy_maix.ps1` and `scripts/deploy.ps1`, including audio recovery and rollback; verify a browser start between preflight and mutation is refused throughout the operation.
- [x] 4.4 Handle stopped/unavailable operators, first upgrade from a pre-maintenance image and rollback to one; verify an unresponsive running operator blocks mutation and old images stay stopped during camera recovery, with recordings and optional private legacy rollback material retained.
- [x] 4.5 Expose maintenance status in the UI and document explicit owner-specific crash recovery plus the reusable API for the future desktop wizard; verify stale markers block starts and cannot be cleared by an unrelated deployment. Keep the existing desktop-setup proposal unchanged.

## 5. Report legacy recording results honestly

- [x] 5.1 Classify spontaneous and stop-time legacy exit codes and forced termination before clearing handles; verify nonzero/timeout output is retained for recovery, reports an error and is absent from successful listings, while successful legacy capture retains its current filename and metadata.
- [x] 5.2 Update UI completion handling and `docs/multistream-recording.md` recovery guidance; verify both browser builds show failure rather than saved-recording success and the existing multistream finalization tests still pass.

## 6. Use browser downloads for real recordings

- [x] 6.1 Replace real-recording fetch/Blob buffering with a native download link using the existing validated file route; verify a download through an isolated real backend has the expected filename/content without the application's full-file fetch/Blob path.
- [x] 6.2 Retain demo downloads and byte-range playback; verify demo browser checks and real-file range/seek checks pass, and update frontend documentation only where behavior descriptions change.

## 7. Remove obsolete camera padding and correct installer guidance

- [x] 7.1 Repeat the whole-tree caller search and remove `pad_nv21`, `crop_encoder_padding` and `trim_padding` support; verify no production/config/test imports remain and current `maix/rtsp_av.py` still uses full-frame rotation without padding.
- [x] 7.2 Change the camera RTSP integration fixture from padded 512x640/cropped 480x640 to aligned 768x432; verify FFmpeg decodes two reconnect cycles and retain full Y/chroma rotation and packet reassembly checks.
- [x] 7.3 Correct PuTTY prerequisites/private-key instructions in `docs/docker-run-guide.md` to Windows OpenSSH; verify every cited script parameter exists and links agree with the root README, coordinating overlapping text with the pending desktop-setup work.

## 8. Verify integration and review scope

- [x] 8.1 Run `python -m unittest discover -s tests -v`, `npm test` in `frontend`, and `docker compose config --quiet`; verify no new failures and list every skipped check explicitly.
- [x] 8.2 Run the isolated multistream/headset media integration cases with their documented opt-ins and isolated fixtures; verify H.264 copy, four-track output, separate microphone return and talkback signaling without touching production ports/devices.
- [x] 8.3 Review the final diff against all three delta specs and `audit.md`; verify no unrelated rewrite, dependency additions, unrelated data changes or weakening of SCO startup/packet validation, and record results in a dated session note linked from AGENTS.md.

## Workflow follow-up

- Implementation begins only after a new explicit apply request; this proposal does not authorize production deployment.
- If live deployment is later requested, verify idle state and follow the recording-safe rollout/recovery design. Record picture, audible duplex and recording acceptance separately from automated checks; no physical timing claim follows from test success.
