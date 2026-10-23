# WorkerCam Admin frontend

React, TypeScript, Vite, and Lucide. This replaces the old operator page;
the Python backend and physical MaixCAM programs are unchanged.

## Deployment and development

Customer deployment runs entirely in Docker: from the project root, run
`./deploy_pc.ps1 -Build`, or `./run_all.ps1 -WifiSsid <SSID> -HeadsetMac <MAC>` (full fresh reinstall) to also open the browser.
The build packages this interface into the operator image. The page is available
at http://127.0.0.1:8000; Worker #07 connects to MaixCAM and Worker #12 is a demo.
See the [customer README](../README.md) for configuration and daily use.

For source development only, install Node.js and run from this directory:

```powershell
npm ci
npm run dev
```

Vite serves http://localhost:5173 and proxies `/api` to the Docker operator on
port 8000. The default browser media endpoint is on localhost port 8889.

```powershell
npm run build
npx playwright install chromium
npm test
```

The build generates `../pc/operator_test.html`; it is ignored by Git and rebuilt
inside Docker, so no duplicate compiled UI is maintained in source control.
Browser tests exercise both source and compiled interfaces using mocked camera
APIs and media signaling. They do not control the physical camera.

`src/demo.ts` and `scripts/demo-scene.svg` are retained source assets: the former
embeds the offline demonstration clip and the latter is its regeneration input.
Media probes and measurement scripts remain developer tools, excluded from the
customer image. Python tests run from the root with
`python -m unittest discover -s tests -v`.

After `npm run build`, run `node scripts/capture-readme.mjs` to regenerate the
README screenshots. It serves the compiled page on an isolated local port,
mocks unavailable camera APIs and uses Worker #12's demo. No device is contacted.

## Data and authentication boundaries

- Local demo login is `admin` / `admin`. Its session lives in sessionStorage
  and survives refresh in that tab. Logout clears it. This is a prototype UI
  gate, **not server-side authentication or API authorization**.
- Worker and preference entities and demo recording metadata persist in
  IndexedDB. `Repository` in `src/data.ts` provides generic collection/get/put
  methods, so a future backend database can replace `BrowserRepository` without
  putting database code in UI components. The UI does not connect directly to
  a server-side database.
- Worker #07 / Nguyen A uses the physical MaixCAM via existing APIs and WHEP.
  Battery, radio, and microphone telemetry are unavailable in the existing backend and are
  displayed as unknown. Headset state comes from the Bluetooth API.
- Worker #12 / Tran B is a demo device. Its recording/talk state is simulated.
  Stopping a demo recording saves metadata and replays/downloads the demo clip;
  it does not record the physical device.
  An embedded synthetic warehouse clip works offline. To regenerate it, install
  Playwright Chromium and FFmpeg, then run `node scripts/create-demo.mjs`.
- Real recording downloads use the browser's native file download with the
  recording filename, without buffering the whole file in an application Blob.
  Playback still uses the same byte-range file route for seeking.
- Settings stores WHEP and demo video URLs locally and retains real Bluetooth
  scan/select controls. Browser microphone capture publishes
  a WebRTC audio track through WHIP while Talk is held; the PC resamples to 8 kHz PCM16 for the camera.
- Browser camera audio starts muted to allow autoplay; use Enable audio.
  Microphone and IndexedDB require a supported browser. Use localhost or HTTPS
  for microphone access. A remote HTTPS deployment also needs HTTPS WHEP/API.

Quarter-turn live views (90/270 degrees) and portrait recording playback draw
decoded video frames on a canvas to avoid rotated native-video display failures
reported in Edge. `paintVideoFrames` in `src/media.ts` draws at source resolution
on video-frame callbacks, redraws after seeking and cancels callbacks on unmount.
CSS fits the complete picture. The underlying video retains decoding/audio;
portrait playback provides play/pause, seek, volume and fullscreen controls.
Landscape playback uses native controls. This changes presentation only: WHEP,
camera encoding and saved MP4 rotation metadata are unchanged.

## Existing API integration

| Feature | Existing endpoint |
| --- | --- |
| Recording status | `GET /api/recordings/status` |
| Start / stop recording | `POST /api/recordings/start`, `/api/recordings/stop` |
| Saved files | `GET /api/recordings`, returned file URLs |
| Talkback availability | `GET /api/talkback/status` |
| Talkback signaling / stop | `POST /api/talkback/offer` (SDP offer, JSON answer/session), `/api/talkback/stop` (`X-Talkback-Session` header) |
| Headset status | `GET /api/bluetooth/status` |
| Scan / select | `POST /api/bluetooth/scan`, `/api/bluetooth/select` |

Login, workers, and generic database backend APIs are future backend work.
The frontend never silently switches a failed physical camera into demo mode.

Browser audio uses a send-only WebRTC track via MediaMTX WHIP; HTTP carries signaling only. Playback uses WHEP. The selected ICE candidate pair must report UDP before the UI marks playback Online; Device Status shows the verified transport. Playback retries interrupted peers, and Talk releases on blur/navigation, including release during negotiation. See [UDP media prototype](../docs/udp-media.md) for the protocol map, deployment constraints, and actual-media integration test.

Settings also provides Camera Diagnostics via `GET /api/camera/diagnostics`: the backend checks Wi-Fi services and uses its configured USB address when Wi-Fi services are unreachable. Device addresses are configured on the PC server using `MAIX_IP` / `MAIX_USB_IP`, independently of the browser WHEP URL.
