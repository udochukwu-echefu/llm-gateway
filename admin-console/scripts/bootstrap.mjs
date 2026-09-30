import { readConfig } from "../lib/config-schema.mjs";

try {
  readConfig();
} catch (error) {
  console.error(error.message);
  process.exit(1);
}
