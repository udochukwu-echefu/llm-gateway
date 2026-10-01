import { readConfig } from "../lib/config-schema.mjs";
import { checkDemoKeys } from "../lib/demo-role.mjs";

try {
  await checkDemoKeys(readConfig());
} catch (error) {
  console.error(error.message);
  process.exit(1);
}
