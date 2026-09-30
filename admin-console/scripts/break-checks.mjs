import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";
const env = {
  ...process.env,
  ADMIN_API_URL: "http://127.0.0.1:18091",
  ADMIN_CONSOLE_ORIGIN: "http://localhost:3100",
  ADMIN_CONSOLE_SESSION_SECRET: "obviously-fake-break-test-secret-at-least-32-bytes",
  NEXT_TELEMETRY_DISABLED: "1",
  CONSOLE_SCREENSHOTS: "0",
};
function run(args, expectedFailure) {
  const result = spawnSync("npm", args, {
    cwd: process.cwd(),
    env,
    encoding: "utf8",
    timeout: 300000,
  });
  const output = (result.stdout ?? "") + (result.stderr ?? "");
  if (expectedFailure) {
    if (result.status === 0 || !output.includes(expectedFailure)) {
      console.error(
        output
          .replace(/lgwa_[A-Za-z0-9_-]+/g, "[redacted]")
          .replace(/lgw_[A-Za-z0-9_-]+/g, "[redacted]"),
      );
      throw new Error(`Mutation was not caught by the designated test: ${expectedFailure}`);
    }
  } else if (result.status !== 0)
    throw new Error("Production build failed during mutation checks.");
}
function runGateway(testName) {
  const root = fileURLToPath(new URL("../../", import.meta.url));
  const result = spawnSync(root + ".venv/bin/pytest", ["-p", "no:cacheprovider", "-q", testName], {
    cwd: root,
    env: {
      ...env,
      GATEWAY_TEST_DATABASE_URL:
        "postgresql+asyncpg://gateway:local-only-example@127.0.0.1:5432/gateway",
      GATEWAY_TEST_REDIS_URL: "redis://127.0.0.1:6379/15",
    },
    encoding: "utf8",
    timeout: 300000,
  });
  const output = (result.stdout ?? "") + (result.stderr ?? "");
  const name = testName.split("::")[1];
  if (result.status === 0 || !output.includes(name)) {
    console.error(output.replace(/lgwa?_[A-Za-z0-9_-]+/g, "[redacted]"));
    throw new Error(`Gateway mutation was not caught by ${name}`);
  }
}

function mutate(path, change, check) {
  const original = readFileSync(path, "utf8");
  const changed = change(original);
  if (changed === original) throw new Error(`Mutation did not modify ${path}`);
  try {
    writeFileSync(path, changed);
    check();
  } finally {
    writeFileSync(path, original);
  }
}
const retainedKeyControl =
  "{remembered && <button onClick={() => setSecret(remembered)}>Reveal key again</button>}";
try {
  mutate(
    "app/(console)/layout.tsx",
    (s) =>
      'import { readSession } from "@/lib/session";\n' +
      s.replace(
        "identity={JSON.parse(identity) as Identity}",
        "identity={{ ...JSON.parse(identity), adminKey: (await readSession()).adminKey } as Identity}",
      ),
    () => {
      run(["run", "build"]);
      run(["run", "test:e2e"], "Admin credential in response");
      console.log(
        "a PASS: admin key passed to client Shell was caught by the real-stack response no-leak scan.",
      );
    },
  );
  mutate(
    "lib/origin.ts",
    (s) =>
      s.replace(
        'return request.headers.get("origin") === new URL(expected).origin;',
        "return true;",
      ),
    () => {
      run(
        ["test", "--", "tests/lib/routes.test.ts", "-t", "mutating HTTP handlers"],
        "mutating HTTP handlers reject cross-origin",
      );
      console.log(
        "b PASS: missing Origin check was caught by " +
          "mutating HTTP handlers reject cross-origin and missing Origin before any mutation.",
      );
    },
  );
  mutate(
    "components/team-keys.tsx",
    (s) =>
      s
        .replace(
          "const [secret, setSecret] = useState<string>();",
          "const [secret, setSecret] = useState<string>();\n  const [remembered, setRemembered] = useState<string>();",
        )
        .replace("setSecret(body.key)", "setSecret(body.key), setRemembered(body.key)")
        .replace(
          "{secret && <KeyCreatedDialog",
          retainedKeyControl + "\n    {secret && <KeyCreatedDialog",
        ),
    () => {
      run(
        ["test", "--", "tests/components/dialogs.test.tsx", "-t", "cannot be reopened"],
        "the created key cannot be reopened after closing",
      );
      console.log(
        "c PASS: re-openable key dialog was caught by the created key cannot be reopened after closing.",
      );
    },
  );
  mutate(
    "lib/session-policy.ts",
    (s) => s.replace("httpOnly: true", "httpOnly: false"),
    () => {
      run(
        ["test", "--", "tests/lib/session.test.ts", "-t", "secure cookie flags"],
        "round trip encrypts the credential and has secure cookie flags",
      );
      console.log(
        "d PASS: removed httpOnly was caught by round trip encrypts the credential and has secure cookie flags.",
      );
    },
  );
  mutate(
    "../src/llm_gateway/admin/api/auth.py",
    (source) =>
      source.replace(
        "    ip = client_ip(request, ctx.trusted_proxy_hops)\n",
        "    ip = client_ip(request, ctx.trusted_proxy_hops)\n" +
          "    if ctx.limits is not None:\n        await _failure_limit(ctx.limits, ip, False)\n",
      ),
    () => {
      runGateway(
        "tests/admin_api/test_security.py::test_valid_admin_bypasses_exhausted_failure_limit",
      );
      console.log(
        "e PASS: early failure-limit check was caught by " +
          "test_valid_admin_bypasses_exhausted_failure_limit.",
      );
    },
  );
  mutate(
    "../src/llm_gateway/admin/api/reports.py",
    (source) => source.replace("if value is not None\n                and (", "if ("),
    () => {
      runGateway("tests/admin_api/test_reports.py::test_unpriced_usage_is_json_null");
      console.log(
        "f PASS: string None serialization was caught by test_unpriced_usage_is_json_null.",
      );
    },
  );
} finally {
  run(["run", "build"]);
  console.log("All mutated sources restored; clean production build regenerated.");
}
