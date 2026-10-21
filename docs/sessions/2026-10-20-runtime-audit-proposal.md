# Runtime audit and OpenSpec proposal — 2026-10-20

## Request and boundary

User requested `ponytail-audit` of the whole project and an `openspec-propose` solution. Work was read-only for application code and runtime. Only planning artifacts, this session note and the project index were authored. Existing untracked `.agents/` and `openspec/changes/add-guided-desktop-setup` were preserved.

## Result

Created [harden-runtime-and-trim-obsolete-code](../../openspec/changes/harden-runtime-and-trim-obsolete-code/proposal.md): proposal, three capability delta specs, design, tasks and an [eight-finding audit](../../openspec/changes/harden-runtime-and-trim-obsolete-code/audit.md).

The audit assumes one prepared camera, one Windows PC and one operator with potentially multiple tabs. Priorities are local HTTP authority validation, exclusion between recording and deployment, talkback cleanup, optional metadata resilience and honest legacy-recording outcomes. Smaller changes replace whole-file download buffering, retire camera padding/SPS code used only by an old fixture, and correct stale PuTTY installer instructions.

The proposal preserves TCP/video, independent UDP8004 return, SCO setup, clock calibration, packet authentication, fixed headset identity, tokens, recordings and current rotation. It adds no dependencies and does not replace the working pipeline. The pending desktop wizard remains separate and must reuse the maintenance contract when implemented.

## Verification and evidence

- `python -m unittest discover -s tests -v`: 141 run, 135 passed, six skipped, exit 0.
- `npm test` in `frontend/`: TypeScript/build/package succeeded; all 30 source/compiled browser checks passed. Ignored build/test artifacts were refreshed.
- `docker compose config --quiet`: passed, without starting or rebuilding services.
- Temporary files reproduced a startup `JSONDecodeError` from invalid camera-view JSON and an uncaught recording-list `AttributeError` from array metadata.
- An ephemeral loopback HTTP server accepted matching foreign Host/Origin and changed only temporary rotation state; no production service was contacted.
- A mocked failed talkback decoder left relay ownership set; the next offer was rejected as already active.
- A mocked legacy recorder exiting 1 left nonempty failed output listed as saved without an error.
- Deployment's race follows the source sequence from status check to later mutation and direct rollback. It was not reproduced by interrupting live capture.
- Whole-tree reference search showed no caller for `pad_nv21` and only a historical-format test caller for padding/SPS cropping. Long-download overhead follows the complete response-to-Blob path; browser RAM usage was not measured.
- `openspec status --change harden-runtime-and-trim-obsolete-code`: all four artifact groups complete.
- `openspec validate harden-runtime-and-trim-obsolete-code --strict`: passed.

## Limits and final runtime state

No source fixes, camera SSH operations, image builds, restarts or production recordings were performed. Live camera/headset state was not queried and is unknown for this session. Audible duplex, physical latency/A/V synchronization, long-load behavior, a full browser rebinding exploit, external dependency advisories and the six skipped checks remain unverified. The request authorizes planning only; implementation awaits a new apply request.
