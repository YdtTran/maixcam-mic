// The existing Python server serves one HTML file. Inline the compiled app so
// replacing its UI requires no new backend routes or static-file handlers.
import { readFile, writeFile, mkdir } from "node:fs/promises";
const folder = new URL("../dist/", import.meta.url);
let html = await readFile(new URL("index.html", folder), "utf8");
for (const match of [
  ...html.matchAll(/<script[^>]*src="([^"]+)"[^>]*><\/script>/g),
]) {
  const js = await readFile(
    new URL(match[1].replace(/^\//, ""), folder),
    "utf8",
  );
  html = html.replace(
    match[0],
    () => `<script type="module">${js.replace(/<\/script/gi, "<\\/script")}</script>`,
  );
}
for (const match of [
  ...html.matchAll(/<link[^>]*href="([^"]+\.css)"[^>]*>/g),
]) {
  const css = await readFile(
    new URL(match[1].replace(/^\//, ""), folder),
    "utf8",
  );
  html = html.replace(match[0], () => `<style>${css}</style>`);
}
await mkdir(new URL("../../pc/", import.meta.url), { recursive: true });
await writeFile(new URL("../../pc/operator_test.html", import.meta.url), html);
console.log("Updated pc/operator_test.html");
