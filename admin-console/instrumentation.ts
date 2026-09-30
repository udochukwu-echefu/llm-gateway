export async function register() {
  if (process.env.NEXT_RUNTIME === "nodejs") {
    const { readConfig } = await import("./lib/config");
    readConfig();
  }
}
