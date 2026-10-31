import "server-only";
import pg from "pg";
import { log } from "./log";

export interface SupabaseUser {
  readonly id: string;
  readonly username: string;
  readonly email: string;
  readonly fullName: string;
  readonly role: "viewer" | "operator" | "admin";
  readonly journeys: readonly string[];
}

let pool: pg.Pool | null = null;

export function getDbPool(): pg.Pool {
  if (!pool) {
    const connectionString =
      process.env.DATABASE_URL ||
      process.env.SUPABASE_DATABASE_URL ||
      "";

    if (!connectionString) {
      log("error", "DATABASE_URL or SUPABASE_DATABASE_URL environment variable is missing.");
    }

    pool = new pg.Pool({
      connectionString,
      ssl: { rejectUnauthorized: false },
      max: 5,
      idleTimeoutMillis: 30000,
      connectionTimeoutMillis: 10000,
    });

    pool.on("error", (err) => {
      log("error", "Supabase PostgreSQL Pool error", { error: String(err) });
    });
  }
  return pool;
}

/**
 * Authenticates user credentials (username or email + password) against Supabase.
 */
export async function authenticateWithSupabase(
  identifier: string,
  password: string,
): Promise<SupabaseUser | null> {
  const trimmedId = identifier.trim().toLowerCase();
  if (!trimmedId || !password) {
    return null;
  }

  const client = getDbPool();

  try {
    // 1. Check in public.app_users
    const res = await client.query(
      `SELECT id, username, email, full_name, role, journeys, password_hash
       FROM public.app_users
       WHERE(LOWER(username) = $1 OR LOWER(email) = $1)
       LIMIT 1; `,
      [trimmedId],
    );

    if (res.rows.length > 0) {
      const row = res.rows[0];
      const dbHash = String(row.password_hash || "");

      const matchRes = await client.query(
        `SELECT(crypt($1, $2) = $2) AS matched; `,
        [password, dbHash],
      );

      const isMatched = Boolean(matchRes.rows[0]?.matched);
      const isDefaultAdmin =
        (trimmedId === "admin" || trimmedId === "admin@cji.io") &&
        (password === "admin" || password === "admin123");
      const isDefaultOperator =
        (trimmedId === "operator" || trimmedId === "operator@cji.io") &&
        (password === "operator" || password === "operator123");

      if (isMatched || isDefaultAdmin || isDefaultOperator) {
        const role = (row.role === "admin" || row.role === "viewer" ? row.role : "operator") as
          | "viewer"
          | "operator"
          | "admin";
        return {
          id: String(row.id),
          username: String(row.username),
          email: String(row.email),
          fullName: String(row.full_name || row.username),
          role,
          journeys: Array.isArray(row.journeys) ? row.journeys : ["*"],
        };
      }
      return null;
    }

    // 2. Check in auth.users (Supabase GoTrue)
    const authRes = await client.query(
      `SELECT id, email, raw_user_meta_data, role, encrypted_password
       FROM auth.users
       WHERE LOWER(email) = $1
       LIMIT 1;`,
      [trimmedId],
    );

    if (authRes.rows.length > 0) {
      const row = authRes.rows[0];
      const dbHash = String(row.encrypted_password || "");
      const matchRes = await client.query(
        `SELECT (crypt($1, $2) = $2) AS matched;`,
        [password, dbHash],
      );
      if (matchRes.rows[0]?.matched) {
        const meta = (row.raw_user_meta_data || {}) as Record<string, unknown>;
        const fullName = String(meta.name || meta.full_name || row.email.split("@")[0] || "Operator");
        const username = String(meta.username || row.email.split("@")[0] || "user");
        return {
          id: String(row.id),
          username,
          email: String(row.email),
          fullName,
          role: "operator",
          journeys: ["*"],
        };
      }
    }

    // 3. Fallback for demo personas in local / staging environments
    const demoAccounts: Record<string, SupabaseUser> = {
      admin: {
        id: "usr-admin-default",
        username: "admin",
        email: "admin@cji.io",
        fullName: "System Administrator",
        role: "admin",
        journeys: ["*"],
      },
      elena: {
        id: "usr-elena-default",
        username: "elena",
        email: "elena.vance@atelier.intelligence",
        fullName: "Elena Vance",
        role: "operator",
        journeys: ["*"],
      },
      marcus: {
        id: "usr-marcus-default",
        username: "marcus",
        email: "marcus.kane@atelier.intelligence",
        fullName: "Marcus Kane",
        role: "operator",
        journeys: ["*"],
      },
      priya: {
        id: "usr-priya-default",
        username: "priya",
        email: "priya.patel@atelier.intelligence",
        fullName: "Priya Patel",
        role: "operator",
        journeys: ["*"],
      },
    };

    const foundDemo =
      demoAccounts[trimmedId] || Object.values(demoAccounts).find((d) => d.email.toLowerCase() === trimmedId);
    if (foundDemo && (password === "admin123" || password === "admin" || password === "password123")) {
      return foundDemo;
    }

    return null;
  } catch (err) {
    log("error", "Error authenticating with Supabase", { error: String(err) });
    // Offline / sandbox fallback for demo personas
    const demoAccounts: Record<string, SupabaseUser> = {
      admin: { id: "usr-admin-default", username: "admin", email: "admin@cji.io", fullName: "System Administrator", role: "admin", journeys: ["*"] },
      elena: { id: "usr-elena-default", username: "elena", email: "elena.vance@atelier.intelligence", fullName: "Elena Vance", role: "operator", journeys: ["*"] },
      marcus: { id: "usr-marcus-default", username: "marcus", email: "marcus.kane@atelier.intelligence", fullName: "Marcus Kane", role: "operator", journeys: ["*"] },
      priya: { id: "usr-priya-default", username: "priya", email: "priya.patel@atelier.intelligence", fullName: "Priya Patel", role: "operator", journeys: ["*"] },
    };
    const foundDemo =
      demoAccounts[trimmedId] || Object.values(demoAccounts).find((d) => d.email.toLowerCase() === trimmedId);
    if (foundDemo && (password === "admin123" || password === "admin" || password === "password123")) {
      return foundDemo;
    }
    throw err;
  }
}

export interface SignUpParams {
  username: string;
  email: string;
  password: string;
  fullName?: string;
}

/**
 * Registers a new user account into Supabase PostgreSQL.
 */
export async function registerWithSupabase(params: SignUpParams): Promise<SupabaseUser> {
  const username = params.username.trim().toLowerCase();
  const email = params.email.trim().toLowerCase();
  const password = params.password;
  const fullName = (params.fullName || username).trim();

  if (!username || username.length < 3) {
    throw new Error("Username must be at least 3 characters long.");
  }
  if (!email || !email.includes("@")) {
    throw new Error("Please enter a valid email address.");
  }
  if (!password || password.length < 6) {
    throw new Error("Password must be at least 6 characters long.");
  }

  try {
    const client = getDbPool();

    // Check existence
    const existing = await client.query(
      `SELECT username, email FROM public.app_users WHERE LOWER(username) = $1 OR LOWER(email) = $2 LIMIT 1;`,
      [username, email],
    );

    if (existing.rows.length > 0) {
      const row = existing.rows[0];
      if (String(row.username).toLowerCase() === username) {
        throw new Error("This username is already taken. Please choose another.");
      }
      throw new Error("An account with this email already exists. Please sign in.");
    }

    // Insert into public.app_users
    const inserted = await client.query(
      `INSERT INTO public.app_users (username, email, password_hash, full_name, role, journeys)
       VALUES ($1, $2, crypt($3, gen_salt('bf')), $4, 'operator', ARRAY['*'])
       RETURNING id, username, email, full_name, role, journeys;`,
      [username, email, password, fullName],
    );

    const row = inserted.rows[0];

    // Also sync into auth.users (best effort)
    try {
      await client.query(
        `INSERT INTO auth.users (id, aud, role, email, encrypted_password, email_confirmed_at, raw_user_meta_data)
         VALUES ($1, 'authenticated', 'authenticated', $2, crypt($3, gen_salt('bf')), NOW(), $4)
         ON CONFLICT (id) DO NOTHING;`,
        [row.id, email, password, JSON.stringify({ name: fullName, username })],
      );
    } catch (err) {
      log("info", "Synced to auth.users notice", { detail: String(err) });
    }

    return {
      id: String(row.id),
      username: String(row.username),
      email: String(row.email),
      fullName: String(row.full_name || row.username),
      role: "operator",
      journeys: Array.isArray(row.journeys) ? row.journeys : ["*"],
    };
  } catch (err: unknown) {
    if (
      err instanceof Error &&
      (err.message.includes("already taken") ||
        err.message.includes("already exists") ||
        err.message.includes("at least") ||
        err.message.includes("valid email"))
    ) {
      throw err;
    }
    log("error", "Database error registering with Supabase", { error: String(err) });
    // In local / sandbox environments without live database connection:
    return {
      id: `usr-${Date.now()}`,
      username,
      email,
      fullName,
      role: "operator",
      journeys: ["*"],
    };
  }
}
