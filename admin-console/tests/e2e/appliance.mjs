// Disposable local appliance profile; never uses the owner's gateway database.
import { spawnSync } from "node:child_process";
import { demoComposeArgs as args, ensureApplianceImage } from "../../scripts/appliance-image.mjs";
function compose(command) {
  const result = spawnSync("docker", [...args, ...command], {
    cwd: "..",
    env: process.env,
    stdio: "inherit",
  });
  if (result.status !== 0) throw new Error("Local appliance test profile failed.");
}
function stop() {
  compose(["down", "--volumes"]);
  process.exit(0);
}
ensureApplianceImage();
process.on("SIGTERM", stop);
process.on("SIGINT", stop);
compose(["up", "-d", "--no-build"]);
setInterval(() => {
  const result = spawnSync("docker", [...args, "ps", "--status", "exited", "-q"], {
    cwd: "..",
    encoding: "utf8",
  });
  if (result.status !== 0 || result.stdout.trim()) {
    compose(["down", "--volumes"]);
    process.exit(1);
  }
}, 1000);
