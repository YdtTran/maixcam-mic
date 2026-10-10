# WorkerCam Admin frontend

React, TypeScript, Vite, and Lucide. This replaces the old operator page;
the Python backend and physical MaixCAM programs are unchanged.

## Deployed operator page

The current Windows deployment uses native `app.py` in TCP video-only mode.
Open **http://127.0.0.1:8000/operator_test.html**, sign in with **admin / admin**,
and select **Worker #07**. This compiled page does not require Vite or a separate
frontend service. It can open while MaixCAM is offline; video and talkback require
the camera's existing services.

Docker Desktop localhost access failed even after restart on 2026-10-10, so the
operator container is stopped and a hidden native stack is running. Its PID/logs
are in `.runtime/operator-native.*`; do not run both stacks. Follow the
[root README](../README.md#run-the-configured-stack) for startup and evidence.
Earbuds → MaixCAM → PC audio remains unimplemented; current video and recordings
have no microphone track. The user reports acceptable video and PC talkback
latency, but physical playback was not retested after the native workaround.

## Frontend development

From this directory:

```powershell
npm ci
npm run dev
```

Open http://localhost:5173. Vite proxies `/api` to the existing PC server on
port 8000. Start that server separately using the project README. The default
WHEP stream is `http://<browser-host>:8889/maix01/whep`.

```powershell
npm run build
```

Build type-checks the sources and replaces `../pc/operator_test.html` with a
self-contained compiled page. The existing server serves it at `/` and
`/operator_test.html`. Docker builds this same page in a Node build stage;
`docker compose -f compose.yaml -f compose.host.yaml up --build -d`, from the
project root after stopping native services, builds and starts the Docker route.
Windows access through that route currently remains unresolved.
For native deployment, run `.\start_operator.ps1 -Build` from the project root
to rebuild this compiled page and start or reuse the working Windows stack.
Use `.\stop_operator.ps1` after stopping recording when shutting it down.
No frontend service or backend route changes are needed.

Run `npx playwright install chromium` once, then `npm test` for browser checks
against both the Vite source app and the compiled single-file page. Tests mock
camera APIs and media signaling; they do not control the physical MaixCAM.

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
- Settings stores WHEP and demo video URLs locally and retains real Bluetooth
  scan/select controls. Browser microphone capture publishes
  a WebRTC audio track through WHIP while Talk is held; the PC resamples to 8 kHz PCM16 for the camera.
- Browser camera audio starts muted to allow autoplay; use Enable audio.
  Microphone and IndexedDB require a supported browser. Use localhost or HTTPS
  for microphone access. A remote HTTPS deployment also needs HTTPS WHEP/API.

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
