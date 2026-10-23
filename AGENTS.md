# Project Brain and Index

Read this file first when resuming work. It records current decisions and points
to detailed evidence; session logs preserve the history. Last updated: 2026-10-23.

## Current State and User Decisions

- **Playback volume removed (2026-10-23):** User requested removal of
  `Earbud playback volume`; PC→MaixCAM Talk should send normally. Removed its
  UI/API/mixer handler and simplified the retained microphone control. Camera
  connector updated, PC rebuilt; 52 focused Python and 50 browser checks
  passed. Real UI absence, retired API 404, 15-second video/mic continuity and
  Talk signaling passed. Docker healthy, headset connected, maintenance clear.
  See [removal evidence](docs/sessions/2026-10-23-remove-earbud-playback-volume.md).

- **Working microphone volume control (2026-10-23):** User clarified that
  setting 0 must silence MaixCAM mic on the laptop; the old slider controlled
  earbud playback. Added a separate Live Workers microphone control with
  persistent camera-side software scaling: 0 sends silence, 100 retains +50%
  gain. Camera modules and PC rebuilt/deployed; 225 Python tests ran (eight
  skips), 52 browser checks passed. Real browser zero/nonzero measurements and
  a controlled all-silent worker/mixed recording passed. Maintenance released;
  mic returned to 100. For mute verification or competing browser writes, read
  [microphone volume evidence](docs/sessions/2026-10-23-earbud-microphone-volume.md).

- **Earbud microphone gain (2026-10-23):** User confirmed the system works and
  requested roughly 50% louder earbud capture. Added fixed 1.5 PCM gain with
  S16 saturation before RTP/RTSP encoding; deployed only the camera microphone
  sender. 25 focused tests and 15-second real browser video/audio continuity
  passed; Docker healthy, headset connected, maintenance released. Audible
  comparison pending. For gain/clipping or redeployment, read the
  [capture gain evidence](docs/sessions/2026-10-23-earbud-capture-gain.md).

- **Single fresh-install entry point (2026-10-23):** Only `scripts/deploy.ps1`
  remains executable. Camera install, PC build and safe stop moved into
  `scripts/NetworkDeployment.psm1`; component/wrapper/recovery scripts removed.
  README now documents one fresh-install command. Authorized full reinstall on
  iPhoneYdt passed after fixing optional `finalizing` access under module strict
  mode; 222 Python tests ran (eight skips). Real browser rotation, Talk signaling,
  recording/playback/download and 60-second video/audio continuity passed.
  Docker healthy, headset connected, recording idle, rotation zero, maintenance
  released; audible user acceptance pending. See
  [scope and verification](docs/sessions/2026-10-23-single-fresh-install.md).

- **iPhone hotspot recovery (2026-10-23):** Unused `n8n_default` reserved
  172.20.0.0/16 and blocked Docker access to camera 172.20.10.7. Removed the
  empty network after saving inspection. One safe PC stop/start restored host
  UDP8004. Browser video/audio continuity passed for 15 seconds; Docker healthy,
  headset connected, maintenance released. Added deployment subnet checks.
  Read [cause and limits](docs/sessions/2026-10-23-iphone-wifi-docker-route.md)
  before restarting n8n or diagnosing hotspot startup.

- **Hard-fresh deployment (2026-10-23):** User now prioritizes full reinstall
  over saved application settings/backups. `scripts/deploy.ps1` and `run_all.ps1`
  require SSID/headset MAC, stop all running Docker containers on the current
  engine, reset WorkerCam settings, reinstall/reboot camera and rebuild PC
  without cache. No application rollback. Two real deployments passed; second
  started without camera `workercam.env`. User confirmed audible duplex.
  For fresh-install prerequisites, reruns or verification limits, read the
  [deployment evidence](docs/sessions/2026-10-23-hard-fresh-reinstall.md).

- **Live worker volume placement (2026-10-23):** Moved earbud playback volume
  from Settings to the selected physical worker's Live Workers Actions card.
  Demo workers cannot change the camera mixer; returning to the physical worker
  reloads actual volume. All 48 source/compiled browser checks passed. Elevated
  PC-only rebuild/redeployment succeeded; real UI/mixer 100→53→100 and clear
  live video verified. Docker healthy, headset connected, recording idle,
  maintenance released. See [placement and live evidence](docs/sessions/2026-10-23-live-worker-volume.md).

- **Earbud playback volume (2026-10-23):** User confirmed the microphone issue
  was resolved and requested louder/adjustable MaixCAM earbuds. Hardware was
  already at 100%. Added Settings volume control (0–100%) through bounded PC/
  camera APIs, targeting only the selected earbud playback mixer. Deployed the
  camera control modules with a scoped connector restart and rebuilt PC; actual
  UI/mixer changes and final 100% passed. Capture volume and working Talk input
  retained. See [volume implementation and live evidence](docs/sessions/2026-10-23-earbud-volume.md).

- **Elevated live deployment (2026-10-23):** User authorized real deployment.
  Root/root SSH passed over USB/Wi-Fi without a host-key prompt or mismatch.
  Fixed a proven elevated-launch working-directory bug in the shared child
  process helper; four focused checks passed. Paired forced deployment passed,
  including camera reboot/shared SSID, firewall, media, browser rotation,
  recording/playback/download and 60-second continuity. Follow-up isolated silent
  Talk to the PC's default Realtek microphone; user selected SOUNDPEATS, its
  Windows communications input. Talk now requests that input explicitly with
  default fallback when unavailable; PC rebuilt healthy. User confirmed laptop
  listening and audible Talk speech. Final rotation 0, recording idle,
  maintenance released; no Bluetooth reset or re-pairing performed.
  Before further recovery, read the
  [live deployment evidence](docs/sessions/2026-10-23-elevated-live-deployment.md).

- **Automatic camera login (2026-10-23):** User guarantees standard root/root
  camera SSH credentials. Deployment supplies them automatically, ignores stale
  saved credentials by default and enrolls first-time SSH host keys without a
  prompt; changed keys still fail. Wi-Fi password input remains separate.
  For implementation and verification limits, read the
  [automatic login session](docs/sessions/2026-10-23-automatic-camera-login.md).
  Implemented; redeployment verification pending. No live services changed.

- **Required shared Wi-Fi setup (2026-10-23):** Camera setup now requires
  `-WifiSsid` matching the PC's connected Wi-Fi. Supplied `-WifiPassword` enables
  switching MaixCAM over USB, persistent boot configuration and IP rediscovery.
  Setup reports/preserves the camera Wi-Fi MAC and checks SSID again after reboot.
  For command examples, password handling and recovery limits, read the
  [shared Wi-Fi setup session](docs/sessions/2026-10-23-required-shared-wifi.md).
  Implemented; redeployment verification pending. No live network changes.

- **Deployment firewall setup (2026-10-23):** Deployment entry points now require
  administrator PowerShell. Automatic deployment refreshes inbound UDP 8004/8005
  for the discovered camera Wi-Fi IP; PC deployment uses the Compose camera IP.
  Dry run/preflight remain read-only. For missing `/headsetmic`, changing camera
  addresses and verification limits, read the
  [firewall implementation session](docs/sessions/2026-10-23-deployment-firewall.md).
  Implemented; redeployment verification pending. No live firewall or service changes.

- **Final hardening redeployment (2026-10-21):** User authorized both devices.
  Maintenance-safe forced deployment succeeded on camera 192.168.1.7 and PC
  192.168.1.4; configuration unchanged. Clear 0/90 video, Talk signaling,
  recording/portrait playback/seeking, native download with matching SHA256,
  byte range and 60-second continuity (~20fps, zero reported loss) passed.
  Docker healthy, rotation zero, recording idle and maintenance released.
  Headset remained disconnected and return decode was silence; audible duplex
  acceptance remains pending. No archival; rollback defect remains. See
  [rollout evidence and limits](docs/sessions/2026-10-21-hardening-final-redeployment.md).

- **Hardening remaining tasks (2026-10-21):** Completed sections 6–8 of
  `harden-runtime-and-trim-obsolete-code` (22/22 implementation tasks): native
  recording downloads, removal of retired camera padding and verified OpenSSH
  guidance. Python: 198 passed, eight skipped; 44 browser checks passed, plus
  isolated media, Linux boot and camera rotation checks. Implemented;
  redeployment verification pending. Before rollout, archival or reviewing
  skipped checks, read the [results and limits](docs/sessions/2026-10-21-hardening-remaining-tasks.md).

- **P526 paired redeployment and duplex accepted (2026-10-21):** User requested
  P526_5G and reported only PC-to-camera audio working. Persisted camera Wi-Fi
  across reboot; redeployed both devices with camera 192.168.1.7 and PC/return
  destination 192.168.1.4. Headset initially disconnected, then reconnected;
  user confirmed both directions working. Docker healthy; real 60-second browser
  continuity ~20fps, zero reported loss; return decode contains microphone data.
  Final rotation 0, recording idle, maintenance released. Earlier hardening
  rollout passed rotation/Talk/recording/playback, 198 Python checks (eight skips)
  and 42 browser checks after a test-only HTTP mock correction. Rollback's known
  port-format defect remains. Before further rollout/recovery, read the
  [network, deployment and acceptance evidence](docs/sessions/2026-10-21-p526-redeployment.md).

- **Legacy recording section 5 (2026-10-21):** Implemented tasks 5.1–5.2 of
  `harden-runtime-and-trim-obsolete-code` (14/22 tasks). Failed/forced legacy
  output is retained outside successful listings; API/UI report failure.
  Final Python: 198 passed, eight skipped; all 42 browser checks passed.
  Implemented; redeployment verification pending. Before legacy recovery or
  rollout, read the [results and verification limits](docs/sessions/2026-10-21-legacy-recording-results.md).

- **Recording maintenance section 4 (2026-10-21):** Implemented tasks 4.1–4.5
  of `harden-runtime-and-trim-obsolete-code` (12/22 tasks). Persistent owner-bound
  maintenance excludes capture across all five deployment/stop entry points;
  nested calls share a host lock. Failed operations retain the marker; rollback
  restores previous images stopped for explicit recovery. Python ran 199 tests
  with eight skips; final Windows checks and all 36 browser checks passed.
  Implemented; redeployment verification pending. Before maintenance recovery,
  legacy bootstrap or rollout, read the
  [maintenance evidence and limits](docs/sessions/2026-10-21-recording-maintenance-exclusion.md).

- **Optional metadata section 3 (2026-10-21):** Implemented tasks 3.1–3.3 of
  `harden-runtime-and-trim-obsolete-code` (7/22 tasks). Invalid view JSON falls
  back to rotation zero; bad sidecars retain listed media with unknown duration.
  Separate status/UI warnings provide recovery guidance. Python ran 189 tests
  with eight skips; final focused checks and all 34 browser checks passed.
  Implemented; redeployment verification pending. For recovery, skipped checks
  and verification limits, read the
  [metadata isolation session](docs/sessions/2026-10-21-optional-metadata-isolation.md).

- **Talkback recovery sections 1–2 (2026-10-21):** Preserved local access
  defaults and implemented identity-bound, idempotent failed-session cleanup
  for `harden-runtime-and-trim-obsolete-code` (4/22 tasks). Retry no longer
  needs the old browser's Stop; delayed cleanup cannot stop a new session.
  Implemented; redeployment verification pending. For regressions, skipped
  checks and rollout limits, read the
  [session recovery evidence](docs/sessions/2026-10-21-talkback-session-recovery.md).

- **Efficiency paired redeployment verified with limits (2026-10-21):** User
  authorized both devices and SSH setup of `HCMUT-MEETING`. Fixed a proven
  native-startup regression: launcher passes `auto_start`, now accepted/tested.
  Saved Wi-Fi in `/boot` so reboot retains it. Final forced deployment passed;
  Docker healthy, native RTSP 768x432/20fps, no camera FFmpeg/OpenCV/NumPy.
  Real browser 60-second continuity (~19.8fps, zero reported packet loss),
  headset return, TB3 Talk, 0/90 rotation and multistream recording/playback
  passed. User confirmed both audio directions audible. Python rerun: 180 tests,
  eight skips. Final rotation 0, recording idle. Performance is qualified:
  final CPU idle 17–23% (below 55–65% target), 0% I/O wait, ~97MiB video VSZ;
  FFmpeg recording decode emitted timestamp warnings despite clear playback.
  Earlier failed deployment also exposed unresolved rollback port-format error;
  snapshots retained. No archival or long-stability claim. See
  [deployment evidence and remaining limits](docs/sessions/2026-10-21-efficiency-redeployment.md).

- **Automated regression section 4 (2026-10-21):** Required checks for
  `optimize-maixcam-cpu-and-video-transport` passed: Python ran 179 tests with
  eight skips, all 32 source/compiled browser tests passed after the frontend
  build, and Compose validation passed. Task 4.1 checked; tracked progress 6/6.
  No application changes or deployment. Implemented; redeployment verification
  pending, including live continuity and audio acceptance. See
  [regression evidence and limits](docs/sessions/2026-10-21-automated-regression.md).

- **In-process headset return section 3 (2026-10-21):** Implemented tasks
  3.1–3.2 of `optimize-maixcam-cpu-and-video-transport`: camera direct UDP8004
  PCMU encoding/packetization now runs in-process; explicit RTSP audio retains
  FFmpeg. Added best-effort console printk/Wi-Fi power-save boot tuning before
  SCO preparation. Focused sender/deployment checks and isolated Linux boot
  checks passed; full Python suite ran 178 tests with eight skips, plus one
  additional retry test passed. OpenSpec progress 5/6; section 4 remains pending.
  Implemented; redeployment verification pending. No hardware performance or
  audible improvement claimed. See [evidence and limits](docs/sessions/2026-10-21-in-process-headset-return.md).

- **PC baseline orientation section 2 (2026-10-21):** Implemented task 2.1 of
  `optimize-maixcam-cpu-and-video-transport`: optional `CAMERA_BASE_ROTATION`
  combines with the saved manager angle for live display and copied-H.264 MP4
  rotation. Manager selection persists independently. 170 Python tests ran
  successfully (seven skips); 32 browser checks and Compose validation passed.
  OpenSpec progress 3/6. Implemented; redeployment verification pending.
  See [configuration and evidence](docs/sessions/2026-10-21-pc-baseline-orientation.md).

- **Camera efficiency section 1 (2026-10-21):** User selected only tasks 1.1–1.2
  of `optimize-maixcam-cpu-and-video-transport`. Added default native-bound
  768x432/20fps RTSP and opt-in Python fallback with reusable rotation buffers,
  NAL views and blocking queue waits. Native mode removes camera pixel rotation;
  the separate PC baseline-offset task remains pending. No live deployment;
  operational verification remains pending. See
  [implementation evidence](docs/sessions/2026-10-21-camera-pipeline-section-one.md).

- **Token-free live verification (2026-10-20):** User authorized paired
  redeployment to verify operational completion. Both sides now run TB3; real
  login, video, headset return, Talk, rotation and a new recording/playback passed
  short checks. User confirmed audible PC-to-headset speech. Follow-up sustained
  video froze; a scoped video restart then failed with a camera read timeout.
  Normal reboot restored service and a final 30-second browser check passed
  (370 decoded frames); headset return and Talk were available, rotation 0 and
  recording idle. The intermittent camera fault remains unresolved, so overall
  acceptance is qualified. See
  [live deployment evidence](docs/sessions/2026-10-20-token-free-live-verification.md)
  for recovery actions and the actual final runtime state. Tests do not override
  this live failure.

- **Completion principle (2026-10-20):** The user defines completion by the
  system running successfully after redeployment. Automated tests are supporting
  diagnostics, not proof of completion. Apply the completion rule below.

- **Token removal implementation (2026-10-20):** Applied
  `remove-local-network-token-auth`: token-free TB3 runtime/control, paired
  deployment and inspected old-runtime recovery snapshots; admin login retained.
  Source implementation is ready; the later authorized live deployment is
  recorded above. Operational completion awaits reliable video verification.
  Verification results and remaining limits are recorded in the
  [implementation session](docs/sessions/2026-10-20-token-removal-implementation.md).
  No live deployment is part of this apply request. The two pending plans now
  follow this decision and defer additional Host/Origin hardening. The original
  [proposal session](docs/sessions/2026-10-20-token-removal-proposal.md) remains
  historical evidence.

- **Runtime audit and repair proposal (2026-10-20):** User requested a whole-repo
  audit and OpenSpec solution. Eight concrete findings and the validated
  `harden-runtime-and-trim-obsolete-code` plan are ready; implementation has not
  started. For the findings, scope and verification limits, read the
  [audit/proposal session](docs/sessions/2026-10-20-runtime-audit-proposal.md).
  Application code and live services were unchanged; preserve the separate
  pending desktop-setup proposal.

- **Nontechnical Windows README (2026-10-17):** User requested self-service
  redeployment instructions with PowerShell bypass included. Root README now
  leads with USB-first automatic deployment, explains laptop/password setup,
  preserves camera pairing and recordings, and provides picture/audio checks
  and recovery. All script examples use per-run `-ExecutionPolicy Bypass`.
  Local links and PowerShell example syntax checked; no live services changed.
  See [documentation session](docs/sessions/2026-10-17-nontechnical-windows-readme.md).

- **Visible PC deployment progress (2026-10-16):** User reports another laptop
  blocked at `deploy_pc.ps1`; exact remote error/output still pending. Confirmed
  wrapper buffered all PC output until exit. PC subprocess logs now stream live
  and display five deployment stages. 22 focused tests and real local read-only
  PC preflight passed; no runtime restart. Video supports concurrent RTSP readers,
  but headset return still targets one PC and talkback is not coordinated across
  servers. See [evidence](docs/sessions/2026-10-16-deployment-progress.md).

- **Automatic Windows network deployment (2026-10-16):** User requests USB-first
  address discovery and one-command full redeployment using Windows OpenSSH only.
  Added `scripts/deploy.ps1`, a shared PowerShell helper and deployment guide.
  Central runtime `.env` retains camera aliases and records both devices' Wi-Fi
  and USB addresses, camera Wi-Fi MAC and exact fixed earbuds binding. Reuses
  camera staged install/reboot and Docker PC deployment; supports dry run,
  force, interface selection, backups/rollback and actual media health checks.
  Exact one-command live run completed successfully: Docker healthy, camera
  settings/processes and both video/headset streams verified; 21 focused tests
  passed. Includes one recording-safe PC stop/start for missing headset return
  after container recreation. Existing pairing token and headset binding kept.
  A second exact run verified idempotence: no install/build/reboot, both media
  streams and application checks passed again.
  See [session evidence](docs/sessions/2026-10-16-automatic-network-deployment.md)
  and [usage/recovery](scripts/README.md) for verification and runtime state.

- **Canvas presentation for quarter turns (2026-10-16):** User confirms both
  live 90-degree video and `20261016T044816Z_74cc3723.mp4` are black in their
  Edge session; filter workaround failed again after entering Recordings.
  Live 90/270 and portrait playback now paint decoded frames on canvas; source
  streams, copied MP4s and camera unchanged. Added portrait playback controls.
  30 browser checks passed; actual Edge playback of exact file, successful new
  90-degree capture and three return-to-live cycles showed clear canvas pixels.
  A three-second diagnostic recording failed with empty staging; retained.
  User initially still reported black. On continuation, inspected their actual
  Edge window: old page lacked canvas; hard refresh loaded the current player.
  Exact recording and return to 90-degree live visibly worked in that same
  window. PC Docker healthy, idle, rotation 90. No file-specific fix or mutation.
  See [canvas session](docs/sessions/2026-10-16-canvas-video-rendering.md).

- **Quarter-turn black-screen investigation (2026-10-16):** User reports Edge
  recording playback and video after recording fail at 90 degrees, while 0/180
  work; hard refresh does not help. Latest 90-degree file decodes clear frames
  and plays in isolated Edge/Chromium sessions. A real 90-degree recording cycle,
  playback and return to live also passed. No cause proven or source changes made;
  User identified `20261016T044816Z_74cc3723.mp4`. Deployed a small frontend
  compositing workaround for quarter-turn live video and recording playback;
  recordings/camera unchanged. All 26 browser checks and actual Edge repeated
  rotations/exact-file playback passed; user's affected session acceptance
  pending. Docker healthy, idle; last observed selection 0.
  See [investigation](docs/sessions/2026-10-16-quarter-turn-black-screen.md).

- **Rotation jump-back repair (2026-10-16):** User reports repeated rotations
  eventually jump back. Reproduced an older status poll overwriting a newly
  saved angle while waiting for Bluetooth. Frontend now ignores camera status
  from polls spanning a rotation update. Regression and full source/compiled
  browser suite passed (26 checks). PC Docker rebuilt healthy; camera unchanged.
  See [repair log](docs/sessions/2026-10-16-rotation-jump-back.md).

- **Original16:9 and reversed rotation (2026-10-16):** User requested0°=768×432 and inversion of90°. Camera now captures432×768 and physically rotates the complete imageCCW to768×432; encoder width is aligned without padding/SPS changes. Manager numeric90 now meansCCW (CSS negative angle, matching MP4 rotation), displaying432×768. Camera video alone restarted; PC Docker rebuilt healthy. Actual UI recordings and Chromium playback verified at0° and90°; final selection0°, no active recording/error.10 targeted checks/one skip,24 browser checks and Docker media checks passed. See [16:9 rotation session](docs/sessions/2026-10-16-16x9-rotation.md). Supersedes earlier resolution/angle convention below.

- **Camera-side pixel rotation (2026-10-16):** User explicitly requires MaixCAM to rotate pixels 90° CCW while preserving the original 640×480 capture area. Final camera code rotates full NV21 planes before hardware encoding, pads encoder input for alignment, and excludes only padding through SPS bounds; decoded RTSP/TCP output is480×640. Manager Original now adds0°; PC recordings copy this source without square resizing. Camera and PC deployed; clear live and exact-file recording playback verified. Short samples12–13fps; physical latency/long stability untested. Headset return unavailable after restart; no audible acceptance. See [camera rotation log](docs/sessions/2026-10-16-camera-pixel-rotation.md). Supersedes browser-only baseline below.

- **Manager rotation and recording aspect (2026-10-16):** User requested counter-clockwise live video, manual manager rotation and recordings preserving the original image. Added shared/persistent quarter-turn controls (counter-clockwise default), full-frame contain rendering, and MP4 rotation preserving 640×480 H.264 without video re-encoding. Rotation locks through capture/finalization. PC Docker rebuilt healthy; real Chromium verified live rotation and a new MP4 displayed 480×640. Further manager rotation selections were observed and preserved. 126 Python checks/five skips and 24 browser checks passed; real FFmpeg rotation checks passed on Windows and Debian. See [rotation session](docs/sessions/2026-10-16-manager-rotation-recording.md).

- **Restored commit redeployed (2026-10-16):** User requested latest-commit restore and redeployment of both devices. Camera installed/rebooted and Docker rebuilt healthy from  `6e55f38`. Clear 640×480 landscape video visually verified in Chromium. SCO connected at MTU120; PC stop/start restored initially missing G711 return. Talkback available; audible acceptance untested. See [deployment log](docs/sessions/2026-10-16-restored-commit-redeployment.md).

- **Architecture reference and safe local cleanup (2026-10-16):** User reports
  the architecture works well and requests documentation without code changes.
  Added source-checked architecture/pipeline/protocol reference and rendered
  diagram. Preserved all existing source/configuration edits and live services.
  Permanent cleanup was rejected by automatic approval policy; moved six
  disposable cache/build/test-output directories (46 files, 1,576,087 bytes) into
  ignored `.runtime/cleanup-quarantine-2026-10-16/` for reversible cleanup instead.
  Settings, token, recordings, dependencies, packaged UI and session evidence
  retained. See [architecture](docs/architecture.md) and
  [session log](docs/sessions/2026-10-16-architecture-cleanup.md).

- **SCO/multistream deployed (2026-10-11):** User requested README update and
  redeployment of both devices. Combined workflow installed/rebooted MaixCAM
  with SCO and rebuilt/recreated the healthy Docker PC with multistream.
  Windows HTTP passed; browser peers read H264 video and G711 headset return.
  Camera eSCO connected, MTU120:4, one capture; PC Bluetooth connected and
  talkback available. No recording/audio acceptance trial performed. See
  [redeployment log](docs/sessions/2026-10-11-sco-multimedia-redeployment.md).

- **SCO and multimedia defaults (2026-10-11):** User requested SCO and multimedia
  as the default pipeline, reporting SCO already in use. Multimedia means the
  existing multistream recorder: video plus mixed/worker/operator audio. Compose,
  `.env.example`, local `.env`, app and recorder defaults now select multistream;
  camera startup fallback also selects SCO. Explicit legacy/A2DP remain available.
  TCP/video monitoring and independent UDP8004 return are preserved. Suite ran
  123 tests successfully with five skips; Compose validation passed. No services
  restarted; recording changes activate at the next PC rebuild/deployment. See
  [default pipeline log](docs/sessions/2026-10-11-sco-multimedia-default.md).

- **SCO deployment defaults aligned (2026-10-11):** User reiterated recovered
  SCO setup is the default. `deploy_maix.ps1` and `run_all.ps1` now default
  `AudioProfile` to `sco`; explicit `a2dp` remains fallback. README and installer
  guides agree and include safe missing-headsetmic recovery. Legacy recording
  remains default, multistream optional. Ten deployment checks passed. No runtime
  restart in this update. Supersedes the earlier docs-only/A2DP script-default
  decision below. See [default update log](docs/sessions/2026-10-11-readme-sco-default.md).

- **Headset return recovery (2026-10-11,08:34–08:39 UTC):** User authorized
  fixing the outage. Safe PC stop/start restored UDP8004 publication and browser
  audio connection. Headset reconnect remained busy; scoped reset attempt lost
  camera access, then user hard-rebooted camera. After reconnect retries, SCO
  capture returned. Final six-second `/headsetmic` decode produced48000 samples,
  34190 nonzero; no new return loss in inspected post08:38:30 logs. Docker healthy,
  SCO120, talkback available. Audible user confirmation pending; underlying
  forwarding/profile failure causes remain unproven. No source fix in this
  recovery. See [outage/recovery evidence](docs/sessions/2026-10-11-headsetmic-outage.md).

- **Headset return outage (2026-10-11,08:31–08:32 UTC):** User pasted missing
  `/headsetmic` stream errors. Read-only checks found no SCO link, capture
  PCM-not-found retries, and PC receiver publication timeout/backoff. Camera
  still sends UDP8004 packets; eight-second container check saw none during
  receiver backoff. Addressing unchanged, Docker API healthy; no repair done.
  Cause of packet delivery loss remains unisolated. See
  [outage evidence](docs/sessions/2026-10-11-headsetmic-outage.md).

- **README standard SCO pipeline (2026-10-11):** User requested README use SCO
  duplex as the default pipeline. Camera and combined deployment examples now
  explicitly pass `-AudioProfile sco`, explain simultaneous listening/talkback,
  post-reboot checks and A2DP fallback. This documentation change does not alter
  script parameter defaults (A2DP when omitted), recordings or live services.
  See [README update log](docs/sessions/2026-10-11-readme-sco-default.md).

- **SCO boot-order repair (2026-10-11):** User requested root-cause fix.
  Traced boot confirmed MTU120 applied while down, power-up resetting to255,
  capture/eSCO opening at255, and connector overriding too late. SCO boot now
  synchronously powers/prepares/verifies MTU before audio clients start. Tests
  cover reset ordering and failed preparation; actual shell retry test passed.
  Fixed traced reboot opened capture/eSCO only at120; user confirmed steady
  WHIP tone without manual reconnect. Production probe removed; second clean
  reboot verified connected SCO120, stable capture and successful WHIP relay.
  Final suite121 tests/five skips; POSIX startup test separately passed in Docker.
  See [repair evidence](docs/sessions/2026-10-11-sco-boot-order.md).

- **SCO talkback recovery (2026-10-11):** User authorized a fix. Headset was
  connected and unmuted but initial WHIP tone was inaudible. Clean pause/ack,
  scoped headset disconnect/reconnect and capture resume restored delivery;
  user confirmed a steady tone through a 20-second browser-path WHIP test.
  Source, video, PC runtime and recording mode unchanged. Exact silent-link
  cause and prolonged stability remain unproven. See
  [recovery evidence](docs/sessions/2026-10-11-readme-redeployment.md).

- **Post-reboot SCO check (2026-10-11):** User rebooted camera. Read-only check
  confirmed one SCO connector, duplex receiver, microphone sender and SCO capture;
  eSCO connected, MTU 120:4. PC healthy, Bluetooth connected, talkback available;
  video/return republished after reboot. Persistent audio logs contain errors
  without enough timestamps to assign them to this boot. No fixes performed;
  audible duplex unverified. See
  [redeployment evidence](docs/sessions/2026-10-11-readme-redeployment.md).

- **SCO redeployment follow-up (2026-10-11):** User requested SCO duplex.
  Combined deployment with `-AudioProfile sco` passed camera reboot/video-port,
  Docker build/health and Windows HTTP checks. Camera configuration confirmed
  SCO in both directions at 8 kHz mono and MTU 120:4. Extra process inspection
  failed on unsupported BusyBox `ps -ww`; stopped checks without fixes as
  requested. Audible duplex remains unverified. See
  [redeployment evidence](docs/sessions/2026-10-11-readme-redeployment.md).

- **README redeployment (2026-10-11):** User requested both devices redeployed
  with failures reported and no fixes. Combined README workflow completed:
  MaixCAM installed/rebooted with default A2DP and PC destination 10.127.9.237;
  Docker rebuilt/recreated, healthy, Windows HTTP verified and browser opened.
  Logs confirmed online H.264 video and G.711 return. Audible checks remain
  untested. See [redeployment evidence](docs/sessions/2026-10-11-readme-redeployment.md).

- **Docker deployment cleanup (2026-10-11):** User chose Docker for all PC
  deployment and exactly four PowerShell entry points: `deploy_maix.ps1`,
  `deploy_pc.ps1`, `stop_docker_pc.ps1`, `run_all.ps1`. One Compose configuration
  now defaults to TCP/video plus independent UDP8004 return, with local browser
  port publication. Camera programs remain on MaixCAM; one parameterized boot
  template supports A2DP by default and opt-in experimental SCO. Generated HTML
  and the local pairing token are no longer tracked. README is a customer guide
  with actual demo screenshots. This supersedes older native startup instructions
  below; those entries retain the history. See
  [deployment cleanup evidence](docs/sessions/2026-10-11-docker-cleanup.md).

- **Repository cleanup (2026-10-11):** Removed two obsolete implementation prompts
  and unreferenced `auto.key`. Retained runtime files, packaged UI, diagnostic
  tools, package markers and session evidence. No live services changed. See
  [cleanup log](docs/sessions/2026-10-11-repository-cleanup.md).

- **PC multistream recorder (2026-10-11):** Implemented opt-in
  `--recording-mode multistream` / native `-RecordingMode multistream`. Independent
  H.264-copy staging and reconnecting 48 kHz PCM decoders produce mixed default,
  worker and operator AAC tracks on asynchronous stop. Monotonic audio timeline
  with silence; video arrival timestamps use a fixed PC clock bridge. Legacy
  recorder remains default. No camera, Bluetooth, live TCP/video route or runtime
  deployment changes. 105 Python tests passed, four skipped; two isolated real
  media tests and 22 browser tests passed. Physical flash/click synchronization,
  long hardware drift and VLC acceptance remain pending. See
  [recording guide](docs/multistream-recording.md) and
  [session evidence](docs/sessions/2026-10-11-multistream-recording.md).

- **SCO duplex trial (2026-10-11):** User requested a separate branch and
  sustained SCO investigation. `experiment/sco-duplex` starts from accepted
  recovery commit `4e8aafb` on clean `uplink-audio`. User confirmed simultaneous
  browser speech in both directions and accepted it as hearable, authorizing
  this checkpoint commit; Maix-to-PC quality remains bad.
  Live camera trial uses SCO/CVSD, 120-byte SCO MTU, and 20ms/80ms raw playback
  with paced silence during packet gaps. Twenty automated WHIP cycles connected;
  one earlier attempt failed strict camera clock calibration. Return HCI packets
  include invalid/no-data flags; exact cause remains unresolved. Opt-in scoped
  stuck-SCO recovery has regression coverage; a live normal disconnect recovered
  in27 seconds without triggering reset. A60-second hold connected but still
  logged underruns. 101 tests OK, two skipped. TCP/video,
  UDP8004 return and video-only recordings preserved. Boot remains A2DP;
  separate SCO template is uninstalled. No physical latency gain measured.
  See [SCO trial log](docs/sessions/2026-10-11-sco-duplex.md) and
  [procedure/rollback](docs/sco-duplex.md).

- **Audio recovery (2026-10-11, approximately 08:58 local):** Both audio routes
  failed with a stuck eSCO link and capture hw-parameter errors. Scoped audio
  restarts and reconnect did not recover SCO; resetting only hci0 restored
  sound. User confirmed both directions, A2DP talkback working perfectly, but
  noisy/choppy return. Fixed receiver pause deadline race (3s vs capture's
  2s termination wait). Requested 20ms capture periods/80ms buffer: exact-zero
  return frames fell from 252/300 to 13/298, then 2/300 in short samples. User
  reports much smoother return, still below talkback quality. No physical
  latency improvement measured. A2DP/half-duplex,
  TCP/video and recording unchanged. 91 tests OK, two skipped. See
  [audio recovery log](docs/sessions/2026-10-11-audio-recovery.md).

- **Stage 1 SCO validation (2026-10-11):** Live USB inspection confirmed
  SCO/CVSD playback and capture at 8kHz mono. Two isolated SCO tone tests
  exited successfully, but the user reported interrupted SCO sound. Two
  A2DP file tests timed out; capture processes reopened after all tests.
  Keep production A2DP: continuous audible SCO acceptance failed. No runtime
  route/startup, TB2, duplex, lifecycle, video or recording changes.
  Prepared separate `validation/a2dp-baseline` and `validation/sco-stage1`
  worktree branches with test helper, procedure and rollback. Browser-cycle
  comparison and physical latency remain pending; no latency gain measured.
  See [Stage 1 log](docs/sessions/2026-10-11-sco-stage1.md).

- **Talkback repair (2026-10-11, approximately 00:30):** Measured camera clock
  2.169 seconds ahead of Windows; Windows Time is stopped and cannot be started
  by this session. PC talkback now calibrates packet timestamps to an authenticated
  camera clock endpoint for each session without relaxing the two-second age
  limit. Sender deadlines also compensate for coarse Windows timer waits.
  Camera playback drops temporary full-pipe frames instead of restarting
  audio; normal release clears stale PC interruption status. Camera connector
  PID1260 and receiver PID1481 deployed; native PID9128 retains TCP/video and
  UDP8004 return. Silent device test kept one player through the hold and restored
  capture; Chromium validated video, return audio and talkback signaling. Audible
  speech still needs user confirmation. See [talkback repair log](docs/sessions/2026-10-11-talkback-repair.md).

- **Operator startup repair (2026-10-11, approximately 00:17):** Docker operator
  was restarting on MediaMTX's 4 MiB UDP request versus the Linux buffer limit.
  `app.py` now caps the request to `rmem_max`, or uses OS defaults if unreadable;
  native Windows sizing is unchanged. Native helper now detects restarting
  Docker operators too; Docker helper no longer requires VM sysctl changes.
  Docker image rebuilt, but operator container remains stopped. Native PID28756
  restored TCP/video plus UDP8004 return; HTTP200, decoded H.264 and available
  talkback verified. PPS errors did not recur in the short native check.
  See [startup repair log](docs/sessions/2026-10-11-startup-repair.md).

- **Bluetooth reconnect repair (2026-10-11, approximately 00:09):** Documented
  pinned PuTTY login works via USB 10.172.16.1. Camera connector PID3846 now
  avoids redundant Bluetooth mutations on healthy polls, does not re-pair on
  failed status reads, and backs off failed reconnects to 30 seconds. Camera
  logs showed historical busy/unknown/timeouts and missing playback PCM; the
  physical drop cause remains unproven. BlueALSA4.1.1/BlueZ5.68 expose both SCO
  directions and A2DP playback. Only the connector was restarted; accepted
  TCP/video plus independent return and A2DP/pause talkback remain unchanged.
  See the Bluetooth stability log for backup paths and validation.

- **User acceptance (2026-10-11):** The user reports that latency is great after
  direct deployment and requested committing this implementation before further
  work. Preserve TCP/video plus independent PCMU return on UDP8004. This is user
  feedback, not a numeric physical measurement or confirmation of SCO duplex.

- **Direct deployment (2026-10-10, approximately 23:57):** Native Windows app
  PID16660 runs TCP/video with independent return on UDP8004. Existing camera
  RTP sender feeds `/headsetmic`; real Chromium decoded H.264 and received PCMU,
  audio element unmuted/playing. Six-second input level was very quiet (mean
  -76.3dB, peak -50dB), so intelligible earbuds speech remains unverified.
  Talkback status reports available. SSH root authentication failed twice,
  including the requested retry, so camera files/profiles were not changed;
  SCO duplex remains pending and legacy talkback pauses capture. See deployment log.

- **Headset return implementation (2026-10-10, approximately 23:50):** An independent
  PCMU RTP receiver and browser `/headsetmic` WHEP audio are implemented. Native
  `start_operator.ps1` enables UDP8004 return by default (`-ReturnAudioPort 0`
  disables it); video/recordings remain video-only. Synthetic real Chromium
  media and regression checks passed; physical headset capture/duplex and latency
  remain unverified because SSH authentication was unavailable. Production
  processes were not restarted. Final HTTP8000 check was refused and no
  MediaMTX/FFmpeg processes were present at that check, before direct deployment.
  Default camera A2DP talkback still pauses capture;
  explicit SCO/duplex options need hardware validation. See the return guide/log.

- **Earlier runtime (2026-10-10, approximately 19:19):** Docker Desktop restart
  did not restore Windows access to the host-network operator listeners. The
  operator container is stopped; a hidden native Windows `app.py` process now
  runs with explicit `--maix-ip 192.168.1.7 --rtsp-transport tcp --stream-mode
  video`. Windows operator HTTP returned 200, `/maix01` published one H.264
  track, and the talkback status API reported available. Browser playback and
  audible talkback were not remeasured in this follow-up. Logs/PID are in
  `.runtime/operator-native.*`. ThingsBoard and PostgreSQL were restarted and
  are running (PostgreSQL healthy). Stop native services before starting the
  operator container again; Docker localhost forwarding remains unresolved.
- **Earlier user status (2026-10-10):** Video and PC-to-camera talkback latency
  are acceptable. Earbuds → MaixCAM → PC microphone audio remains unimplemented
  end to end. Existing microphone service/code must not be treated as completion
  of that path. Preserve the accepted video and talkback operation.
- **Keep TCP video-only monitoring.** The user chose the configuration observed
  around 18:38–18:40 on 2026-10-10 and asked to retain it while they investigate
  audio latency. Local `.env` contains `RTSP_TRANSPORT=tcp` and `STREAM_MODE=video`;
  both were verified in the earlier running Docker container. The latest native
  workaround passes equivalent explicit flags. Do not switch back to
  combined mode or UDP as routine cleanup.
- Code defaults remain UDP/combined for compatibility. Compose reads `.env`;
  native `python app.py` does not automatically load it. Pass explicit flags for
  equivalent native operation.
- Video path: MaixCAM RTSP/TCP → PC FFmpeg H.264 copy → MediaMTX RTSP/TCP →
  admin browser WebRTC/WHEP over UDP. Installed camera TCP-interleaved support
  was verified by actual received H.264 packets.
- Current monitored stream and recordings exclude headset microphone audio.
  The original camera microphone service still publishes direct RTP/UDP to PC
  port 8004, but video-only FFmpeg does not consume it. WHIP talkback and the
  authenticated sequenced-UDP TB2 camera relay remain independently available.
- Preserve the working architecture. Diagnose buffering and stream timing before
  major changes; do not assume TCP reduces latency. Do not start duplicate camera
  capture or Bluetooth audio processes.

## Documentation Index

| Read this | For |
|---|---|
| [README.md](README.md) | Current configuration, startup and project overview |
| [Architecture and protocols](docs/architecture.md) | Current Docker/SCO architecture, four data pipelines, port map, TB2 format and storage boundaries |
| [Docker run guide](docs/docker-run-guide.md) | Installation and operational troubleshooting; apply the current README settings when older guide defaults differ |
| [Transport and measurement guide](docs/rtsp-transport.md) | TCP/UDP selection, isolated modes, physical stopwatch capture and timing diagnostics |
| [Measured results](docs/rtsp-measurements.md) | Physical latency, packet/continuity metrics, evidence and limitations |
| [2026-10-10 session log](docs/sessions/2026-10-10-rtsp-latency.md) | Investigation history, final user decision and next steps |
| [UDP protocol/deployment history](docs/udp-media.md) | Earlier UDP validation, protocol details and fallback |
| [Frontend guide](frontend/README.md) | UI development, API and persistence boundaries |
| [Multistream recording](docs/multistream-recording.md) | Default PC recorder, timeline strategy, four-track MP4, recovery and physical acceptance procedure |
| [Headset return guide](docs/headset-return-audio.md) | Independent microphone return, duplex prerequisites, exact device/Windows commands and pending hardware checks |
| [Headset implementation log](docs/sessions/2026-10-10-headset-return.md) | Code changes, synthetic verification and unchanged live runtime |
| [Headset deployment log](docs/sessions/2026-10-10-headset-deployment.md) | Active native runtime, real camera RTP/browser delivery and remaining SSH/duplex limitation |
| [Headset acceptance log](docs/sessions/2026-10-11-headset-acceptance.md) | User latency feedback and implementation commit scope |
| [Bluetooth stability log](docs/sessions/2026-10-11-bluetooth-stability.md) | USB access, reconnect-handler repair, deployment and remaining physical-drop investigation |

## Findings and Open Questions

- Physical Edge pilots: UDP video-only 175 ms median / 200 ms p95 (12 clear
  samples); TCP video-only 230 / 240 ms (7); earlier UDP combined 1,710 / 1,980 ms
  (13). These are provisional, short trials, not guarantees or a fully controlled
  mode comparison. The user's original 10.23-second delay was not reproduced.
- Short UDP arrival-versus-PTS traces showed approximately −0.91 ms/s delay growth
  at the camera and +4.80 ms/s at combined relay output. This suggests examining
  the PC combined path; it does not isolate FFmpeg from MediaMTX or measure
  absolute stage latency.
- The user observed lower video **and audio** delay around 18:38–18:40. That time
  matches TCP video-only. Video measurements support the observation; the audio
  source remains unresolved because the publisher excluded microphone audio.
  The latest clarification accepts PC talkback latency and identifies earbuds →
  MaixCAM → PC audio as unimplemented; the earlier observation does not establish
  that the earbuds microphone path works.
- Physical synchronized audio/video testing is unavailable until a matching
  flash/click stimulus is arranged. Browser buffers, PTS offsets and startup time
  must not be reported as physical end-to-end or A/V synchronization measurements.
- Desktop capture works; built-in OCR was unreliable. Use simultaneous saved
  stopwatch images and clear manual readings. ROIs depend on the current desktop
  layout; reject occluded, ambiguous and reconnection samples.

## Session Memory Maintenance

After substantial work, add a dated log under `docs/sessions/` with user requests,
changes, commands/results, failures, unresolved questions and final runtime state.
Link it here and update current decisions. Separate measured facts, user reports
and hypotheses. Keep raw captures/logs in ignored `.runtime/`, recordings in
`recordings/`, and credentials/tokens out of session notes. Preserve unrelated
working-tree edits; the 2026-10-10 session began with extensive existing changes.

## Codex Runtime Conventions

Use `.codex/config.toml` as the baseline when present (absent in this checkout at
the last update). Keep MCP usage task-driven. Prefer project-local role files in
`.codex/agents/` when available, and follow current delegation instructions.
Project skills in `.agents/skills/` should describe concrete Codex workflows and
artifacts without Claude-only commands or hidden runtime assumptions.

## Repository Guidelines

## Project Structure & Module Organization

This project relays MaixCAM video and Bluetooth headset audio to the WorkerCam Admin interface. `app.py` supervises the PC stack; `pc/` contains the operator HTTP server, recording, Bluetooth client, and talkback relay. `maix/` contains camera programs and device startup templates. `frontend/src/` holds React/TypeScript UI code; `frontend/scripts/` packages the interface and generates demo media. Python tests live in `tests/`, browser tests in `frontend/tests/`, screenshots in `imgs/`, and runtime recordings in `recordings/`.

## Build, Test, and Development Commands

Run these from the repository root:

- `powershell.exe -NoProfile -ExecutionPolicy Bypass -File ./scripts/deploy.ps1 -WifiSsid <SSID> -HeadsetMac <MAC>`:
  the only deployment script; hard-fresh reinstall both devices, stopping all
  running Docker containers. `-DryRun` performs read-only discovery. Camera/PC
  install and recording-safe stop are internal functions in `NetworkDeployment.psm1`.
- `docker compose config --quiet`: validate the single Compose configuration.
- `docker compose logs --tail 80 server`: inspect PC service logs.
- `python -m unittest discover -s tests -v`: run developer Python checks. Local
  Python/media tools are development dependencies, not customer requirements.

Run these from `frontend/`:

- `npm ci`: install locked dependencies.
- `npm run dev`: start Vite; `/api` proxies to the separately running PC server on port 8000.
- `npm run build`: type-check and generate ignored `pc/operator_test.html`. Docker generates it during image builds; do not commit the compiled copy.
- `npx playwright install chromium`: install the browser required by tests.
- `npm test`: build and test both source and compiled interfaces.

## Coding Style & Naming Conventions

Match existing code: four-space Python indentation, two-space TypeScript indentation, and descriptive names. Use `snake_case` for Python functions/modules and `camelCase` for TypeScript functions/variables; React components and types use `PascalCase`. Keep media handling in `media.ts` and persistence/API access in `data.ts`. No dedicated formatter or linter is configured; the frontend build checks types.

## Testing Guidelines

Use Python `unittest` with `test_*.py` files and `test_*` methods; use Playwright `*.spec.ts` files for browser behavior. Mock hardware and media services in automated tests. No numeric coverage threshold is configured. Add regression coverage for changed behavior; document physical-device checks separately.

## Completion Rule

For runtime changes, completion means the system works after redeployment.
Automated tests are supplementary diagnostics; passing tests, builds or task
checkboxes alone never establishes completion. Run tests after implementation.
Redeploy the affected PC/camera components within the authorized scope, then
verify startup and the affected real workflows: picture, listening, Talk,
rotation and recording as applicable. Report audible acceptance separately
when it needs the user's confirmation. If redeployment is not authorized or
cannot be verified, report "implemented; redeployment verification pending"
and keep overall completion pending. Documentation-only changes need no deployment.

## Commit & Pull Request Guidelines


History uses short descriptive subjects without a consistent prefix scheme. Write imperative subjects, such as `Fix headset reconnect handling`. PRs should explain behavior changes, list validation commands/results, link relevant issues, and include screenshots for UI changes. Document hardware requirements when applicable.

## Security & Configuration

Use token-free TB3 only on the trusted LAN; update PC and camera together. Keep optional legacy rollback tokens private and out of logs/reviews. Treat frontend login as a prototype, not API authorization. Configure camera addressing through `MAIX_IP`; keep recordings and generated runtime files out of commits.
