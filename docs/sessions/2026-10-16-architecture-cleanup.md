# Architecture reference and reversible local cleanup — 2026-10-16

## Request and scope

The user reports that the current architecture works well. They requested a
written architecture, data-pipeline and protocol description, no code changes,
and safe removal of unused local files. The checkout already had extensive
tracked/untracked changes from prior work; those changes were preserved.

## Documentation

Added `docs/architecture.md`, editable `docs/architecture.mmd` and rendered
`docs/architecture.svg`. Linked the reference from README and the project index.
Inspected Compose, Dockerfile, MediaMTX configuration, supervisor, camera boot
template, camera media programs, PC relay/receiver/protocol, frontend media/data
integration and recording guide. The reference distinguishes selected Docker
TCP/video + independent RTP return + SCO duplex + multistream recording from
older UDP/combined, A2DP and legacy-recorder alternatives.

The diagram contains only component/protocol information, with no installation
addresses or credentials; it was submitted to Kroki for Mermaid validation and
SVG rendering. Rendering returned HTTP 200 and SVG content. No application or
camera runtime tests were needed for documentation-only changes.

## Cleanup and safety checks

Inspected Git status/ignored files and local generated directories. Each target
was resolved to an absolute path inside this workspace, checked for tracked
files and reparse points, and limited to an explicit allowlist. Permanent
`Remove-Item` cleanup was rejected by automatic approval review as blocked by
policy, with no further reason. No deletion occurred. Used reversible
`Move-Item` quarantine instead; checked both source and destination boundaries.

| Original location | Files | Bytes |
| --- | ---: | ---: |
| `__pycache__/` | 1 | 26,088 |
| `maix/__pycache__/` | 7 | 71,324 |
| `pc/__pycache__/` | 12 | 137,317 |
| `tests/__pycache__/` | 19 | 257,888 |
| `frontend/dist/` | 3 | 450,837 |
| `frontend/test-results/` | 4 | 632,633 |
| Total | 46 | 1,576,087 |

Files now live under `.runtime/cleanup-quarantine-2026-10-16/`, retaining their
relative paths, with `manifest.json` recording counts and sizes. This removes
the outputs from their working locations but does **not** reclaim disk space.
To restore one directory, move its quarantined copy back to the original path
only after checking that the original has not been regenerated.

Retained `.env`, `.talkback_token`, `recordings/`, all other `.runtime/` evidence,
`frontend/node_modules/`, `pc/operator_test.html`, local `mediamtx.exe`, screenshots,
diagnostic utilities, source files and pre-existing untracked work. Ignored or
old files were not assumed unused. Python caches/build/test outputs regenerate
when their respective tools run.

## Verification and final runtime state

SHA-256 comparison of existing tracked/untracked non-Markdown project files
verifies that source and configuration were not changed by this task. Checked
new document links, diagram output and quarantined file counts/sizes. No code
tests/builds were run, which also avoids recreating the removed outputs.

No deployment, Docker service restart, camera connection, Bluetooth operation or
recording action was performed. The runtime is unchanged by this task; its live
health and physical A/V synchronization were not newly measured. User feedback
that the architecture works well is recorded as user feedback.

## Commit and push follow-up

The user subsequently requested committing and pushing the pending changes.
Included the existing Docker/SCO deployment/defaults/cleanup changes together
with this architecture reference on `experiment/sco-duplex`, targeting `origin`.
Checked that private/generated paths were absent from additions and that staged
text did not contain the local pairing-token value. Its existing staged removal
from version control is included; the local token file remains on disk.

Validation before commit: `python -B -m unittest discover -s tests -v` ran 123
tests successfully with five expected skips; `docker compose config --quiet`
and `git diff --cached --check` passed. This follow-up performed no deployment
or service restart.
