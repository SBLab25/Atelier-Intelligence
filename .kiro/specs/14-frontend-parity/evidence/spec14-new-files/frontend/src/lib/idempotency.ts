/**
 * Idempotency keys for write actions (Spec 14, OD-151). A key is created when the page renders and sent with the
 * form, so a double submit or a retry after a network error repeats the same request instead of a second one.
 */
const KEY = /^[A-Za-z0-9._-]{8,64}$/;

export function newKey(): string {
  return crypto.randomUUID();
}

export function isKey(value: unknown): value is string {
  return typeof value === "string" && KEY.test(value);
}
