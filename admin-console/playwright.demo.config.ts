import { defineConfig } from "@playwright/test";
import base from "./playwright.config";
const port = process.env.CONSOLE_TEST_PORT ?? "3300";
const origin = `http://localhost:${port}`;
process.env.DEMO_APPLIANCE_E2E = "1";
export default defineConfig({
  ...base,
  testIgnore: [],
  testMatch: "**/public-demo.spec.ts",
  use: { ...base.use, baseURL: origin },
  webServer: {
    command: "node tests/e2e/appliance.mjs",
    url: `${origin}/login`,
    // A missing/stale image may need an online build before service readiness.
    timeout: 1800000,
    reuseExistingServer: false,
    gracefulShutdown: { signal: "SIGTERM", timeout: 30000 },
    env: { CONSOLE_TEST_PORT: port },
  },
});
