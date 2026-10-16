# Dark camera video recovery — 2026-10-16

User reported black streaming video after portrait redeployment and confirmed
the lens was uncovered and pointed at a lit scene.

## Evidence and actions

- Docker remained healthy; WebRTC readers connected and decoded 480×640 frames.
- Direct camera RTSP snapshots showed the same dark purple sensor noise as the
  browser. This isolated the visible fault upstream of browser rotation.
- Earlier deployment verification established decoding/dimensions but did not
  establish a usable camera scene; its initial screenshot also contained noise.
- Temporarily restored the backed-up 640×480 camera program and rebooted.
  Direct snapshot then showed ceiling tiles and a lit panel clearly.
- Restored the unchanged requested 480×640 camera program and rebooted again.
  Direct snapshots and browser now show a clear scene at portrait resolution.
  Therefore portrait resolution alone does not consistently reproduce the fault.
  Transient sensor/ISP initialization failure is a hypothesis, not proven cause.
- No permanent source changes were needed for recovery; both installed camera
  copies again match the repository's 480×640 program. Existing web layout and
  clockwise live rotation remain deployed. PC container was not restarted.
- One FFmpeg invocation rejected `rw_timeout`; reran without that option.
  Checks launched while the camera rebooted could time out or wait indefinitely;
  subsequent captures used Python subprocess timeouts. Stopped the known local
  stale FFmpeg check process after recovery.

## Final verification (approximately 10:04 local)

- Inspected direct portrait snapshot and Chromium screenshot: clear ceiling scene
  and light panel; no longer dark sensor noise.
- Real Chromium decodes 480×640, advances playback, applies clockwise matrix,
  and matches the existing player's bounds with object-fit contain.
- Five-second decoded RTSP sample succeeded. First sampled frame luminance
  YAVG 122.244, range 0–255, compared with dark sample YAVG 57.7193, range 37–93.
  These describe sampled images, not a general image-quality acceptance threshold.
- Docker remains healthy; camera reports connected eSCO and ACL headset links.
  Audible audio and prolonged repeat-boot stability were not tested.
- Evidence in ignored `.runtime/`: `portrait-camera-black-check.png`,
  `landscape-camera-black-check.png`, `portrait-camera-retest2.png`,
  `portrait-live-20261016.png`, and both signalstats files.
- Exact cause and recurrence risk remain unresolved. No new commits.
