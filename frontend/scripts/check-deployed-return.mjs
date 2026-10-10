// Read-only check of the deployed video and return audio; no talkback activation.
import { chromium, expect } from '@playwright/test';

const browser = await chromium.launch();
try {
  const page = await browser.newPage();
  await page.addInitScript(() => {
    const Original = window.RTCPeerConnection;
    window.checkPeers = [];
    window.RTCPeerConnection = class extends Original {
      constructor(...args) { super(...args); window.checkPeers.push(this); }
    };
  });
  await page.goto(process.env.OPERATOR_URL || 'http://127.0.0.1:8000/operator_test.html');
  await page.getByLabel('Password', { exact: true }).fill('admin');
  await page.getByRole('button', { name: 'Sign In' }).click();
  await expect(page.locator('video').first()).toHaveAttribute('data-media-transport', 'udp', { timeout: 20000 });
  await expect(page.locator('audio')).toHaveAttribute('data-media-transport', 'udp', { timeout: 20000 });
  await page.getByRole('button', { name: 'Enable audio', exact: true }).click();
  let verified;
  await expect.poll(async () => {
    verified = await page.evaluate(async () => {
    const received = [];
    for (const peer of window.checkPeers) {
      const stats = await peer.getStats();
      for (const report of stats.values()) {
        if (report.type === 'inbound-rtp') received.push({
          kind: report.kind, codec: stats.get(report.codecId)?.mimeType,
          bytesReceived: report.bytesReceived, packetsLost: report.packetsLost,
          framesDecoded: report.framesDecoded, jitter: report.jitter,
        });
      }
    }
    const audio = document.querySelector('audio');
    return { received, audioMuted: audio.muted, audioPaused: audio.paused };
    });
    return verified.received.some((report) => report.kind === 'video' && report.framesDecoded > 0)
      && verified.received.some((report) => report.kind === 'audio' && report.bytesReceived > 1000)
      && !verified.audioMuted && !verified.audioPaused;
  }, { timeout: 20000 }).toBe(true);
  console.log(JSON.stringify(verified, null, 2));
  if (process.env.SCREENSHOT_PATH) await page.screenshot({ path: process.env.SCREENSHOT_PATH, fullPage: true });
  await page.getByRole('button', { name: 'Settings', exact: true }).click();
} finally { await browser.close(); }
