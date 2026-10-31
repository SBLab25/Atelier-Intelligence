/**
 * The browser's address as seen through trusted proxies (Spec 15, OD-165), forwarded to the API as
 * `X-Forwarded-For` so its sign-in and per-address limits apply per user, not to the Next.js server.
 *
 * Same rule as the collector (`cji.collector.security.client_address`): with `hops` trusted proxies in front of
 * Next.js, the client is the `hops`-th entry from the right of `X-Forwarded-For`. With 0 hops nothing is trusted
 * and nothing is forwarded (the API then counts the Next.js server, as before Spec 15).
 */
const ADDRESS = /^[0-9A-Fa-f:.]{2,45}$/;

export function clientAddress(forwardedFor: string | null | undefined, hops: number): string | null {
  if (!Number.isInteger(hops) || hops <= 0 || !forwardedFor) {
    return null;
  }
  const entries = forwardedFor
    .split(",")
    .map((part) => part.trim())
    .filter((part) => part.length > 0);
  if (entries.length < hops) {
    return null;
  }
  const candidate = entries[entries.length - hops] ?? "";
  return ADDRESS.test(candidate) ? candidate : null;
}
