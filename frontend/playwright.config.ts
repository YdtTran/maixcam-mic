import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./tests",
  use: {
    baseURL: "http://127.0.0.1:5173",
    viewport: { width: 1366, height: 768 },
    launchOptions: {
      args: [
        "--use-fake-ui-for-media-stream",
        "--use-fake-device-for-media-stream",
      ],
    },
  },
  projects: [
    { name: 'source' },
    { name: 'compiled', use: { baseURL: 'http://127.0.0.1:5174' } },
  ],
  webServer: [
    { command: "npm run dev -- --port 5173", url: "http://127.0.0.1:5173", reuseExistingServer: true },
    { command: "python -m http.server 5174 --bind 127.0.0.1 --directory ../pc", url: "http://127.0.0.1:5174/operator_test.html", reuseExistingServer: true },
  ],
});
