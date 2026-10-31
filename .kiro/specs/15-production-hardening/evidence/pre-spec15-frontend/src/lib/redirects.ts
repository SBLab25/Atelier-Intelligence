/**
 * Post-login redirect targets (Spec 13, OD-131): only same-origin absolute paths are kept, so `?next=` cannot send a
 * user to another site.
 */

const FALLBACK = "/";
const MAX_LENGTH = 512;

export function safeNext(raw: string | null | undefined): string {
  if (!raw || raw.length > MAX_LENGTH) {
    return FALLBACK;
  }
  let value: string;
  try {
    value = decodeURIComponent(raw);
  } catch {
    return FALLBACK;
  }
  // Must be a path on this origin: one leading slash, no scheme, no backslashes or control characters.
  if (!value.startsWith("/") || value.startsWith("//") || value.includes("\\") || /[\u0000-\u001f\u007f]/.test(value)) {
    return FALLBACK;
  }
  try {
    const url = new URL(value, "http://frontend.invalid");
    if (url.origin !== "http://frontend.invalid") {
      return FALLBACK;
    }
    if (url.pathname === "/login" || url.pathname.startsWith("/login/")) {
      return FALLBACK;
    }
    return url.pathname + url.search;
  } catch {
    return FALLBACK;
  }
}
