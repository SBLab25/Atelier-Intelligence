/**
 * Server configuration (Spec 13, OD-133). Pure parsing, so tests and the request proxy can use it; application code
 * imports `config.ts`, which adds the `server-only` guard. Every key is server-side: none is exposed to the browser.
 */

export const MIN_SECRET_LENGTH = 32;
export const DEFAULT_API_BASE_URL = "http://127.0.0.1:8006";
export const DEFAULT_TIMEOUT_MS = 10_000;

export interface ServerConfig {
  readonly apiBaseUrl: string;
  readonly sessionSecret: string;
  /** Spec 15: the key before the last rotation, accepted for reading session cookies (null = none). */
  readonly sessionSecretPrevious: string | null;
  readonly timeoutMs: number;
  /** Spec 15: proxies in front of Next.js whose X-Forwarded-For is trusted (0 = none). */
  readonly trustedProxyHops: number;
}

const LOOPBACK = new Set(["localhost", "127.0.0.1", "[::1]"]);

export class ConfigError extends Error {
  readonly problems: readonly string[];

  constructor(problems: readonly string[]) {
    super(`Frontend configuration is invalid:\n- ${problems.join("\n- ")}`);
    this.problems = problems;
    this.name = "ConfigError";
  }
}

type Env = Readonly<Record<string, string | undefined>>;

export function parseConfig(env: Env): ServerConfig {
  const problems: string[] = [];

  const rawUrl = (env.CJI_API_BASE_URL ?? "").trim() || DEFAULT_API_BASE_URL;
  let apiBaseUrl = rawUrl;
  try {
    const url = new URL(rawUrl);
    if (url.protocol !== "http:" && url.protocol !== "https:") {
      problems.push("CJI_API_BASE_URL must be an http or https URL.");
    } else if (url.username || url.password || url.search || url.hash) {
      problems.push("CJI_API_BASE_URL must not contain credentials, a query or a fragment.");
    }
    apiBaseUrl = url.origin + url.pathname.replace(/\/+$/, "");
    if (env.NODE_ENV === "production" && url.protocol === "http:" && !LOOPBACK.has(url.hostname)) {
      problems.push("CJI_API_BASE_URL must use https in production unless the API is on this host (loopback).");
    }
  } catch {
    problems.push("CJI_API_BASE_URL is not a valid URL.");
  }

  const sessionSecret = env.CJI_SESSION_SECRET ?? "";
  if (sessionSecret.length < MIN_SECRET_LENGTH) {
    problems.push(
      `CJI_SESSION_SECRET must be at least ${MIN_SECRET_LENGTH} random characters ` +
        "(node -e \"console.log(require('crypto').randomBytes(32).toString('base64url'))\").",
    );
  }

  const previous = (env.CJI_SESSION_SECRET_PREVIOUS ?? "").trim();
  if (previous && (previous.length < MIN_SECRET_LENGTH || previous === sessionSecret)) {
    problems.push(
      `CJI_SESSION_SECRET_PREVIOUS must be the previous key (at least ${MIN_SECRET_LENGTH} characters, ` +
        "different from CJI_SESSION_SECRET), or unset.",
    );
  }

  let trustedProxyHops = 0;
  const rawHops = (env.CJI_FRONTEND_TRUSTED_PROXY_HOPS ?? "").trim();
  if (rawHops) {
    const value = Number(rawHops);
    if (!Number.isInteger(value) || value < 0 || value > 5) {
      problems.push("CJI_FRONTEND_TRUSTED_PROXY_HOPS must be an integer between 0 and 5.");
    } else {
      trustedProxyHops = value;
    }
  }

  let timeoutMs = DEFAULT_TIMEOUT_MS;
  const rawTimeout = (env.CJI_API_TIMEOUT_MS ?? "").trim();
  if (rawTimeout) {
    const value = Number(rawTimeout);
    if (!Number.isInteger(value) || value < 100 || value > 120_000) {
      problems.push("CJI_API_TIMEOUT_MS must be an integer between 100 and 120000.");
    } else {
      timeoutMs = value;
    }
  }

  if (problems.length > 0) {
    throw new ConfigError(problems);
  }
  return { apiBaseUrl, sessionSecret, sessionSecretPrevious: previous || null, timeoutMs, trustedProxyHops };
}
