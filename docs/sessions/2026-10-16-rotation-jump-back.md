# Rotation jumps back after repeated operations — 2026-10-16

User reported that 90-degree rotation stopped working after several operations,
then clarified that the view rotates and jumps back. This repair does not add
rotation during recording; the existing recording/finalization lock remains.

## Cause and changes

`refresh()` reads recording status (including rotation), Bluetooth status and
talkback availability concurrently, then applies all results after all requests
settle. A delayed Bluetooth request can hold an old camera angle until after a
new rotation has been saved. Applying that old result resets the displayed angle
while the server still holds the new selection.

Added a rotation revision ref in `frontend/src/main.tsx`. Status polls capture
the revision when they start; polls spanning a rotation operation cannot apply
stale camera/recording state. Incrementing at both operation start and completion
also covers polls launched while the save request is pending. Bluetooth and
talkback results continue to update normally.

Added a Playwright regression that delays Bluetooth status, performs four angle
changes ending at 90 degrees, releases the delayed poll and verifies the player
and selector remain at 90. The test failed before the fix with actual value 0,
then passed in source and compiled interfaces.

## Verification and deployment

- `npm test`: final clean run passed all 26 source/compiled checks and build/type
  checks. An earlier full run had one navigation timeout while a source
  formatting edit triggered Vite reload during the run; the clean rerun passed.
- `git diff --check -- frontend/src/main.tsx frontend/tests/ui.spec.ts`: passed.
- Initial indentation helper failed on Windows default text decoding before
  writing; rerun with explicit UTF-8 succeeded.
- Predeployment API: recording false, finalizing false, rotation 0, error null.
- `./deploy_pc.ps1 -Build`: Docker rebuilt/recreated healthy; Windows operator
  page HTTP check passed. Camera programs/processes were not changed.
- Existing unrelated working-tree edits retained. No new recordings created.
  Hardware audio quality and physical latency were not tested in this repair.
