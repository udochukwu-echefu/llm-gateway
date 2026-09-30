import { spawnSync } from "node:child_process";
import { expect, test } from "vitest";

const valid = {
  ADMIN_API_URL: "http://fake.test",
  ADMIN_CONSOLE_ORIGIN: "https://console.test",
  ADMIN_CONSOLE_SESSION_SECRET: "obviously-fake-startup-test-at-least-32-bytes",
};

for (const script of ["scripts/start.mjs", "scripts/docker-start.mjs"]) {
  test(`${script} exits before startup for invalid configuration`, () => {
    for (const invalid of [
      { ADMIN_CONSOLE_SESSION_SECRET: undefined },
      { ADMIN_CONSOLE_SESSION_SECRET: "short" },
      { ADMIN_API_URL: "ftp://fake.test" },
      { ADMIN_CONSOLE_ORIGIN: "https://user:fake@console.test" },
      { ADMIN_CONSOLE_TRUSTED_PROXY_HOPS: "-1" },
      { ADMIN_CONSOLE_TRUSTED_PROXY_HOPS: "1.5" },
    ]) {
      const result = spawnSync(process.execPath, [script], {
        env: { ...process.env, ...valid, ...invalid },
        encoding: "utf8",
        timeout: 10000,
      });
      expect(result.status).toBe(1);
      expect(result.stderr).toMatch(/^Invalid console configuration:/);
      expect(result.stdout).not.toContain("Ready");
      expect(result.stderr.includes("short")).toBe(false);
    }
  });
}
