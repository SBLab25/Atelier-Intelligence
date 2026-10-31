import "server-only";
import crypto from "crypto";
import { getDbPool } from "./supabase-auth";
import { log } from "./log";

export interface ApiKeyRecord {
  apiKey: string;
  journeyName: string;
  description: string;
  createdAt: string;
  isActive: boolean;
  isDev?: boolean | undefined;
  accountId?: string | undefined;
}

// In-memory fallback if the remote PostgreSQL database is temporarily offline or in unit tests
let memoryFallbackKeys: ApiKeyRecord[] = [
  {
    apiKey: "cji_dev_localtest",
    journeyName: "*",
    description: "Default Development Key",
    createdAt: new Date().toISOString(),
    isActive: true,
    isDev: true,
  },
];

/**
 * Ensures the api_keys table exists in the PostgreSQL database with account_id isolation column.
 */
export async function ensureApiKeysTable(): Promise<void> {
  try {
    const pool = getDbPool();
    await pool.query(`
      CREATE TABLE IF NOT EXISTS public.api_keys (
        api_key VARCHAR PRIMARY KEY,
        account_id VARCHAR(64),
        journey_name VARCHAR NOT NULL,
        description VARCHAR,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        is_active BOOLEAN DEFAULT true
      );
      ALTER TABLE public.api_keys ADD COLUMN IF NOT EXISTS account_id VARCHAR(64);
      CREATE INDEX IF NOT EXISTS api_keys_account_idx ON public.api_keys(account_id);
    `);
  } catch (err) {
    log("error", "Failed to ensure api_keys table", { error: String(err) });
  }
}

/**
 * Generates a cryptographically secure 36-character live client key: cji_live_{32_hex_chars}.
 */
export function generateLiveKeyString(): string {
  return `cji_live_${crypto.randomBytes(16).toString("hex")}`;
}

/**
 * Lists active API keys. If accountId is provided, filters to that user account.
 * If no active keys exist for this account, auto-provisions a default live client key.
 */
export async function listOrProvisionApiKeys(
  journeyFilter?: readonly string[],
  accountId?: string,
): Promise<ApiKeyRecord[]> {
  try {
    await ensureApiKeysTable();
    const pool = getDbPool();

    let query = `
      SELECT api_key, journey_name, description, created_at, is_active, account_id
      FROM public.api_keys
      WHERE is_active = true
    `;
    const params: unknown[] = [];

    if (accountId) {
      params.push(accountId);
      query += ` AND (account_id = $1 OR account_id IS NULL)`;
    }
    query += ` ORDER BY created_at DESC;`;

    const res = await pool.query<{
      api_key: string;
      journey_name: string;
      description: string | null;
      created_at: Date | string;
      is_active: boolean;
      account_id: string | null;
    }>(query, params);

    if (res.rows.length === 0) {
      // Auto-provision the first key for this account workspace
      const initialKey = await createApiKey({
        journeyName: journeyFilter && journeyFilter[0] && journeyFilter[0] !== "*" ? journeyFilter[0] : "*",
        description: accountId ? `Primary Ingestion Key (${accountId})` : "Primary Ingestion Key (Auto-Provisioned)",
        accountId,
      });
      return [initialKey];
    }

    return res.rows.map((r) => ({
      apiKey: r.api_key,
      journeyName: r.journey_name,
      description: r.description || "Client Ingestion Key",
      createdAt: typeof r.created_at === "string" ? r.created_at : r.created_at.toISOString(),
      isActive: r.is_active,
      isDev: r.api_key.startsWith("cji_dev_") || r.api_key.startsWith("cji_test_"),
      accountId: r.account_id || undefined,
    }));
  } catch (err) {
    log("error", "Error loading api_keys from PostgreSQL, using memory fallback", { error: String(err) });
    return memoryFallbackKeys.filter((k) => k.isActive && (!accountId || !k.accountId || k.accountId === accountId));
  }
}

export interface CreateKeyParams {
  journeyName: string;
  description?: string | undefined;
  accountId?: string | undefined;
}

/**
 * Creates and registers a new cryptographically secure client API key in the database with tenant account isolation.
 */
export async function createApiKey(params: CreateKeyParams): Promise<ApiKeyRecord> {
  const cleanJourney = (params.journeyName || "*").trim().toLowerCase().replace(/\s+/g, "_");
  const desc = (params.description || "Client Ingestion Key").trim();
  const accountId = params.accountId?.trim() || null;
  const newKey = generateLiveKeyString();
  const now = new Date().toISOString();

  try {
    await ensureApiKeysTable();
    const pool = getDbPool();
    await pool.query(
      `INSERT INTO public.api_keys (api_key, account_id, journey_name, description, created_at, is_active)
       VALUES ($1, $2, $3, $4, NOW(), true);`,
      [newKey, accountId, cleanJourney, desc]
    );

    return {
      apiKey: newKey,
      journeyName: cleanJourney,
      description: desc,
      createdAt: now,
      isActive: true,
      isDev: false,
      accountId: accountId || undefined,
    };
  } catch (err) {
    log("error", "Database error inserting api_key, storing in fallback memory", { error: String(err) });
    const memoryRecord: ApiKeyRecord = {
      apiKey: newKey,
      journeyName: cleanJourney,
      description: desc,
      createdAt: now,
      isActive: true,
      isDev: false,
      accountId: accountId || undefined,
    };
    memoryFallbackKeys.unshift(memoryRecord);
    return memoryRecord;
  }
}

/**
 * Revokes / deactivates an API key.
 */
export async function revokeApiKey(apiKey: string): Promise<boolean> {
  const targetKey = apiKey.trim();
  if (!targetKey) return false;

  try {
    const pool = getDbPool();
    const res = await pool.query(
      `UPDATE public.api_keys
       SET is_active = false
       WHERE api_key = $1;`,
      [targetKey]
    );
    if ((res.rowCount ?? 0) > 0) {
      return true;
    }
  } catch (err) {
    log("error", "Database error revoking api_key", { error: String(err) });
  }

  // Update fallback memory as well
  let changed = false;
  memoryFallbackKeys = memoryFallbackKeys.map((k) => {
    if (k.apiKey === targetKey) {
      changed = true;
      return { ...k, isActive: false };
    }
    return k;
  });

  return changed;
}

