// Generate README screenshots from the real interface's offline demo worker.
// Run npm run build first. No physical device or live operator is contacted.
import { createServer } from 'node:http';
import { readFile, mkdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { chromium, expect } from '@playwright/test';

const html = await readFile(new URL('../../pc/operator_test.html', import.meta.url));
const images = new URL('../../imgs/', import.meta.url);
await mkdir(images, { recursive: true });
const server = createServer((request, response) => {
  response.writeHead(200, { 'Content-Type': 'text/html' });
  response.end(html);
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
let browser;
try {
  browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await page.route('**/api/**', route => {
    const path = new URL(route.request().url()).pathname;
    const payload = path === '/api/recordings' ? []
      : path === '/api/recordings/status' ? { recording: false, duration_seconds: 0 }
      : path === '/api/bluetooth/status' ? { connected: false, selected: null }
      : { available: false };
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(payload) });
  });
  await page.route('**/*/whep', route => route.fulfill({ status: 404, body: 'Demo capture: no physical camera' }));
  await page.goto(`http://127.0.0.1:${server.address().port}`);
  await page.getByLabel('Password', { exact: true }).fill('admin');
  await page.getByRole('button', { name: 'Sign In' }).click();
  await page.getByLabel('Select worker').selectOption('cam-012');
  await expect(page.getByRole('heading', { name: 'Live Workers' })).toBeVisible();
  await page.waitForFunction(() => document.querySelector('video')?.readyState >= 2);
  await page.locator('video').evaluate(video => { video.pause(); video.currentTime = 2; });
  await page.waitForFunction(() => !document.querySelector('video').seeking);
  await page.screenshot({ path: fileURLToPath(new URL('dashboard-demo.png', images)), fullPage: true });
  await page.getByRole('button', { name: 'Record', exact: true }).click();
  await page.waitForTimeout(1200);
  await page.getByRole('button', { name: 'Stop Recording', exact: true }).click();
  await page.getByRole('button', { name: 'Recordings', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Play', exact: true }).first()).toBeVisible();
  await page.screenshot({ path: fileURLToPath(new URL('recordings-demo.png', images)), fullPage: true });
  console.log('Saved imgs/dashboard-demo.png and imgs/recordings-demo.png (demo data).');
} finally {
  if (browser) await browser.close();
  await new Promise(resolve => server.close(resolve));
}
