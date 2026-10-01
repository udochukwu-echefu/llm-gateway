import { readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { spawnSync } from "node:child_process";
const root = resolve("..");
const cases = [
  {
    name: "a settings full-object disclosure",
    file: "src/llm_gateway/admin/api/platform.py",
    before: "return public_settings(configured)",
    after: 'return configured.model_dump(mode="json")',
    test: "tests/admin_api/test_platform_settings.py::test_settings_never_disclose_secrets",
  },
  {
    name: "e callable seeder local check removed",
    file: "scripts/seed_demo.py",
    before: "    require_local_sessions(sessions)",
    after: "    # Deliberate break: omitted local bound-engine check.",
    test: "tests/test_demo_seed.py::test_callable_seeder_refuses_remote_bound_engine_before_io",
  },
  {
    name: "b request org predicate removed",
    file: "src/llm_gateway/admin/service/request_log.py",
    before: "query = select(UsageRow).where(UsageRow.organization_id == org_id)",
    after: "query = select(UsageRow)",
    test: "tests/admin_api/test_requests.py::test_request_pagination_timeline_and_isolation",
  },
  {
    name: "c CSV formula neutralisation removed",
    file: "admin-console/lib/csv.ts",
    before: 'const safe = /^[\\s\\u0000-\\u001f]*[=+\\-@]/.test(raw) ? "\'" + raw : raw;',
    after: "const safe = raw;",
    unit: true,
    test: "CSV escapes delimiters quotes newlines and neutralises formula prefixes",
  },
  {
    name: "d command search all-org scope",
    file: "src/llm_gateway/admin/api/search.py",
    before:
      'scope = [] if admin.role == "platform" else [Organization.id == admin.organization_id]',
    after: "scope = []",
    test: "tests/admin_api/test_search.py::test_search_is_scoped_before_matching_names_and_ids",
  },
];
// CSV source is intentionally found by its dedicated assignment, independent of escaping.
cases[3].before = readFileSync(resolve(root, cases[3].file), "utf8")
  .split("\n")
  .find((line) => line.trimStart().startsWith("const safe ="));
for (const item of cases) {
  const path = resolve(root, item.file),
    original = readFileSync(path, "utf8");
  if (!item.before || !original.includes(item.before))
    throw new Error(`Mutation target missing: ${item.name}`);
  try {
    writeFileSync(path, original.replace(item.before, item.after));
    const result = item.unit
      ? spawnSync(
          process.execPath,
          [
            "node_modules/vitest/vitest.mjs",
            "run",
            "tests/lib/console-completeness.test.ts",
            "-t",
            item.test,
          ],
          { cwd: process.cwd(), encoding: "utf8" },
        )
      : spawnSync(resolve(root, ".venv/bin/pytest"), ["-q", "-p", "no:cacheprovider", item.test], {
          cwd: root,
          encoding: "utf8",
          env: {
            ...process.env,
            GATEWAY_TEST_DATABASE_URL:
              "postgresql+asyncpg://gateway:local-only-example@127.0.0.1:5432/gateway",
          },
        });
    const output = (result.stdout ?? "") + (result.stderr ?? "");
    if (
      result.status === 0 ||
      !(/AssertionError|^E\s+assert /m.test(output) && /FAIL/.test(output)) ||
      /SyntaxError|ImportError|CollectionError/.test(output)
    )
      throw new Error(`Mutation did not fail its behavior assertion: ${item.name}`);
    console.log(`${item.name}: caught by ${item.test}`);
  } finally {
    writeFileSync(path, original);
  }
}
console.log("All five console-completeness mutations caught; every source restored.");
