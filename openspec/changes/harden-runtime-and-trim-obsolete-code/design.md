# Design

## Context

See `proposal.md` for motivation and `audit.md` for evidence. Expected load is one prepared camera, one Windows operator PC and one person, potentially with multiple browser tabs. Docker is the customer runtime; standalone Python and legacy/A2DP remain explicit compatibility paths.

`RecordingManager` already has an RLock and central start/stop handling. Deployment scripts check recording status but leave it possible to start recording between that check and mutation. `TalkbackRelay` already serializes browser control but worker failure does not release `location`. Persisted rotation is atomically written but read without validation recovery. The active camera encoder emits aligned 768x432 frames; padding/SPS rewriting exists only for a retired configuration and its test fixture.

There are no main OpenSpec specs. The separate `add-guided-desktop-setup` change is still a plan, not current implementation. Do not edit its artifacts in this change; document the maintenance API it must consume.

## Goals / Non-Goals

**Goals:** Repair failures in the existing owners of each behavior, preserve data and accepted media behavior, and add small failure/race regressions. Keep changes independently reviewable and introduce no dependencies.

**Non-Goals:** A service framework, generic repositories, multi-PC coordination, login/session infrastructure, automatic media recovery, React component decomposition by size, or replacement of the camera RTSP server. Additional Host/Origin hardening is deferred.

## Decisions

### 1. Preserve the existing local boundary

The later `remove-local-network-token-auth` decision defers additional Host/Origin hardening. Retain the existing operator Origin check, loopback publication and prototype login. Do not add new authority guards in this change.

### 2. Make maintenance an operation, not a status snapshot

Extend `RecordingManager` with begin/end maintenance operations, using the same RLock as recording start. Begin atomically refuses capture/finalization and writes a small owner marker under the existing recordings bind mount. Start checks that marker under the lock, including after a container restart. End only removes the matching owner's marker. Expose maintenance status and a clear rejection to the UI; read/list/playback remain usable. Keep user recording metadata separate from this marker.

Use one project-scoped host lock for mutating Windows entry points, with an operation ID shared through nested project-script calls. The outermost caller owns release. Acquire maintenance before the first camera/PC mutation and hold it through build, reboot, health checks, return-audio recovery and rollback. Direct PC stop/update, combined deployment and standalone local camera deployment use the same helper/contract. A stopped/nonexistent operator permits host-side marker creation only after the existing container/native-listener checks prove no local capture can be running. An unresponsive running operator blocks mutation.

Persist exclusion because a purely in-memory flag disappears on container replacement. Reject a competing owner instead of adding a job queue. Leave the marker after a crash or unverified rollback, with an explicit documented recovery action that verifies idle state and requires the recorded owner. Do not automatically expire it by elapsed time. Dry-run/check-only paths stay read-only. Local maintenance cannot protect a different operator PC; retain the current requirement to stop the old PC before migration.

The host lock also covers direct script execution and rollback. Tests must prove a record request races either before acquisition (deployment refused) or after it (recording refused), and never succeeds during maintenance. Merely adding another status check is insufficient.

### 3. Retire failed talkback sessions by their own identity

Capture session identity, cancellation event and relay location when workers are created. Route decoder failure and media disappearance through idempotent cleanup for that identity. Detach state under the existing locks, then terminate/join/delete outside locks that workers need. Never join the current worker. Keep cleanup bounded using the existing decoder/HTTP timeouts and make failure diagnostics survive cleanup.

A retry is admitted after old ownership has been released. A late old worker must use the old session's stop identity and cannot read `self.session` to construct a stop for the new one. Apply the same identity checks to late browser Stop. Cover lost Stop, failed spawn and delayed worker cleanup; do not rely on browser unload handlers. Keep calibration, sequence handling and bounded queues unchanged.

### 4. Treat optional JSON as fallible input

Read and validate optional view/recording metadata in narrow exception boundaries. Check object shape before accessing keys; reject invalid rotations, wrong types and nonfinite duration values. Default view rotation to zero and duration to unknown, preserving valid metadata behavior. Preserve invalid files and expose a separate actionable warning so a metadata warning cannot masquerade as a capture failure. Clear or acknowledge the warning after a valid replacement is saved. Keep atomic rotation writes and avoid a general settings framework.

### 5. Keep failed legacy recordings out of the success list

Classify process exit in both explicit stop and spontaneous `_refresh` before clearing the process handle. A forced kill or nonzero exit records an error and retains output under an ID-associated failed/recovery filename excluded by the existing successful-recording filter. Do not write success metadata merely because bytes exist. Keep successful legacy MP4 names and old successful files unchanged. The UI must display the retained failure instead of announcing success; add a source/compiled browser case for it.

### 6. Reuse native browser downloads

For same-origin real recordings use a link with the existing recording URL and download filename. Add an explicit validated download query/header response only if needed to ensure browser behavior, while retaining range playback. Preserve the separate demo Blob/data-URL behavior as needed. Do not add a download SDK or streaming proxy. Test a real backend file route and filename; mocked data-URL downloads alone do not verify this path.

### 7. Delete the retired padding path and replace its fixture

Remove `pad_nv21`, `crop_encoder_padding`, and the `trim_padding` constructor/branch after a fresh whole-tree caller check. `pad_nv21` has no caller; cropping is invoked only by `tests/test_camera_rotation.py`. Generate an aligned 768x432 fixture and retain exact pixel rotation, H.264 fragmentation, TCP decoding and reconnect coverage. Historical session documents remain historical; do not rewrite them. Removal saves roughly 75 production lines, but net savings depend on regression tests and maintenance logic.

Correct the PuTTY prerequisites and key-format guidance in `docs/docker-run-guide.md` using the current OpenSSH helper and README. The desktop-setup proposal already calls for that correction: whichever change lands second must reuse the updated text without reverting it.

## Risks / Trade-offs

- Persistent maintenance can remain after a crash → fail closed with owner-specific recovery instructions; test that stale/foreign owners cannot release it.
- Old released images do not understand the new marker → the first upgrade must stop the old operator and build the replacement before camera mutation, then acquire the new API guard; rollback to an old image keeps it stopped until all camera changes finish. Verify idle status before that stop, and do not advertise the old version as race-safe during bootstrap.
- Worker cleanup can deadlock or stop new speech → never perform blocking joins/network calls under shared state locks; test cleanup/retry interleavings and old-session packets.
- Fallback metadata can hide storage trouble → preserve the original file, warn clearly and keep actual read/write failures visible.
- Native downloads differ for demo URLs → retain the existing demo path where necessary and test real file downloads separately.
- Camera fixture change can weaken old coverage → retain actual FFmpeg decode/reconnect and full-plane rotation checks on the current baseline; hardware testing remains a separate acceptance step.

## Migration Plan

1. Implement persistence and talkback repairs with focused failure regressions.
2. Implement the maintenance contract and migrate all mutating entry points together, including first-upgrade and rollback behavior. Publish the contract for the desktop wizard before its implementation starts.
3. Fix legacy outcome reporting and native downloads; remove retired camera padding and correct installer documentation.
4. Run Python and source/compiled browser suites plus isolated media tests. No production device is needed to prove the audit reproductions.
5. Deploy later only within separately authorized apply/deployment scope, while idle. Preserve `.env`, optional private legacy recovery material, recordings and camera backups. Verify camera video, independent return and talkback plus a short recording; audible acceptance and physical timing remain explicitly separate.
6. On failure keep maintenance active during rollback and do not claim recovery until the prior configuration is verified. If reverting to a pre-marker image, keep that operator stopped throughout camera recovery and only release it after mutation is finished.
