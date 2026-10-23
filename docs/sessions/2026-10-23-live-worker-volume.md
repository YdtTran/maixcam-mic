# Earbud volume in Live Workers — 2026-10-23

User requested moving the adjustment onto the live worker page, associated with
its selected worker. This supersedes the Settings placement recorded in
[the initial volume implementation](2026-10-23-earbud-volume.md).

Moved the existing volume state, validation feedback and controls into a small
component in the selected physical worker's Actions card, below Talk/Record.
Removed the control from Settings. Worker selection remounts the control and
reads actual camera volume; demo workers do not render hardware controls.
The existing backend supports one physical camera, not independently routed
multiple physical workers. No backend or microphone changes were needed.
README now points to Live Workers.

## Verification and deployment

- `npm test --prefix frontend`: type-check/build and all 48 source/compiled
  browser checks passed, including applying volume, switching demo/real workers,
  Settings absence and unavailable mixer feedback.
- Elevated `deploy_pc.ps1 -Build -Recreate` completed successfully, exit 0;
  maintenance released. No camera restart or camera module deployment.
- Real browser at localhost:8000: selected physical worker initially read 100;
  applying 50 returned actual mixer step 53. Demo worker hid the control;
  returning to physical worker reloaded 53. Applying 100 restored the original
  level. Settings had no volume control. API readback confirmed final 100/TB3.
- Clear decoded live video visually verified after navigation; Docker healthy,
  headset connected, recording idle, rotation 0, maintenance null.
- `git diff --check` passed.

Ignored evidence: `.runtime/live-worker-volume-deploy.log`, exit marker,
`.runtime/live-worker-volume-ui.json`, `.runtime/live-worker-volume-live.png`.
An initial live diagnostic began before deployment maintenance finished and its
broad status locator matched both maintenance and toast messages. The helper
restored original volume in finally. After deployment exit 0, narrowed the
helper to the toast and the full live check passed. An early screenshot preceded
video decode; the final screenshot shows clear video.

Audible speech and reconnect/reboot volume persistence were not retested for
this UI move. Hardware remains limited to 100%; multiple physical-camera routing
is outside the existing single-camera backend.
