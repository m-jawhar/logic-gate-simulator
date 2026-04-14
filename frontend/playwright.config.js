import { defineConfig, devices } from "@playwright/test";

const frontendURL = process.env.BASE_URL || "http://127.0.0.1:5173";
const frontendPort = new URL(frontendURL).port || "5173";
const pythonCommand = process.platform === "win32" ? "py -3" : "python3";

export default defineConfig({
  testDir: "./e2e",
  timeout: 120_000,
  expect: {
    timeout: 10_000,
  },
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: [
    ["list"],
    ["html", { outputFolder: "playwright-report", open: "never" }],
  ],
  use: {
    baseURL: frontendURL,
    viewport: { width: 1600, height: 960 },
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "off",
  },
  projects: [
    {
      name: "desktop-edge",
      use: {
        ...devices["Desktop Chrome"],
        channel: "msedge",
      },
      testMatch: /desktop\/.*\.spec\.js/,
    },
    {
      name: "mobile-edge",
      use: {
        ...devices["Pixel 7"],
        channel: "msedge",
      },
      testMatch: /mobile\/.*\.spec\.js/,
    },
  ],
  webServer: [
    {
      command: `${pythonCommand} -m uvicorn api:app --host 127.0.0.1 --port 8000`,
      cwd: "..",
      url: "http://127.0.0.1:8000/health",
      timeout: 120_000,
      reuseExistingServer: !process.env.CI,
    },
    {
      command: `npm run dev -- --host 127.0.0.1 --port ${frontendPort} --strictPort`,
      cwd: ".",
      url: frontendURL,
      timeout: 120_000,
      reuseExistingServer: !process.env.CI,
    },
  ],
});
