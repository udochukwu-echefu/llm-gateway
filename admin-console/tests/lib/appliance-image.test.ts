import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { ensureApplianceImage, demoComposeArgs } from "../../scripts/appliance-image.mjs";

const mocks = vi.hoisted(() => ({ spawn: vi.fn(), log: vi.fn() }));
vi.mock("node:child_process", async (importOriginal) => {
  const actual = await importOriginal<typeof import("node:child_process")>();
  return { ...actual, default: { ...actual, spawnSync: mocks.spawn }, spawnSync: mocks.spawn };
});
afterEach(() => vi.restoreAllMocks());

const revision = "a".repeat(40);
let dirty: boolean;
let stamped: string | null;
let buildStatus: number;
let stampBuild: boolean;

beforeEach(() => {
  dirty = false;
  stamped = revision;
  buildStatus = 0;
  stampBuild = true;
  vi.clearAllMocks();
  vi.spyOn(console, "error").mockImplementation(mocks.log);
  mocks.spawn.mockImplementation((command: string, args: string[]) => {
    if (command === "git")
      return {
        status: 0,
        stdout: args[0] === "rev-parse" ? revision : dirty ? " M src/fake.py" : "",
      };
    if (args[0] === "image") return { status: stamped === null ? 1 : 0, stdout: stamped ?? "" };
    if (args.includes("build")) {
      if (stampBuild && buildStatus === 0)
        stamped = args.find((arg) => arg.startsWith("DEMO_SOURCE_REVISION="))!.split("=")[1];
      return { status: buildStatus };
    }
    throw new Error("Unexpected command");
  });
});

function buildCalls() {
  return mocks.spawn.mock.calls.filter(([, args]) => args.includes("build"));
}

test("matching clean source image is reused without a build", () => {
  ensureApplianceImage();

  expect(buildCalls()).toHaveLength(0);
  expect(mocks.spawn).toHaveBeenCalledWith(
    "docker",
    [
      "image",
      "inspect",
      "--format",
      '{{ index .Config.Labels "org.opencontainers.image.revision" }}',
      "llm-gateway-demo:step16",
    ],
    expect.any(Object),
  );
});

for (const old of [null, "old-commit", ""]) {
  test(`missing or mismatched image (${old}) is rebuilt and its label verified`, () => {
    stamped = old;

    ensureApplianceImage();

    expect(buildCalls()).toHaveLength(1);
    expect(buildCalls()[0]).toEqual([
      "docker",
      [...demoComposeArgs, "build", "--build-arg", `DEMO_SOURCE_REVISION=${revision}`, "appliance"],
      expect.objectContaining({ stdio: "inherit" }),
    ]);
    expect(mocks.spawn.mock.calls.filter(([, args]) => args[0] === "image")).toHaveLength(2);
  });
}

test("dirty checkouts always rebuild even if the existing dirty stamp matches", () => {
  dirty = true;
  stamped = `${revision}-dirty`;

  ensureApplianceImage();
  ensureApplianceImage();

  expect(buildCalls()).toHaveLength(2);
  expect(buildCalls()[0][1]).toContain(`DEMO_SOURCE_REVISION=${revision}-dirty`);
});

test("offline build failure stops with an explicit build instruction", () => {
  stamped = "old-commit";
  buildStatus = 1;

  expect(ensureApplianceImage).toThrow(/refusing to run a stale image.*offline.*docker compose/);
  expect(buildCalls()).toHaveLength(1);
  expect(mocks.spawn.mock.calls.some(([, args]) => args.includes("up"))).toBe(false);
});

test("a successful build without the matching label is refused", () => {
  stamped = "old-commit";
  stampBuild = false;

  expect(ensureApplianceImage).toThrow(/build label is missing.*Refusing to start/);
});

test("unknown Git revision is refused before inspecting or building an image", () => {
  mocks.spawn.mockReturnValue({ status: 1, stdout: "" });

  expect(ensureApplianceImage).toThrow("Cannot determine demo source revision");
  expect(mocks.spawn).toHaveBeenCalledTimes(1);
});
