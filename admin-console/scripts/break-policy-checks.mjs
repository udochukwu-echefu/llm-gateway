import { readFileSync, writeFileSync } from "node:fs";
import { spawnSync } from "node:child_process";
const env = {
  ...process.env,
  CONSOLE_SCREENSHOTS: "0",
  GATEWAY_TEST_DATABASE_URL:
    "postgresql+asyncpg://gateway:local-only-example@127.0.0.1:5432/gateway",
};
function brokenTest(command, args, name, cwd = process.cwd()) {
  const result = spawnSync(command, args, { cwd, env, encoding: "utf8", timeout: 120000 });
  const output = (result.stdout ?? "") + (result.stderr ?? "");
  if (
    result.status === null ||
    result.status === 0 ||
    !output.includes(name) ||
    !/AssertionError|assert |expected .* to/i.test(output)
  ) {
    console.error(output.replace(/lgwa?_[A-Za-z0-9_-]+/g, "[redacted]"));
    throw new Error(`Mutation did not fail the designated behavior test: ${name}`);
  }
}
function mutate(label, path, before, after, check) {
  const original = readFileSync(path, "utf8");
  if (!original.includes(before)) throw new Error(`Missing mutation target: ${label}`);
  try {
    writeFileSync(path, original.replace(before, after));
    check();
    console.log(`${label} PASS`);
  } finally {
    writeFileSync(path, original);
  }
}
const unit = (file, name) => brokenTest("npm", ["test", "--", file, "-t", name], name);
mutate(
  "a API ignoring If-Match: test_fresh_stale_clear_and_repeated_writes",
  "../src/llm_gateway/policy_version.py",
  "if expected is None:",
  "if True:",
  () =>
    brokenTest(
      ".venv/bin/pytest",
      [
        "-p",
        "no:cacheprovider",
        "-q",
        "tests/admin_api/test_policy_versions.py::test_fresh_stale_clear_and_repeated_writes[org-model-policy-body0]",
      ],
      "test_fresh_stale_clear_and_repeated_writes",
      "..",
    ),
);
mutate(
  "b console omitting If-Match: model-policy deny-all requires confirmation before a conditional write",
  "components/use-policy-editor.ts",
  'headers: { "If-Match": `"${view.version}"` },',
  "headers: {},",
  () =>
    unit(
      "tests/components/policy-editors.test.tsx",
      "model-policy deny-all requires confirmation before a conditional write",
    ),
);
mutate(
  "c deny-all without confirmation: model-policy deny-all requires confirmation before a conditional write",
  "components/policy-editor-frame.tsx",
  ": danger;",
  ": undefined;",
  () =>
    unit(
      "tests/components/policy-editors.test.tsx",
      "model-policy deny-all requires confirmation before a conditional write",
    ),
);
mutate(
  "d purge enabled without typing: purge requires the exact typed name before calling the BFF",
  "components/cache-purge.tsx",
  "disabled={busy || typed !== name}",
  "disabled={busy}",
  () =>
    unit(
      "tests/components/policy-editors.test.tsx",
      "purge requires the exact typed name before calling the BFF",
    ),
);
mutate(
  "e BFF accepting unknown detector: strict policy schemas reject unknown detectors actions regions and bad patterns",
  "lib/policy-schemas.ts",
  "detector.safeParse(parts[0]).success",
  "true",
  () =>
    unit(
      "tests/lib/policy-editing.test.ts",
      "strict policy schemas reject unknown detectors actions regions and bad patterns",
    ),
);
console.log("All five policy mutations caught; every source restored.");
