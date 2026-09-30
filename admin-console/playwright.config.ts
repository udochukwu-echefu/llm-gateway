import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./tests/e2e", fullyParallel: false, workers: 1, retries: 0, timeout: 120000, expect: { timeout: 10000 },
  reporter: [["list"]], use: { baseURL: "http://localhost:3100", viewport: { width: 1440, height: 1050 }, trace: "off", screenshot: "off", video: "off" },
  webServer: [
    { command: "../.venv/bin/python tests/e2e/stack.py", gracefulShutdown: { signal: "SIGTERM", timeout: 10000 }, url: "http://127.0.0.1:18090/healthz", timeout: 120000, reuseExistingServer: false },
    { command: "npm run start", url: "http://localhost:3100/login", timeout: 120000, reuseExistingServer: false, env: { HOSTNAME: "localhost", PORT: "3100", ADMIN_API_URL: "http://127.0.0.1:18091", ADMIN_CONSOLE_ORIGIN: "http://localhost:3100", ADMIN_CONSOLE_SESSION_SECRET: "obviously-fake-e2e-session-secret-at-least-32-bytes", NEXT_TELEMETRY_DISABLED: "1" } },
  ],
});
