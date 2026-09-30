import { cpSync, rmSync } from "node:fs";
import { fileURLToPath } from "node:url";
const root = new URL("../", import.meta.url);
const assets = new URL(".next/standalone/.next/static", root);
rmSync(assets, { recursive: true, force: true });
cpSync(new URL(".next/static", root), assets, { recursive: true });
process.env.HOSTNAME ??= "localhost";
await import(fileURLToPath(new URL(".next/standalone/server.js", root)));
