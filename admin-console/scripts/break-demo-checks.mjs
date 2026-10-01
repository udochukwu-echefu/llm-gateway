import { readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { spawnSync } from "node:child_process";
const root = resolve("..");
const cases = [
  {
    name: "a API viewer guard removed",
    file: "src/llm_gateway/admin/api/auth.py",
    before: 'if record.role == "viewer" and request.method not in',
    after: 'if record.role == "deliberate-break" and request.method not in',
    test: "tests/admin_api/test_authorization.py",
    filter: "test_viewer_authorization_matrix and POST",
  },
  {
    name: "b demo response exposes key",
    file: "admin-console/app/api/auth/demo/route.ts",
    before: "return reply({ identity }, 200);",
    after: "return reply({ identity, key }, 200);",
    unit: true,
    test: "demo sign-in uses a server-side key and returns only identity",
  },
  {
    name: "c startup accepts platform key",
    file: "admin-console/lib/demo-role.mjs",
    before: 'role: z.literal("viewer")',
    after: 'role: z.enum(["viewer", "platform"])',
    unit: true,
    test: "startup refuses a platform-admin demo key and wrong viewer scope",
  },
  {
    name: "d demo route active when off",
    file: "admin-console/app/api/auth/demo/route.ts",
    before: 'if (!config.DEMO_MODE) return reply({ error: "Not found." }, 404);',
    after: "// Deliberate break: demo always active.",
    unit: true,
    test: "demo route is 404 when demo mode is off",
  },
  {
    name: "e appliance admin binds publicly",
    file: "deploy/demo/config.py",
    before: '"GATEWAY_ADMIN_API__HOST": INTERNAL_HOST',
    after: '"GATEWAY_ADMIN_API__HOST": "0.0.0.0"',
    test: "tests/demo/test_appliance.py::test_appliance_internal_listeners_bind_only_loopback",
  },
  {
    name: "f boot key printed",
    file: "deploy/demo/boot_keys.py",
    before: "os.write(descriptor, json.dumps(keys).encode())",
    after: "print(json.dumps(keys))\n    os.write(descriptor, json.dumps(keys).encode())",
    test: "tests/demo/test_appliance.py::test_boot_keys_use_only_private_pipe_never_stdout_or_disk",
  },
  {
    name: "f boot key written to disk",
    file: "deploy/demo/boot_keys.py",
    before: "os.write(descriptor, json.dumps(keys).encode())",
    after:
      'with open("boot-keys.env", "w") as file:\n        file.write(json.dumps(keys))\n    os.write(descriptor, json.dumps(keys).encode())',
    test: "tests/demo/test_appliance.py::test_boot_keys_use_only_private_pipe_never_stdout_or_disk",
  },
];
for (const item of cases) {
  const path = resolve(root, item.file),
    original = readFileSync(path, "utf8");
  if (!original.includes(item.before)) throw new Error(`Mutation target missing: ${item.name}`);
  try {
    writeFileSync(path, original.replace(item.before, item.after));
    const result = item.unit
      ? spawnSync(
          process.execPath,
          ["node_modules/vitest/vitest.mjs", "run", "tests/lib/demo.test.ts", "-t", item.test],
          { encoding: "utf8" },
        )
      : spawnSync(
          resolve(root, ".venv/bin/pytest"),
          ["-q", "-p", "no:cacheprovider", item.test, ...(item.filter ? ["-k", item.filter] : [])],
          {
            cwd: root,
            encoding: "utf8",
            env: {
              ...process.env,
              GATEWAY_TEST_DATABASE_URL:
                "postgresql+asyncpg://gateway:local-only-example@127.0.0.1:5432/gateway",
            },
          },
        );
    const output = (result.stdout ?? "") + (result.stderr ?? "");
    if (
      result.status === 0 ||
      !/FAIL/.test(output) ||
      !/AssertionError|AssertionError:|^E\s+assert /m.test(output) ||
      /SyntaxError|ImportError|CollectionError/.test(output)
    )
      throw new Error(`Mutation did not fail its behavior assertion: ${item.name}`);
    console.log(`${item.name}: caught by ${item.test}`);
  } finally {
    writeFileSync(path, original);
  }
}
console.log("All seven demo mutations caught; every source restored.");
