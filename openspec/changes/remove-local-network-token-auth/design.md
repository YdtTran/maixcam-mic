# Design

## Context

See `proposal.md` for the user decision and scope. The user explicitly chose token removal and deployment simplicity while retaining the admin login. This is a trusted-LAN, single-camera/single-operator-PC deployment.

Source inspection found one shared secret crossing five boundaries:

| Boundary | Current dependency | Planned change |
|---|---|---|
| PC startup | `app.py` and standalone operator instantiate control/talkback only when the token file exists | Always instantiate them from the configured camera address |
| Bluetooth HTTP | PC sends `X-Control-Token`; camera compares it before status/clock/scan/select | Remove the header, token arguments and authorization gate |
| Talkback UDP | TB2 header plus up to 320 PCM bytes and a 16-byte HMAC | TB3 header plus PCM; retain framing/timing/session checks |
| Camera startup | Bluetooth connector and receiver read `/root/.talkback_token` | Remove token CLI flags and reads |
| Deployment | Scripts create/check/upload token; Compose requires a read-only file mount | Remove active token handling and the mount; keep legacy recovery copies only when present |

The current scripts already stage payloads, back up old files, preserve recordings and verify media. `scripts/deploy.ps1` normally installs/reboots the camera before rebuilding the PC, so the migration must account for a brief incompatible-version interval. Existing status-only recording checks have an audit-reported race; implementing the full maintenance redesign is separate work and must not be claimed complete here.

The earlier interrupted implementation turn performed inspection only. No token removal or runtime change has happened.

## Goals / Non-Goals

**Goals:** Delete the shared application credential dependency throughout runtime/deployment/tests; make fresh and existing installations work without token preparation; keep the accepted audio/video behavior and recoverability.

**Non-Goals:** Removing SSH credentials, replacing network discovery, removing the admin login, opening PC ports to the LAN/internet, changing headset pairing, adding an authentication setting, solving the entire audit or introducing a desktop installer. The existing Origin check remains. No new dependencies are needed; HMAC/hash imports disappear from the packet path, while unrelated hashing and random session IDs remain.

## Decisions

### 1. Remove the dependency rather than add a token-free mode

Remove token arguments from `TalkbackRelay`, `TalkbackReceiver`, packet helpers and `CameraBluetoothClient`. Remove `--talkback-token` from both PC entry points and `--token` from both camera entry points. Instantiate the PC client/relay directly from the configured host, retaining `clock_sync=bluetooth.talkback_clock`.

Remove `X-Control-Token` production/verification and the camera handler's authorization helper. Preserve action allowlists, body limits, MAC validation and fixed-headset checks. Keep network errors, calibration timeouts and existing process cleanup visible.

A default secret, empty-token bypass or optional auth flag would leave the dependency surface in place and create extra states to deploy/test. Delete it instead. Obsolete token flags produce normal CLI unknown-argument errors; update every maintained caller and command in the same change.

### 2. Use a distinct TB3 marker with the existing header structure

Retain `struct.Struct("!3sBQIQ")`, a 24-byte network-order header:

| Field | Size |
|---|---:|
| Magic `TB3` | 3 bytes |
| Stop flag | 1 byte |
| Session | 8 bytes |
| Sequence | 4 bytes |
| UTC milliseconds | 8 bytes |
| PCM payload | 0 for stop, 2–320 even bytes for speech |

There is no signature trailer; maximum datagram length becomes 344 bytes. Reject wrong magic before accepting audio. Keep stop/body validation, the two-second timestamp window, the existing 40 ms reorder window, six-frame bound, stale-data dropping, retired-session logic, three stop transmissions and sender pacing. Retain random session IDs to distinguish consecutive sessions; randomness does not depend on a token file.

Do not reuse TB2 with a shorter body: an old signature could otherwise be treated as PCM. Do not replace the signature with a fixed key, checksum, SRTP or extra packet wrapper. The version change is sufficient for framing compatibility; token-free packets intentionally provide no sender authentication or tamper verification.

### 3. Detect compatibility using the existing camera control responses

Include the active talkback protocol version in camera status/clock responses. The PC calibration path and deployment verification require TB3 before claiming compatible talkback. Keep the existing endpoints; do not add a negotiation subsystem or silently fall back to TB2.

Remove the older-camera clock fallback for this release, since a receiver without the new protocol cannot accept the sender's packets. A mixed release returns a readable coordinated-update message rather than an apparent successful talkback session. Network unavailability remains a normal retryable camera error and does not become a token failure.

### 4. Remove active deployment handling, preserve recoverable old releases

Delete token generation/hex validation from `deploy_pc.ps1` and `deploy_maix.ps1`, remove the token preflight in `scripts/deploy.ps1`, remove new-payload upload/install entries and remove the Compose token bind mount. Keep the deployment stage count while changing its token wording to configuration validation. Existing no-token fixtures become the normal tests rather than manufacturing a token file.

Separate the existing camera backup list from the new install list where needed: optional legacy token files belong only in recovery snapshots, never in a new active payload. Preserve `.gitignore` protection for old token files/backups so an upgrade cannot accidentally commit legacy secrets.

The first migration captures the previous effective Compose configuration, image identity, camera payload and any existing token needed by that old release before mutation. Obtain the old container's settings/mounts from Docker inspection or an actual prior configuration snapshot; running `docker compose config` against the edited new file cannot recover the old mount. Store token material only in the existing private/ignored recovery location; never print its contents. Restoration must use that captured recovery configuration, including its legacy token mount. Using the new token-free Compose file with an old image is not a valid rollback.

If a legacy installation has no matching recoverable token, normal new-release deployment still proceeds without asking the customer to recreate one. Mark old-release talkback rollback as unavailable rather than claiming a complete recovery. Retain other recoverable settings/media and show an actionable result if rollback is needed.

After both new sides pass verification, the obsolete PC/camera active token files can be removed through explicit file paths; retain recovery copies. Do not delete them before a currently running old service is replaced. An ignored file left by an old installation is harmless to the new runtime, so removal failure must not reintroduce a startup prerequisite.

### 5. Coordinate activation and verify what actually works

Use the existing combined deployment path for the supported migration. Finish recording/finalization before mutation; keep the operator stopped during incompatible camera/PC activation where the current lifecycle permits. Treat intermediate loss of talkback as expected until both sides are updated. Do not claim that this change fixes the audit's separate concurrent-recording race.

Verify the camera's TB3 version/control responses, expected receiver process, matching installed protocol payload, PC startup without a token mount, actual video/headset-return decode and normal talkback signaling. Automated isolated media validation proves TB3 speech/stop delivery; a later live acceptance trial separately confirms audible speech. Stop/recovery behavior must retain existing SCO boot order and avoid duplicate capture/connector/player processes.

Individual PC-only or camera-only updates can produce an incompatible pair. Document that both must be updated and report the version mismatch. Add no long-lived dual-protocol compatibility layer.

### 6. Reconcile the pending plans without widening implementation scope

The latest user decision supersedes token-preservation statements in the two existing unimplemented changes. During application, update their proposal/design/spec/task text coherently:

- `harden-runtime-and-trim-obsolete-code`: defer its new local Host/Origin hardening work; change token/authenticated-TB2 preservation language to TB3 structure, timing and session preservation. Keep its reliability tasks and historical audit evidence.
- `add-guided-desktop-setup`: remove token adoption, mismatch blockers, synchronization and new-setup preservation requirements. Keep SSH verification, Wi-Fi credentials, fixed earbuds and recovery of an old release where legacy tokens exist. Replace new-PC token-adoption acceptance with no-token new-PC acceptance.

Do not mark unrelated tasks done, archive these plans, or implement their remaining work. This proposal explicitly records the conflict now; those earlier artifact sets are otherwise unchanged by this planning turn.

## Risks / Trade-offs

- LAN clients can send control/audio without an application credential → accepted by the user; retain current network exposure defaults and clearly describe the trusted-LAN assumption.
- Mixed PC/camera versions cannot talk → explicit TB3 check, a combined release and coordinated rollback; no misleading fallback.
- New Compose cannot run an old token-based image correctly → snapshot the old effective configuration and optional token for recovery before mutation.
- Legacy rollback material may already be missing → allow token-free deployment and distinguish partial/unsupported old-release recovery from verified full rollback.
- Removing token parameters touches many tests/callers → update direct imports, CLI fixtures and opt-in integrations, retaining malformed/stale/sequence/calibration tests.
- Ordinary authentication tests no longer apply → replace them with no-token startup/HTTP tests; do not retain assertions that altered PCM is cryptographically rejected.

## Migration Plan

1. Reconcile conflicting pending plan requirements and implement runtime/API/protocol changes with focused tests; leave admin login code alone.
2. Update scripts/Compose and their no-token/migration/rollback fixtures together. Update maintained docs and diagrams; preserve historical logs.
3. Run Python, browser and isolated media checks plus Compose validation from a fixture with no token. Do not touch the user's current active token during development.
4. Only if later authorized to deploy, use the combined workflow while idle; capture the old release, activate both new sides and verify compatibility plus media.
5. After acceptance remove obsolete active token files where safe, retaining private legacy recovery data. On failure restore the previous compatible pair and its captured configuration, reporting any missing legacy prerequisites honestly.
