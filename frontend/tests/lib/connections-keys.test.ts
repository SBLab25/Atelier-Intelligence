import { describe, it, expect, vi, beforeEach } from "vitest";
import { generateLiveKeyString, createApiKey, revokeApiKey, listOrProvisionApiKeys } from "@/lib/api-keys";

// Mock supabase-auth to prevent live network connection during unit test
vi.mock("@/lib/supabase-auth", () => {
  return {
    getDbPool: () => ({
      query: vi.fn().mockImplementation((queryText: string) => {
        if (queryText.includes("SELECT api_key")) {
          return Promise.resolve({
            rows: [
              {
                api_key: "cji_live_mocked1234567890abcdef12345678",
                journey_name: "checkout_funnel",
                description: "Test Key",
                created_at: new Date().toISOString(),
                is_active: true,
              },
            ],
          });
        }
        if (queryText.includes("INSERT INTO public.api_keys")) {
          return Promise.resolve({ rowCount: 1 });
        }
        if (queryText.includes("UPDATE public.api_keys")) {
          return Promise.resolve({ rowCount: 1 });
        }
        return Promise.resolve({ rows: [], rowCount: 0 });
      }),
    }),
  };
});

describe("API Keys Management Service", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("generates keys in the exact cji_live_{32_hex_chars} format", () => {
    const key = generateLiveKeyString();
    expect(key).toMatch(/^cji_live_[0-9a-f]{32}$/);
    expect(key.length).toBe(41); // 'cji_live_' (9) + 32 = 41
  });

  it("lists active API keys from the database", async () => {
    const keys = await listOrProvisionApiKeys();
    expect(keys.length).toBeGreaterThanOrEqual(1);
    expect(keys[0]?.apiKey).toBe("cji_live_mocked1234567890abcdef12345678");
    expect(keys[0]?.journeyName).toBe("checkout_funnel");
    expect(keys[0]?.isActive).toBe(true);
  });

  it("creates a new API key with sanitized journey name", async () => {
    const newKey = await createApiKey({
      journeyName: "Cart Checkout",
      description: "My E-Commerce Site Key",
    });

    expect(newKey.apiKey).toMatch(/^cji_live_[0-9a-f]{32}$/);
    expect(newKey.journeyName).toBe("cart_checkout");
    expect(newKey.description).toBe("My E-Commerce Site Key");
    expect(newKey.isActive).toBe(true);
  });

  it("revokes an API key successfully", async () => {
    const revoked = await revokeApiKey("cji_live_mocked1234567890abcdef12345678");
    expect(revoked).toBe(true);
  });
});

