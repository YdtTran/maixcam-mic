# Token removal implementation — 2026-10-20



## Request and scope



User explicitly applied `remove-local-network-token-auth`, then requested that

remaining tests run after implementation to check consistency. Earlier focused

checks ran before that steering; subsequent verification is one final phase.

No deployment, camera SSH operation, production build/restart or active token

deletion is authorized or performed by this apply request.



## Changes



- Reconciled the two pending plans without completing their unrelated tasks;

  historical audit evidence retained and additional Host/Origin hardening deferred.

- Replaced signed TB2 with token-free TB3: 24-byte header, 344-byte maximum,

  same PCM/session/sequence/stop/freshness/jitter/pacing and audio lifecycle.

- Removed token runtime flags/arguments/reads and Bluetooth token headers/checks.

  Both PC entry points always configure control/talkback with camera calibration.

  Camera status/clock identify TB3; incompatible calibration requires a paired update.

- Removed active deployment generation/validation/upload/mount. Camera backup

  lists retain optional legacy recovery material separately from installation.

- Combined deployment captures the actual old container configuration/image,

  preserves optional legacy material privately, checks matching recoverability,

  stops the old PC before camera activation, verifies TB3 plus real media/control,

  and attempts compatible-pair rollback using the captured configuration.

  Missing/malformed/mismatched legacy material permits the new release and

  explicitly prevents claims of complete old-release talkback recovery.

- Active legacy token cleanup runs only after new-pair/media verification and

  warns on failure; no recordings, SSH keys or Bluetooth bonds are removed.

- Updated maintained guides and diagram labels; dated deployment history retained.

  Isolated fixtures validate real WHIP speech/stop through the TB3 receiver.



## Verification



Final verification after all implementation edits:



- `python -m unittest discover -s tests -v`: 147 checks, 141 passed and six

  skipped; final log `.runtime/token-python-tests-final.log`.

- `npm test` in `frontend`: build/type checks and all 30 source/compiled browser

  tests passed, including login, recording/finalization, rotation and playback.

- `docker compose config --quiet`: passed. A captured legacy rollback Compose

  fixture also passed real Compose configuration validation with its saved mount.

- `HEADSET_INTEGRATION=1 MULTISTREAM_INTEGRATION=1` isolated tests: three passed.

  Real Chromium received independent PCMU return and H.264, actual WHIP packets

  passed the TB3 receiver, stop was accepted, video remained after return loss,

  and legacy/four-track recordings decoded with copied H.264 preserved.

- `UDP_INTEGRATION=1` with a separately owned local MediaMTX fixture: passed

  with RTSP UDP (174 accepted PCM frames) and TCP (153), accepted stop, actual

  WHEP/WHIP and playable MP4. Fixture listeners were checked free first; only

  the process started for this run was stopped. No production ports/devices used.

- All three affected changes passed strict OpenSpec validation. Unrelated

  pending task checkboxes remain unchecked. `git diff --check` passed.

- Read-only Docker mount metadata confirmed the existing container exposes

  Windows bind paths suitable for the recovery snapshot; no token contents were

  displayed and no container state changed.

- Both PC and both camera entry-point help outputs contain no token flag.

  Maintained-source searches show no runtime shared-secret/HMAC/header path;

  remaining legacy references belong to recovery, cleanup, rejection tests,

  migration documentation or explicitly historical evidence. Session randomness

  and deployment file hashes remain unrelated to authentication.



Default-suite skips, each accounted for:



1. Full camera Y/chroma rotation: NumPy unavailable in this Python runtime;

   camera rotation code was not changed.

2. POSIX boot retry shell: Windows host; startup template was not changed.

3. Headset integration: opt-in; separately run and passed.

4. Multistream correlated full-scale voices: opt-in; separately run and passed.

5. Multistream late inputs/gaps/two sessions: opt-in; separately run and passed.

6. UDP integration: opt-in; separately run and passed for UDP and TCP.



Earlier focused development runs caught a remaining obsolete `--token` fixture

and a too-broad filesystem mock; both test fixtures were corrected. Final runs

have no failures. No package/lockfile changes. Raw logs and screenshots are in

ignored `.runtime/`; generated UI/build output remains ignored.



## Runtime and limitations

After implementation, the user clarified the project completion principle:
tests are supplementary; completion requires the real system to run after
redeployment. The source tasks above are implemented and checked, but overall
operational completion remains pending redeployment and running-system
verification. This documentation update does not itself redeploy the system.



Production services and active token files remain unchanged. Automated synthetic

media checks do not establish audible speech or physical latency. New TB3 camera

control/audio intentionally has no sender authentication on the trusted LAN.

The separately planned concurrent-recording maintenance race is not fixed here;

finish recording and do not start another during deployment. No dependencies,

frontend login rewrite, extra authentication switch or new access guard added.


## Later live verification

The subsequent "Verify it" request authorized actual paired redeployment.
See [live verification](2026-10-20-token-free-live-verification.md) for observed
media failures, recovery and final runtime state. The earlier automated results
above do not establish operational completion.
