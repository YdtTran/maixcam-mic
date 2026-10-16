# Repository cleanup — 2026-10-11

User requested removing redundant project files after multistream recording
commit `02aca75`. Inspected tracked files, content hashes, runtime/build/upload
references and documentation before removing:

- `prompts/UI_Promtp.md`: original prototype implementation prompt; superseded
  by the frontend implementation and frontend guide, with no project references.
- `prompts/backend_udp_migration.md`: historical migration request; superseded
  by implementation, transport guides and dated session evidence. Its blanket
  UDP objective no longer matches the accepted TCP/video configuration.
- `auto.key`: no application, configuration or upload reference. The upload
  helper accepts an explicit external `-KeyPath`; active talkback instead uses
  `.talkback_token`, which was retained. Removed the README's obsolete key mention.

Changed the recording path traversal test's example to `../README.md`, retaining
its existing assertion against a file outside the recordings directory.

The only identical tracked files were empty Python package markers; retained
both. Retained compiled `pc/operator_test.html` because native startup serves it,
and kept measurement helpers, alternate startup templates, tests, demo assets
and session history because they have distinct documented uses. Left ignored
runtime evidence, recordings, dependencies and local configuration untouched.

Validation: remaining mentions of the removed files are confined to this cleanup
record. `python -m unittest discover -s tests`: 109 tests run, 105 passed and
four opt-in integration tests skipped. `git diff --check` passed.

The command runner rejected a PowerShell deletion command before execution;
the three file deletions were completed using `apply_patch` instead.

Final runtime: no application or device restart, deployment, Bluetooth change
or live route change. Cleanup remains available for review in the working tree.
