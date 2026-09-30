import "./bootstrap.mjs";
// The dev CLI forks a server worker. Propagate the trusted socket bridge to it.
const preload = new URL("./request-address.mjs", import.meta.url).href;
process.env.NODE_OPTIONS = `${process.env.NODE_OPTIONS ?? ""} --import=${preload}`;
await import("../node_modules/next/dist/bin/next");
