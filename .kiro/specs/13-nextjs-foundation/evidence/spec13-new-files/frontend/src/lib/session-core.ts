/**
 * Encrypted session cookie (Spec 13, OD-130). The API token lives only inside this JWE (dir + A256GCM); the cookie is
 * HttpOnly, so browser JavaScript can neither read nor change it. Pure functions: used by the request proxy, the
 * server code (`session.ts`) and the tests.
 */
import { EncryptJWT, jwtDecrypt } from "jose";

export const SESSION_COOKIE = "cji_session";
export const SESSION_MAX_AGE_S = 8 * 60 * 60;
const VERSION = 1;
const ROLES = ["viewer", "operator", "admin"] as const;

export type Role = (typeof ROLES)[number];

export interface Session {
  readonly token: string;
  readonly tokenId: string;
  readonly label: string;
  readonly role: Role;
  readonly journeys: readonly string[];
  readonly expiresAt: number; // epoch seconds
}

export interface CookieOptions {
  readonly httpOnly: true;
  readonly secure: true;
  readonly sameSite: "strict";
  readonly path: "/";
  readonly maxAge: number;
}

export function cookieOptions(maxAge: number = SESSION_MAX_AGE_S): CookieOptions {
  return { httpOnly: true, secure: true, sameSite: "strict", path: "/", maxAge };
}

async function keyFor(secret: string): Promise<Uint8Array> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(secret));
  return new Uint8Array(digest);
}

export async function sealSession(
  session: Omit<Session, "expiresAt">,
  secret: string,
  nowS: number = Math.floor(Date.now() / 1000),
): Promise<{ value: string; expiresAt: number }> {
  const expiresAt = nowS + SESSION_MAX_AGE_S;
  const value = await new EncryptJWT({
    v: VERSION,
    token: session.token,
    tid: session.tokenId,
    label: session.label,
    role: session.role,
    journeys: [...session.journeys],
  })
    .setProtectedHeader({ alg: "dir", enc: "A256GCM" })
    .setIssuedAt(nowS)
    .setExpirationTime(expiresAt)
    .encrypt(await keyFor(secret));
  return { value, expiresAt };
}

function isRole(value: unknown): value is Role {
  return typeof value === "string" && (ROLES as readonly string[]).includes(value);
}

/** The session in a cookie value, or null when it is missing, tampered with, sealed with another key or expired. */
export async function openSession(
  value: string | undefined,
  secret: string,
  nowS: number = Math.floor(Date.now() / 1000),
): Promise<Session | null> {
  if (!value || value.length > 8192) {
    return null;
  }
  try {
    const { payload } = await jwtDecrypt(value, await keyFor(secret), {
      currentDate: new Date(nowS * 1000),
      keyManagementAlgorithms: ["dir"],
      contentEncryptionAlgorithms: ["A256GCM"],
    });
    const { v, token, tid, label, role, journeys, exp } = payload as Record<string, unknown>;
    if (
      v !== VERSION ||
      typeof token !== "string" ||
      typeof tid !== "string" ||
      typeof label !== "string" ||
      !isRole(role) ||
      !Array.isArray(journeys) ||
      !journeys.every((j) => typeof j === "string") ||
      typeof exp !== "number"
    ) {
      return null;
    }
    return { token, tokenId: tid, label, role, journeys: journeys as string[], expiresAt: exp };
  } catch {
    return null;
  }
}
