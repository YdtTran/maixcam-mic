import { test, expect, type Page } from "@playwright/test";
import { demoVideo } from "../src/demo";
import { spawn } from "node:child_process";
import { once } from "node:events";
import { readFile } from "node:fs/promises";

test("real backend downloads exact bytes natively and retains range playback and seeking", async ({ page, request, baseURL }) => {
  const backend = spawn("python", ["-u", "-c", `
import base64, sys, tempfile, threading, urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from pc.operator_server import RecordingManager, make_handler
with tempfile.TemporaryDirectory() as directory:
    clip = Path('frontend/src/demo.ts').read_text().split('base64,')[1].split("'")[0]
    Path(directory, '20261021T000000Z_12345678.mp4').write_bytes(base64.b64decode(clip))
    class Handler(make_handler(RecordingManager(directory))):
        def do_GET(self):
            if self.path.startswith('/api/'):
                return super().do_GET()
            with urllib.request.urlopen(sys.argv[1] + self.path) as response:
                data = response.read()
                self.send_response(200)
                self.send_header('Content-Type', response.headers['Content-Type'])
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(server.server_port, flush=True)
    sys.stdin.readline()
    server.shutdown()
    server.server_close()
`, baseURL!], { cwd: "..", windowsHide: true });
  try {
    const [output] = await once(backend.stdout, "data");
    const origin = `http://127.0.0.1:${String(output).trim()}`;
    const file = "/api/recordings/20261021T000000Z_12345678/file";
    const bytes = Buffer.from(demoVideo.split(",")[1], "base64");
    await setup(page);
    await page.unroute("**/api/**");
    await page.addInitScript(() => {
      const original = window.fetch;
      window.fetch = (...args) => {
        if (String(args[0]).endsWith("/file")) throw new Error("Full-file fetch forbidden");
        return original(...args);
      };
      URL.createObjectURL = () => { throw new Error("Application Blob forbidden"); };
    });
    await page.goto(origin + "/operator_test.html");
    await login(page);
    await page.getByRole("button", { name: "Recordings", exact: true }).click();
    await expect(page.locator("tbody tr")).toHaveCount(1);
    const pending = page.waitForEvent("download");
    await page.getByRole("button", { name: "Download", exact: true }).click();
    const download = await pending;
    expect(download.suggestedFilename()).toBe("20261021T000000Z_12345678.mp4");
    expect(await readFile((await download.path())!)).toEqual(bytes);
    for (const [range, start, end] of [["bytes=10-29", 10, 29], ["bytes=-32", bytes.length - 32, bytes.length - 1]] as const) {
      const response = await request.get(origin + file, { headers: { Range: range } });
      expect(response.status()).toBe(206);
      expect(response.headers()["content-range"]).toBe(`bytes ${start}-${end}/${bytes.length}`);
      expect(await response.body()).toEqual(bytes.subarray(start, end + 1));
    }
    expect((await request.get(origin + file, { headers: { Range: `bytes=${bytes.length}-` } })).status()).toBe(416);
    await page.getByRole("button", { name: "Play", exact: true }).click();
    const video = page.getByRole("dialog").locator("video");
    await expect.poll(() => video.evaluate((element: HTMLVideoElement) => element.readyState)).toBeGreaterThanOrEqual(2);
    await video.evaluate((element: HTMLVideoElement) => { element.pause(); element.currentTime = 2; });
    await expect.poll(() => video.evaluate((element: HTMLVideoElement) => !element.seeking && element.currentTime >= 2)).toBe(true);
  } finally {
    const exited = once(backend, "exit");
    backend.stdin.end("\n");
    await exited;
  }
});

async function setup(page: Page, fixed = false, baseRotation = 0) {
  let recording = false;
  let saved = false;
  let rotation = 0;
  let captureVolume = 100;
  const requests: string[] = [];
  await page.addInitScript(() => {
    class Peer {
      static instances: Peer[] = [];
      constructor() { Peer.instances.push(this); }
      iceGatheringState = "complete";
      connectionState = "new";
      localDescription = { sdp: "test offer" };
      onconnectionstatechange: (() => void) | null = null;
      tracks: string[] = [];
      addTransceiver(kind: string) { this.tracks.push(kind); }
      addTrack() {}
      getStats() {
        return Promise.resolve(new Map([
          ["transport", { type: "transport", selectedCandidatePairId: "pair" }],
          ["pair", { type: "candidate-pair", localCandidateId: "local" }],
          ["local", { type: "local-candidate", protocol: "udp" }],
        ]));
      }
      createOffer() {
        return Promise.resolve({ type: "offer", sdp: "test offer" });
      }
      setLocalDescription() {
        return Promise.resolve();
      }
      setRemoteDescription() {
        this.connectionState = "connected";
        this.onconnectionstatechange?.();
        return Promise.resolve();
      }
      close() {}
      addEventListener() {}
      removeEventListener() {}
    }
    Object.defineProperty(window, "RTCPeerConnection", { value: Peer });
  });
  await page.route("**/maix01/whep", (route) =>
    route.fulfill({
      status: 201,
      contentType: "application/sdp",
      body: "test answer",
    }),
  );
  await page.route("**/headsetmic/whep", (route) => route.fulfill({
    status: 201, contentType: "application/sdp", body: "test answer",
  }));
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    requests.push(path);
    let payload: unknown = {};
    if (path === "/api/recordings/status")
      payload = { recording, duration_seconds: 0, rotation, effective_rotation: (baseRotation + rotation) % 360 };
    if (path === "/api/camera/view") {
      if (route.request().method() === "POST") rotation = route.request().postDataJSON().rotation;
      payload = { rotation, effective_rotation: (baseRotation + rotation) % 360, locked: recording };
    }
    if (path === "/api/recordings/start") {
      recording = true;
      payload = { recording: true, rotation, effective_rotation: (baseRotation + rotation) % 360 };
    }
    if (path === "/api/recordings/stop") {
      recording = false;
      saved = true;
      payload = { recording: false, rotation, effective_rotation: (baseRotation + rotation) % 360 };
    }
    if (path === "/api/recordings")
      payload = saved
        ? [
            {
              id: "20261010T080214Z_12345678",
              created_at: "2026-10-10T08:02:14Z",
              duration_seconds: 271,
              active: false,
              url: "/api/recordings/20261010T080214Z_12345678/file",
            },
          ]
        : [];
    if (path === "/api/talkback/offer") payload = { sdp: "test answer", session: "test-session" };
    if (path === "/api/talkback/status") payload = { available: true };
    if (path === "/api/bluetooth/status")
      payload = { selected: "AA:BB:CC:DD:EE:FF", connected: true, fixed };
    if (path === "/api/bluetooth/capture-volume") {
      if (route.request().method() === "POST") captureVolume = route.request().postDataJSON().volume;
      payload = { volume: captureVolume };
    }
    if (path === "/api/bluetooth/scan")
      payload = {
        selected: null,
        connected: false,
        devices: [{ name: "Worker Headset", mac: "AA:BB:CC:DD:EE:FF" }],
      };
    if (path === "/api/bluetooth/select")
      payload = { selected: "AA:BB:CC:DD:EE:FF", connected: true, fixed };
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(payload),
    });
  });
  await page.goto("/operator_test.html");
  return requests;
}
async function login(page: Page) {
  await page.getByLabel("Password", { exact: true }).fill("admin");
  await page.getByRole("button", { name: "Sign In" }).click();
  await expect(
    page.getByRole("heading", { name: "Live Workers" }),
  ).toBeVisible();
}

test("maintenance disables recording and shows owner-specific recovery", async ({ page }) => {
  await setup(page);
  await page.route("**/api/recordings/status", route => route.fulfill({
    contentType: "application/json",
    body: JSON.stringify({ recording: false, rotation: 0, duration_seconds: 0,
      maintenance: { owner: "a".repeat(32) } }),
  }));
  await login(page);
  const message = page.getByRole("status", { name: "Maintenance active" });
  await expect(message).toContainText("a".repeat(32));
  await expect(message).toContainText("owner-specific recovery");
  await expect(page.getByRole("button", { name: "Record", exact: true })).toBeDisabled();
  await page.route("**/api/recordings/status", route => route.fulfill({
    contentType: "application/json",
    body: JSON.stringify({ recording: false, rotation: 0, duration_seconds: 0, maintenance: null }),
  }));
  await page.getByRole("button", { name: "Recordings", exact: true }).click();
  await page.getByRole("button", { name: "Refresh", exact: true }).click();
  await expect(message).toBeHidden();
  await page.getByRole("button", { name: "Live Workers", exact: true }).click();
  await expect(page.getByRole("button", { name: "Record", exact: true })).toBeEnabled();
});

test("manager rotation persists, preserves full player bounds, and locks while recording", async ({ page }) => {
  await setup(page);
  await login(page);
  const control = page.getByLabel("Camera rotation", { exact: true });
  const video = page.locator(".video-body video");
  await expect(control).toBeEnabled();
  await expect(control).toHaveValue("0");
  await expect(control.locator("option:checked")).toHaveText("Original (0°)");
  await expect(video).toHaveCSS("object-fit", "contain");
  for (const viewport of [{ width: 1366, height: 768 }, { width: 1920, height: 1080 }]) {
    await page.setViewportSize(viewport);
    for (const rotation of [270, 0, 90, 180]) {
      await control.selectOption(String(rotation));
      await expect(video).toHaveAttribute("data-rotation", String(rotation));
      await expect.poll(async () => video.evaluate((element) => {
        const bounds = element.getBoundingClientRect();
        const body = element.parentElement!.getBoundingClientRect();
        return Math.max(Math.abs(bounds.width - body.width), Math.abs(bounds.height - body.height),
                        Math.abs(bounds.x - body.x), Math.abs(bounds.y - body.y));
      })).toBeLessThan(1);
    }
  }
  await control.selectOption("90");
  await expect(video).toHaveCSS("transform", /matrix\(0, -1, 1, 0,/);
  await page.getByRole("button", { name: "Fullscreen video" }).click();
  await expect.poll(() => page.evaluate(() => Boolean(document.fullscreenElement))).toBe(true);
  await expect.poll(async () => video.evaluate((element) => {
    const bounds = element.getBoundingClientRect();
    return Math.abs(bounds.height - element.parentElement!.clientHeight);
  })).toBeLessThan(1);
  await page.evaluate(() => document.exitFullscreen());
  await page.reload();
  await expect(control).toHaveValue("90");
  await expect(control).toBeEnabled();
  await page.getByRole("button", { name: "Record", exact: true }).click();
  await expect(control).toBeDisabled();
  await page.getByRole("button", { name: "Stop Recording", exact: true }).click();
  await expect(control).toBeEnabled();
  await page.getByLabel("Select worker").selectOption("cam-012");
  await expect(control).toHaveCount(0);
  await expect(video).toHaveAttribute("data-rotation", "0");
  await expect(video).toHaveCSS("transform", /matrix\(1, 0, 0, 1,/);
});

test("a delayed status poll cannot undo a newer rotation", async ({ page }) => {
  await setup(page);
  await page.clock.install();
  await login(page);
  const control = page.getByLabel("Camera rotation", { exact: true });
  const video = page.locator(".video-body video");
  await expect(control).toBeEnabled();
  let release!: () => void;
  const delayed = new Promise<void>((resolve) => { release = resolve; });
  let waiting = false;
  await page.route("**/api/bluetooth/status", async (route) => {
    waiting = true;
    await delayed;
    await route.fulfill({ contentType: "application/json", body: JSON.stringify({ connected: false }) });
  });
  await page.clock.fastForward(10000);
  await expect.poll(() => waiting).toBe(true);
  for (const angle of [90, 0, 270, 90]) {
    await control.selectOption(String(angle));
    await expect(video).toHaveAttribute("data-rotation", String(angle));
    await expect(control).toBeEnabled();
  }
  const completed = page.waitForResponse("**/api/bluetooth/status");
  release();
  await completed;
  // Let the completed refresh update the UI before checking the saved angle.
  await expect(page.getByText("Disconnected", { exact: true })).toBeVisible();
  await expect(control).toHaveValue("90");
  await expect(video).toHaveAttribute("data-rotation", "90");
});

test("quarter-turn pictures retain decoded pixels after recording and page navigation", async ({ page }) => {
  await page.addInitScript(() => {
    const play = HTMLMediaElement.prototype.play;
    HTMLMediaElement.prototype.play = function () {
      // The mocked WHEP peer has no tracks; the test supplies real canvas frames.
      if (this.srcObject instanceof MediaStream && !this.srcObject.getTracks().length)
        return Promise.resolve();
      return play.call(this);
    };
  });
  await setup(page);
  await login(page);
  const control = page.getByLabel("Camera rotation", { exact: true });
  const picture = page.locator(".video-body canvas");
  const feed = () => page.locator(".video-body video").evaluate(async (video: HTMLVideoElement) => {
    const source = document.createElement("canvas");
    source.width = 80; source.height = 40;
    const context = source.getContext("2d")!;
    const draw = () => {
      context.fillStyle = source.dataset.flip ? "blue" : "red"; context.fillRect(0, 0, 40, 40);
      context.fillStyle = source.dataset.flip ? "red" : "blue"; context.fillRect(40, 0, 40, 40);
    };
    draw();
    const stream = source.captureStream(10);
    const timer = setInterval(draw, 100);
    stream.getVideoTracks()[0].addEventListener("ended", () => clearInterval(timer));
    video.srcObject = stream;
    (video as HTMLVideoElement & { testSource: HTMLCanvasElement }).testSource = source;
    await video.play();
  });
  const colors = () => picture.evaluate((canvas: HTMLCanvasElement) => {
    const context = canvas.getContext("2d")!;
    const top = context.getImageData(10, 10, 1, 1).data;
    const bottom = context.getImageData(10, 60, 1, 1).data;
    return [top[2] > 200 && top[0] < 40, bottom[0] > 200 && bottom[2] < 40];
  });
  await expect(control).toBeEnabled();
  await feed();
  await control.selectOption("90");
  await expect(picture).toBeVisible();
  await expect.poll(colors).toEqual([true, true]);
  const flip = (value: string) => page.locator(".video-body video").evaluate((video, value) => {
    (video as HTMLVideoElement & { testSource: HTMLCanvasElement }).testSource.dataset.flip = value;
  }, value);
  await flip("yes");
  await expect.poll(colors).toEqual([false, false]);
  await flip("");
  await expect.poll(colors).toEqual([true, true]);
  await page.getByRole("button", { name: "Record", exact: true }).click();
  await page.getByRole("button", { name: "Stop Recording", exact: true }).click();
  await expect.poll(colors).toEqual([true, true]);
  for (let visit = 0; visit < 2; visit++) {
    await page.getByRole("button", { name: "Recordings", exact: true }).click();
    await page.getByRole("button", { name: "Live Workers", exact: true }).click();
    await feed();
    await expect.poll(colors).toEqual([true, true]);
  }
  await control.selectOption("270");
  await expect.poll(colors).toEqual([false, false]);
  await control.selectOption("180");
  await expect(picture).toHaveCount(0);
  await expect(page.locator(".video-body video")).toHaveCSS("opacity", "1");
});

test("portrait playback draws frames and supports pause, seek, volume and fullscreen", async ({ page }) => {
  await setup(page);
  await login(page);
  // Reuse the checked-in synthetic MP4 with the same quarter-turn display
  // matrix as camera recordings, including its finite seekable timeline.
  const clip = Buffer.from(demoVideo.split(",")[1], "base64");
  const track = clip.indexOf(Buffer.from("tkhd")) - 4;
  expect(track).toBeGreaterThan(0);
  expect(clip[track + 8]).toBe(0);
  [0, -65536, 0, 65536, 0, 0, 0, 0, 1073741824].forEach((value, index) => {
    clip.writeInt32BE(value, track + 48 + index * 4);
  });
  await page.route("**/api/recordings/*/file", (route) => {
    const range = route.request().headers()["range"];
    const match = range?.match(/bytes=(\d+)-(\d*)/);
    const start = match ? Number(match[1]) : 0;
    const end = match?.[2] ? Number(match[2]) : clip.length - 1;
    return route.fulfill({
      status: match ? 206 : 200, contentType: "video/mp4",
      headers: { "Accept-Ranges": "bytes", ...(match ? { "Content-Range": `bytes ${start}-${end}/${clip.length}` } : {}) },
      body: clip.subarray(start, end + 1),
    });
  });
  await page.getByRole("button", { name: "Record", exact: true }).click();
  await page.getByRole("button", { name: "Stop Recording", exact: true }).click();
  await page.getByRole("button", { name: "Recordings", exact: true }).click();
  await page.getByRole("button", { name: "Play", exact: true }).click();
  const picture = page.locator("dialog canvas");
  await expect(picture).toBeVisible();
  await expect.poll(() => picture.evaluate((canvas: HTMLCanvasElement) => canvas.width)).toBe(600);
  await page.getByRole("button", { name: "Pause recording", exact: true }).click();
  await expect(page.getByRole("button", { name: "Play recording", exact: true })).toBeVisible();
  await page.getByLabel("Recording position", { exact: true }).fill("0.3");
  await expect.poll(() => page.locator("dialog video").evaluate((v: HTMLVideoElement) => v.currentTime)).toBeCloseTo(0.3, 1);
  await expect.poll(() => picture.evaluate((canvas: HTMLCanvasElement) => {
    const pixels = canvas.getContext("2d")!.getImageData(0, 0, canvas.width, canvas.height).data;
    let sum = 0;
    for (let i = 0; i < pixels.length; i += 4) sum += pixels[i] + pixels[i + 1] + pixels[i + 2];
    return sum / (canvas.width * canvas.height * 3) > 10;
  })).toBe(true);
  await page.getByLabel("Recording volume", { exact: true }).fill("0.4");
  await expect.poll(() => page.locator("dialog video").evaluate((v: HTMLVideoElement) => v.volume)).toBeCloseTo(0.4);
  await page.getByRole("button", { name: "Fullscreen recording", exact: true }).click();
  await expect.poll(() => page.evaluate(() => document.fullscreenElement?.className)).toBe("recording-player");
  await page.evaluate(() => document.exitFullscreen());
  await page.getByRole("button", { name: "Play recording", exact: true }).click();
  await expect.poll(() => page.locator("dialog video").evaluate((v: HTMLVideoElement) => v.currentTime)).toBeGreaterThan(0.4);
});

test("microphone loss and reconnect leave video connected; audio is enabled by interaction", async ({ page }) => {
  await setup(page);
  let failMic = true;
  let posts = 0;
  await page.route("**/headsetmic/whep", (route) => {
    posts++;
    return route.fulfill({ status: failMic ? 404 : 201, contentType: "application/sdp", body: "test answer" });
  });
  await login(page);
  await expect(page.locator("video").first()).toHaveAttribute("data-media-transport", "udp");
  await expect(page.getByText(/Earbuds microphone: Camera stream unavailable/)).toBeVisible();
  await page.getByRole("button", { name: "Enable audio", exact: true }).click();
  await expect.poll(() => page.locator("audio").evaluate((audio: HTMLAudioElement) => audio.muted)).toBe(false);
  failMic = false;
  await page.getByRole("button", { name: "Reconnect microphone", exact: true }).click();
  await expect(page.locator("audio")).toHaveAttribute("data-media-transport", "udp");
  await expect(page.locator("video").first()).toHaveAttribute("data-media-transport", "udp");
  await page.getByRole("button", { name: "Mute audio", exact: true }).click();
  await expect.poll(() => page.locator("audio").evaluate((audio: HTMLAudioElement) => audio.muted)).toBe(true);
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  const stoppedAt = posts;
  await page.waitForTimeout(2200);
  expect(posts).toBe(stoppedAt);
});

test("login validation, navigation, session refresh and logout", async ({
  page,
}) => {
  await setup(page);
  await page.getByLabel("Password", { exact: true }).fill("incorrect");
  await page.getByRole("button", { name: "Sign In" }).click();
  await expect(page.getByRole("alert")).toHaveText(
    "Incorrect username or password.",
  );
  await login(page);
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Live Workers" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Prototype Settings" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Log out", exact: true }).click();
  await expect(page.getByRole("button", { name: "Sign In" })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("button", { name: "Sign In" })).toBeVisible();
});

test("demo recording persists, talk releases, playback and download work", async ({
  page,
}) => {
  await setup(page);
  await login(page);
  await page.getByLabel("Select worker").selectOption("cam-012");
  await expect(
    page.locator(".status-row").filter({ hasText: "Battery" }),
  ).toContainText("64%");
  const talk = page.getByRole("button", { name: "Talk", exact: true });
  await talk.focus();
  await page.keyboard.down("Space");
  await expect(page.getByRole("button", { name: "Talking..." })).toBeVisible();
  await page.keyboard.up("Space");
  await expect(talk).toBeVisible();
  await page.getByRole("button", { name: "Record", exact: true }).click();
  await expect(
    page.locator(".status-row").filter({ hasText: "Recording" }),
  ).toContainText("On");
  await page.reload();
  await page.getByLabel("Select worker").selectOption("cam-012");
  await page.getByRole("button", { name: "Stop Recording" }).click();
  await page.getByRole("button", { name: "Recordings", exact: true }).click();
  await expect(page.locator("tbody tr")).toHaveCount(1);
  await expect(page.locator("tbody tr")).toContainText("Tran B");
  await page.getByRole("button", { name: "Play", exact: true }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await expect(page.getByRole("dialog").locator("video")).toHaveAttribute(
    "src",
    /.+/,
  );
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).not.toBeVisible();
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download", exact: true }).click();
  expect((await download).suggestedFilename()).toMatch(/^cam-012_.*\.mp4$/);
  await page.reload();
  await page.getByRole("button", { name: "Recordings", exact: true }).click();
  await expect(page.locator("tbody tr")).toContainText("Tran B");
});

test("optional metadata warnings stay separate from capture and clear after rotation repair", async ({ page }) => {
  await setup(page);
  let repaired = false;
  const warning = ".camera-view.json: invalid rotation. Using rotation 0; back up this file, then save a camera rotation to replace it.";
  await page.route("**/api/recordings/status", (route) => route.fulfill({
    contentType: "application/json",
    body: JSON.stringify({ recording: false, rotation: repaired ? 90 : 0, duration_seconds: 0,
      metadata_warnings: repaired ? [] : [warning] }),
  }));
  await page.route("**/api/camera/view", (route) => {
    repaired = true;
    return route.fulfill({ contentType: "application/json", body: JSON.stringify({ rotation: 90 }) });
  });
  await page.route("**/api/recordings", (route) => route.fulfill({
    contentType: "application/json", body: JSON.stringify([{
      id: "20261021T000000Z_12345678", created_at: "2026-10-21T00:00:00Z",
      duration_seconds: null, active: false, url: "/api/recordings/20261021T000000Z_12345678/file",
    }]),
  }));
  await login(page);
  const banner = page.getByRole("status", { name: "Metadata warnings" });
  await expect(banner).toContainText(warning);
  await expect(page.getByRole("button", { name: "Record", exact: true })).toBeEnabled();
  await page.getByRole("button", { name: "Recordings", exact: true }).click();
  await expect(page.locator("tbody tr")).toContainText("Unknown");
  await expect(banner).toBeVisible();
  await page.getByRole("button", { name: "Live Workers", exact: true }).click();
  await page.getByLabel("Camera rotation").selectOption("90");
  await expect(banner).not.toBeVisible();
  await expect(page.getByRole("status")).toContainText("Camera rotation saved");
});

test("physical camera actions use existing APIs; settings retain Bluetooth selection", async ({
  page,
}) => {
  await page.addInitScript(() => {
    const capture = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
    navigator.mediaDevices.getUserMedia = (constraints) => {
      const state = window as unknown as { talkConstraints: MediaStreamConstraints[] };
      (state.talkConstraints ||= []).push(constraints!);
      if (typeof constraints?.audio === "object" && constraints.audio.deviceId) {
        const error = new DOMException("No communications microphone", "OverconstrainedError");
        Object.defineProperty(error, "constraint", { value: "deviceId" });
        return Promise.reject(error);
      }
      return capture(constraints);
    };
  });
  const requests = await setup(page);
  await login(page);
  await expect(page.locator(".live-badge")).toHaveText("● LIVE");
  await page.getByRole("button", { name: "Record", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Stop Recording" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Stop Recording" }).click();
  await page.getByRole("button", { name: "Recordings", exact: true }).click();
  await expect(page.locator("tbody tr")).toContainText("Nguyen A");
  expect(requests).toContain("/api/recordings/start");
  expect(requests).toContain("/api/recordings/stop");
  await page.getByRole("button", { name: "Live Workers", exact: true }).click();
  const talk = page.getByRole("button", { name: "Talk", exact: true });
  await talk.focus();
  await page.keyboard.down("Space");
  await expect(page.getByRole("button", { name: "Talking..." })).toBeVisible();
  expect(await page.evaluate(() =>
    (window as unknown as { talkConstraints: MediaStreamConstraints[] }).talkConstraints[0].audio,
  )).toMatchObject({ deviceId: { exact: "communications" } });
  expect(await page.evaluate(() =>
    (window as unknown as { talkConstraints: MediaStreamConstraints[] }).talkConstraints[1].audio,
  )).toEqual({ echoCancellation: true, noiseSuppression: true, channelCount: 1 });
  await expect
    .poll(() => requests.includes("/api/talkback/offer"))
    .toBeTruthy();
  await page.keyboard.up("Space");
  await expect.poll(() => requests.includes("/api/talkback/stop")).toBeTruthy();
  await expect(talk).toBeVisible();
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  await page.getByRole("button", { name: "Scan", exact: true }).click();
  await expect(page.getByLabel("Bluetooth headset")).toHaveValue(
    "AA:BB:CC:DD:EE:FF",
  );
  await page.getByRole("button", { name: "Connect", exact: true }).click();
  expect(requests).toContain("/api/bluetooth/select");
  await page
    .getByLabel("MaixCAM stream (WHEP)")
    .fill("http://localhost:8889/maix02/whep");
  await page.getByRole("button", { name: "Save connection" }).click();
  await expect(page.getByRole("status")).toContainText(
    "Connection settings saved.",
  );
  await page.reload();
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  await expect(page.getByLabel("MaixCAM stream (WHEP)")).toHaveValue(
    "http://localhost:8889/maix02/whep",
  );
});

test("multistream finalization protects recording and reports saved after completion", async ({ page }) => {
  await setup(page);
  let recording = false;
  let finalizing = false;
  await page.route("**/api/recordings/status", (route) => route.fulfill({
    contentType: "application/json", body: JSON.stringify({ recording, finalizing, duration_seconds: 1, rotation: 270 }),
  }));
  await page.route("**/api/recordings/start", (route) => {
    recording = true;
    return route.fulfill({ contentType: "application/json", body: JSON.stringify({ recording, rotation: 270 }) });
  });
  await page.route("**/api/recordings/stop", (route) => {
    finalizing = true;
    return route.fulfill({ contentType: "application/json", body: JSON.stringify({ recording, finalizing, rotation: 270 }) });
  });
  await login(page);
  await page.getByRole("button", { name: "Record", exact: true }).click();
  await page.getByRole("button", { name: "Stop Recording" }).click();
  await expect(page.getByRole("button", { name: "Finalizing...", exact: true })).toBeDisabled();
  await expect(page.getByRole("status")).toContainText("Finalizing recording");
  await page.screenshot({ path: "test-results/multistream-finalizing.png" });
  finalizing = false;
  recording = false;
  await expect(page.getByRole("button", { name: "Record", exact: true })).toBeEnabled({ timeout: 15000 });
  await expect(page.getByRole("status")).toContainText("recording saved");
});

for (const outcome of ["exit 1", "forced termination", "spontaneous exit 1"]) {
  test(`legacy recording reports ${outcome} without saved success`, async ({ page }) => {
    await setup(page);
    let recording = false;
    let error: string | null = null;
    let releaseStatus: (() => void) | undefined;
    const stopped = new Promise<void>((resolve) => { releaseStatus = resolve; });
    const failure = `Legacy recording failed (${outcome}). Keep 20261021T000000Z_12345678.failed.mp4 and its FFmpeg log for recovery.`;
    await page.route("**/api/recordings/status", async (route) => {
      if (error && outcome !== "spontaneous exit 1") await stopped;
      await route.fulfill({ contentType: "application/json", body: JSON.stringify({ recording, error, rotation: 0 }) });
    });
    await page.route("**/api/recordings/start", (route) => {
      recording = true;
      return route.fulfill({ contentType: "application/json", body: JSON.stringify({ recording, rotation: 0 }) });
    });
    await page.route("**/api/recordings/stop", (route) => {
      recording = false;
      error = failure;
      return route.fulfill({ contentType: "application/json", body: JSON.stringify({ recording, error, rotation: 0 }) });
    });
    await login(page);
    await page.getByRole("button", { name: "Record", exact: true }).click();
    await expect(page.getByRole("status")).toContainText("recording started");
    if (outcome === "spontaneous exit 1") {
      recording = false;
      error = failure;
    } else {
      await page.getByRole("button", { name: "Stop Recording" }).click();
    }
    try {
      await expect(page.getByRole("status")).toContainText(failure, { timeout: 15000 });
      await expect(page.getByRole("status")).not.toContainText("recording saved");
    } finally {
      releaseStatus?.();
    }
    await expect(page.getByRole("button", { name: "Record", exact: true })).toBeEnabled();
    await page.getByRole("button", { name: "Recordings", exact: true }).click();
    await expect(page.getByText("No saved recordings yet. Start and stop a recording in Live Workers.")).toBeVisible();
  });
}

test("desktop composition, search, notifications, and honest offline status", async ({
  page,
}) => {
  await setup(page);
  await login(page);
  await page.getByLabel("Search workers, devices").fill("Tran");
  await expect(page.getByLabel("Select worker").locator("option")).toHaveCount(
    2,
  );
  await page.getByLabel("Select worker").selectOption("cam-012");
  await page.getByRole("button", { name: "Clear search" }).click();
  await page
    .getByRole("button", { name: "Notifications", exact: true })
    .click();
  await page.getByRole("button", { name: "Fullscreen video" }).click();
  await expect
    .poll(() => page.evaluate(() => !!document.fullscreenElement))
    .toBeTruthy();
  await page.evaluate(() => document.exitFullscreen());
  await expect(page.getByText("No new notifications.")).toBeVisible();
  await page
    .getByRole("button", { name: "Notifications", exact: true })
    .click();
  for (const width of [1366, 1920]) {
    await page.setViewportSize({ width, height: width === 1920 ? 1080 : 768 });
    const video = await page.locator(".video-card").boundingBox();
    const status = await page.locator(".status-column").boundingBox();
    expect(video!.width).toBeGreaterThan(status!.width);
    const feed = await page.locator('.video-body').boundingBox();
    expect(Math.abs(feed!.width - video!.width)).toBeLessThan(3);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBeTruthy();
    await page.screenshot({
      path: `test-results/dashboard-${width}.png`,
      fullPage: true,
    });
    expect(await page.evaluate(() => document.documentElement.scrollHeight)).toBeLessThanOrEqual(width === 1920 ? 1080 : 768);
  }
  await page.route("**/maix01/whep", (route) =>
    route.fulfill({ status: 503, body: "Camera unavailable" }),
  );
  await page.getByLabel("Select worker").selectOption("cam-007");
  await expect(
    page.getByRole("heading", { name: "Camera feed unavailable" }),
  ).toBeVisible();
  await expect(page.locator(".live-badge")).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Record", exact: true }),
  ).toBeDisabled();
});


test("fixed earbuds show status without device switching controls", async ({ page }) => {
  const requests = await setup(page, true);
  await login(page);
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  await expect(page.getByRole("heading", { name: "MaixCAM Earbuds" })).toBeVisible();
  await expect(page.getByText("These earbuds are bound to MaixCAM and reconnect automatically.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Scan", exact: true })).toHaveCount(0);
  await expect(page.getByLabel("Bluetooth headset")).toHaveCount(0);
  await expect(page.getByLabel("Earbud playback volume", { exact: true })).toHaveCount(0);
  expect(requests).not.toContain("/api/bluetooth/select");
});

test("live worker retains microphone control without earbud playback adjustment", async ({ page }) => {
  const requests = await setup(page, true);
  await login(page);
  await expect(page.getByLabel("Earbud playback volume", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Apply earbud volume", exact: true })).toHaveCount(0);
  await expect(page.getByLabel("Earbud microphone volume", { exact: true })).toHaveValue("100");
  await expect(page.getByRole("button", { name: "Talk", exact: true })).toBeEnabled();
  expect(requests).not.toContain("/api/bluetooth/volume");
});

test("microphone volume applies zero and reloads", async ({ page }) => {
  await setup(page, true);
  await login(page);
  const microphone = page.getByLabel("Earbud microphone volume", { exact: true });
  await expect(microphone).toHaveValue("100");
  await microphone.fill("0");
  await page.getByRole("button", { name: "Apply microphone volume", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("Earbud microphone volume set to 0%.");
  await page.getByLabel("Select worker").selectOption("cam-012");
  await expect(microphone).toHaveCount(0);
  await page.getByLabel("Select worker").selectOption("cam-007");
  await expect(microphone).toHaveValue("0");
  await microphone.fill("50");
  await page.getByRole("button", { name: "Apply microphone volume", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("Earbud microphone volume set to 50%.");
});

test("unavailable microphone control cannot apply a false volume", async ({ page }) => {
  await setup(page, true);
  await page.route("**/api/bluetooth/capture-volume", route => route.fulfill({status: 503,
    contentType: "application/json", body: JSON.stringify({error: "Microphone volume unavailable"})}));
  await login(page);
  await expect(page.getByLabel("Earbud microphone volume", {exact: true})).toBeDisabled();
  await expect(page.getByRole("button", {name: "Apply microphone volume", exact: true})).toBeDisabled();
  await expect(page.getByRole("status")).toContainText("Microphone volume unavailable");
});



test("playback retries a disconnected UDP peer", async ({ page }) => {
  await setup(page);
  await login(page);
  await expect(page.locator(".live-badge")).toHaveText("● LIVE");
  await page.evaluate(() => {
    const Peer = window.RTCPeerConnection as unknown as { instances: { tracks: string[]; connectionState: string; onconnectionstatechange: () => void }[] };
    const peer = Peer.instances.find((item) => item.tracks.includes("video"))!;
    peer.connectionState = "failed";
    peer.onconnectionstatechange();
  });
  await expect(page.locator(".live-badge")).not.toBeVisible();
  await expect(page.locator(".live-badge")).toHaveText("● LIVE", { timeout: 7000 });
});

test("unverified TCP ICE is never shown as online UDP", async ({ page }) => {
  await setup(page);
  await page.evaluate(() => {
    window.RTCPeerConnection.prototype.getStats = () => Promise.resolve(new Map([
      ["transport", { type: "transport", selectedCandidatePairId: "pair" }],
      ["pair", { type: "candidate-pair", localCandidateId: "local" }],
      ["local", { type: "local-candidate", protocol: "tcp" }],
    ]));
  });
  await login(page);
  await expect(page.locator(".status-row").filter({ hasText: "Media transport" })).toContainText("Unverified");
  await expect(page.locator(".live-badge")).not.toBeVisible();
});

test("release during WHIP negotiation cleans up the resulting session", async ({ page }) => {
  const requests = await setup(page);
  let offered = false;
  await page.route("**/api/talkback/offer", async (route) => {
    offered = true;
    await new Promise((resolve) => setTimeout(resolve, 700));
    await route.fulfill({ contentType: "application/json", body: JSON.stringify({ sdp: "test answer", session: "delayed-session" }) });
  });
  await login(page);
  const talk = page.getByRole("button", { name: "Talk", exact: true });
  await talk.focus();
  await page.keyboard.down("Space");
  await expect.poll(() => offered).toBeTruthy();
  await page.keyboard.up("Space");
  await expect.poll(() => requests.includes("/api/talkback/stop")).toBeTruthy();
  expect(requests).not.toContain("/api/talkback/audio");
  await expect(talk).toBeVisible();
});


test("camera diagnosis displays USB fallback when Wi-Fi is unreachable", async ({ page }) => {
  await setup(page);
  await page.route("**/api/camera/diagnostics", (route) => route.fulfill({
    contentType: "application/json", body: JSON.stringify({
      message: "Wi-Fi services unreachable. USB services reachable; use USB to diagnose the camera.",
      wifi: { ip: "192.168.1.7", reachable: false, tcp_services: { ssh: false, rtsp_control: false, bluetooth_control: false } },
      usb: { ip: "10.172.16.1", reachable: true, tcp_services: { ssh: true, rtsp_control: false, bluetooth_control: true } },
      usb_ip: "10.172.16.1",
    }),
  }));
  await login(page);
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  await page.getByRole("button", { name: "Diagnose camera" }).click();
  const result = page.getByRole("status").filter({ hasText: "use USB to diagnose" });
  await expect(result).toContainText("10.172.16.1");
  await expect(result).toContainText("RTSP control unreachable");
});


test("baseline offset changes live orientation without changing the manager selection", async ({ page }) => {
  await setup(page, false, 270);
  await login(page);
  const control = page.getByLabel("Camera rotation", { exact: true });
  const video = page.locator(".video-body video");
  await expect(control).toBeEnabled();
  await expect(control).toHaveValue("0");
  await expect(video).toHaveAttribute("data-rotation", "270");
  await expect(page.locator(".video-body canvas")).toBeVisible();
  await control.selectOption("90");
  await expect(control).toHaveValue("90");
  await expect(video).toHaveAttribute("data-rotation", "0");
  await expect(page.locator(".video-body canvas")).toHaveCount(0);
  await control.selectOption("180");
  await expect(video).toHaveAttribute("data-rotation", "90");
  await expect(page.locator(".video-body canvas")).toBeVisible();
  await page.getByRole("button", { name: "Record", exact: true }).click();
  await expect(control).toBeDisabled();
  await expect(video).toHaveAttribute("data-rotation", "90");
  await page.getByRole("button", { name: "Stop Recording", exact: true }).click();
  await expect(control).toBeEnabled();
  await page.reload();
  await expect(control).toHaveValue("180");
  await expect(video).toHaveAttribute("data-rotation", "90");
});
