// Optional asset regeneration. The checked-in demo clip is a deliberately
// synthetic warehouse view, rendered from our own SVG and encoded with FFmpeg.
import { chromium } from "@playwright/test";
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
const temporary = new URL("../dist/demo/", import.meta.url);
await mkdir(temporary, { recursive: true });
const browser = await chromium.launch({ headless: true, channel: "chromium" });
try {
  const page = await browser.newPage({
    viewport: { width: 1280, height: 800 },
  });
  const svg = await readFile(
    new URL("./demo-scene.svg", import.meta.url),
    "utf8",
  );
  await page.setContent(`<style>body{margin:0}</style>${svg}`);
  await page.screenshot({
    path: fileURLToPath(new URL("scene.png", temporary)),
  });
} finally {
  await browser.close();
}
const output = new URL("warehouse.mp4", temporary);
const result = spawnSync(
  "ffmpeg",
  [
    "-y",
    "-loglevel",
    "error",
    "-i",
    fileURLToPath(new URL("scene.png", temporary)),
    "-vf",
    "zoompan=z='1+0.00035*on':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d=96:s=960x600:fps=24",
    "-frames:v",
    "96",
    "-c:v",
    "libx264",
    "-pix_fmt",
    "yuv420p",
    "-preset",
    "slow",
    "-crf",
    "25",
    "-movflags",
    "+faststart",
    fileURLToPath(output),
  ],
  { encoding: "utf8" },
);
if (result.status !== 0)
  throw new Error(
    result.stderr || "FFmpeg is required to regenerate the demo clip.",
  );
const clip = await readFile(output);
await writeFile(
  new URL("../src/demo.ts", import.meta.url),
  `// Synthetic industrial camera demo. Regenerate with node scripts/create-demo.mjs.\nexport const demoVideo = 'data:video/mp4;base64,${clip.toString("base64")}';\n`,
);
console.log(
  `Created embedded warehouse clip (${Math.round(clip.length / 1024)} kB).`,
);
