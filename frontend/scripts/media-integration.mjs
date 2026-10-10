// Real Chromium / MediaMTX check. Called by tests/test_udp_integration.py.
import { chromium, expect } from '@playwright/test';

const browser = await chromium.launch({ args: [
  '--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream',
  ...(process.env.FAKE_AUDIO_PATH ? [`--use-file-for-fake-audio-capture=${process.env.FAKE_AUDIO_PATH}`] : []),
] });
try {
  const page = await browser.newPage({ permissions: ['microphone'] });
  await page.addInitScript(() => {
    const Original = window.RTCPeerConnection;
    window.measurePeers = [];
    window.RTCPeerConnection = class extends Original {
      constructor(...args) {
        super(...args);
        window.measurePeers.push(this);
      }
    };
  });
  await page.goto(process.env.OPERATOR_URL);
  await page.getByLabel('Password', { exact: true }).fill('admin');
  await page.getByRole('button', { name: 'Sign In' }).click();
  await page.getByRole('button', { name: 'Settings', exact: true }).click();
  await page.getByLabel('MaixCAM stream (WHEP)').fill(process.env.WHEP_URL || 'http://127.0.0.1:18889/maix01/whep');
  await page.getByRole('button', { name: 'Save connection' }).click();
  await page.getByRole('button', { name: 'Live Workers', exact: true }).click();
  try {
    await expect(page.locator('video').first()).toHaveAttribute('data-media-transport', 'udp', { timeout: 20000 });
  } catch (error) {
    console.error(JSON.stringify(await page.evaluate(async () => Promise.all(window.measurePeers.map(async peer => ({
      state: peer.connectionState, ice: peer.iceConnectionState, signaling: peer.signalingState,
      stats: [...(await peer.getStats()).values()].filter(s => ['candidate-pair', 'inbound-rtp'].includes(s.type)),
    })))), null, 2));
    throw error;
  }
  await page.waitForFunction(() => document.querySelector('video')?.videoWidth > 0);
  const talk = page.getByRole('button', { name: 'Talk', exact: true });
  await talk.focus();
  await page.keyboard.down('Space');
  await expect(page.getByRole('button', { name: 'Talking...' })).toBeVisible({ timeout: 20000 });
  await page.waitForTimeout(3000);
  await page.screenshot({ path: process.env.SCREENSHOT_PATH, fullPage: true });
  const stopped = page.waitForResponse(r => r.url().endsWith('/api/talkback/stop'));
  await page.keyboard.up('Space');
  if (!(await stopped).ok()) throw new Error('Talkback stop failed');
  await expect(talk).toBeVisible();
  console.log('Real WHEP decoded H264 video; selected ICE transport UDP; WHIP talkback stopped');
} finally {
  await browser.close();
}
