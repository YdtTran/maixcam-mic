import { test, expect, type Page } from "@playwright/test";

async function setup(page: Page, fixed = false) {
  let recording = false;
  let saved = false;
  const requests: string[] = [];
  await page.addInitScript(() => {
    class Peer {
      static instances: Peer[] = [];
      constructor() { Peer.instances.push(this); }
      iceGatheringState = "complete";
      connectionState = "new";
      localDescription = { sdp: "test offer" };
      onconnectionstatechange: (() => void) | null = null;
      addTransceiver() {}
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
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    requests.push(path);
    let payload: unknown = {};
    if (path === "/api/recordings/status")
      payload = { recording, duration_seconds: 0 };
    if (path === "/api/recordings/start") {
      recording = true;
      payload = { recording: true };
    }
    if (path === "/api/recordings/stop") {
      recording = false;
      saved = true;
      payload = { recording: false };
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

test("physical camera actions use existing APIs; settings retain Bluetooth selection", async ({
  page,
}) => {
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
  expect(requests).not.toContain("/api/bluetooth/select");
});


test("playback retries a disconnected UDP peer", async ({ page }) => {
  await setup(page);
  await login(page);
  await expect(page.locator(".live-badge")).toHaveText("● LIVE");
  await page.evaluate(() => {
    const Peer = window.RTCPeerConnection as unknown as { instances: { connectionState: string; onconnectionstatechange: () => void }[] };
    const peer = Peer.instances.at(-1)!;
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
