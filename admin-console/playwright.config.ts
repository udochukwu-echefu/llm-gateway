import { defineConfig } from "@playwright/test";

const port = process.env.CONSOLE_TEST_PORT ?? "3100";
const origin = `http://[::1]:${port}`;

export default defineConfig({
  testDir: "./tests/e2e",
  testIgnore: "**/public-demo.spec.ts",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 120000,
  expect: { timeout: 10000 },
  reporter: [["list"]],
  use: {
    baseURL: origin,
    viewport: { width: 1440, height: 1050 },
    trace: "off",
    screenshot: "off",
    video: "off",
  },
  webServer: [
    {
      command: "../.venv/bin/python tests/e2e/stack.py",
      gracefulShutdown: { signal: "SIGTERM", timeout: 10000 },
      url: "http://127.0.0.1:18090/healthz",
      timeout: 120000,
      reuseExistingServer: false,
    },
    {
      command: "npm run start",
      url: `${origin}/login`,
      timeout: 120000,
      reuseExistingServer: false,
      env: {
        HOSTNAME: "::",
        PORT: port,
        ADMIN_API_URL: "http://127.0.0.1:18091",
        ADMIN_CONSOLE_ORIGIN: origin,
        ADMIN_CONSOLE_SESSION_SECRET: "obviously-fake-e2e-session-secret-at-least-32-bytes",
        NEXT_TELEMETRY_DISABLED: "1",
        ADMIN_CONSOLE_TRUSTED_PROXY_HOPS: "0",
        DEMO_MODE: "false",
      },
    },
  ],
});
