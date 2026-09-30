import { isIP } from "node:net";

export const CLIENT_ADDRESS_HEADER = "x-console-client-address";

export function normalizeAddress(address) {
  if (typeof address !== "string" || !isIP(address)) return null;
  if (address.startsWith("::ffff:") && isIP(address.slice(7)) === 4) return address.slice(7);
  if (isIP(address) === 6) return new URL(`http://[${address}]`).hostname.slice(1, -1);
  return address;
}

export function clientAddress(peer, forwarded, trustedHops = 0) {
  const fallback = normalizeAddress(peer) ?? "unknown";
  if (!trustedHops || typeof forwarded !== "string") return fallback;
  const chain = forwarded
    .split(",")
    .map((part) => part.trim())
    .filter(Boolean);
  if (chain.length < trustedHops) return fallback;
  return normalizeAddress(chain[chain.length - trustedHops]) ?? fallback;
}
