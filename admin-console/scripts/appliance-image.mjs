import { spawnSync } from "node:child_process";

export const demoComposeArgs = [
  "compose",
  "-f",
  "deploy/demo/compose.yaml",
  "--profile",
  "demo-test",
];
const image = "llm-gateway-demo:step16";
const label = "org.opencontainers.image.revision";

/** Refuse old binaries even when a mutable local image tag exists. */
export function ensureApplianceImage() {
  const revision = sourceRevision();
  // Two different dirty trees share a stamp; only a clean commit can reuse an image.
  if (!revision.endsWith("-dirty") && imageRevision() === revision) return;
  console.error(`Demo appliance image is missing, stale or dirty; building ${revision}.`);
  const result = spawnSync(
    "docker",
    [...demoComposeArgs, "build", "--build-arg", `DEMO_SOURCE_REVISION=${revision}`, "appliance"],
    { cwd: "..", env: process.env, stdio: "inherit" },
  );
  if (result.status !== 0) throw buildError(revision);
  if (sourceRevision() !== revision || imageRevision() !== revision)
    throw new Error(
      "Demo appliance image/source revision changed or the build label is missing. " +
        "Refusing to start; rerun npm run test:e2e:demo to rebuild the current source.",
    );
}

function sourceRevision() {
  const commit = gitOutput(["rev-parse", "HEAD"]);
  const dirty = gitOutput(["status", "--porcelain", "--untracked-files=all"]);
  return `${commit}${dirty ? "-dirty" : ""}`;
}

/** @param {string[]} args */
function gitOutput(args) {
  const result = spawnSync("git", args, { cwd: "..", encoding: "utf8" });
  if (result.status !== 0)
    throw new Error(
      "Cannot determine demo source revision; run from admin-console in a Git checkout.",
    );
  return result.stdout.trim();
}

function imageRevision() {
  const result = spawnSync(
    "docker",
    ["image", "inspect", "--format", `{{ index .Config.Labels "${label}" }}`, image],
    { cwd: "..", encoding: "utf8" },
  );
  return result.status === 0 ? result.stdout.trim() : null;
}

/** @param {string} revision */
function buildError(revision) {
  return new Error(
    `Cannot build the current demo appliance image (${revision}); refusing to run a stale image. ` +
      "Check Docker and network access (offline builds require cached dependencies). " +
      "From the repository root, build the image with: " +
      `docker compose -f deploy/demo/compose.yaml --profile demo-test build --build-arg DEMO_SOURCE_REVISION=${revision} appliance; ` +
      "then rerun npm run test:e2e:demo from admin-console. Dirty checkouts always rebuild.",
  );
}
