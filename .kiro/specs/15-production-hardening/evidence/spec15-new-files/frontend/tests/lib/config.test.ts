// @vitest-environment node
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

import { ConfigError, DEFAULT_API_BASE_URL, DEFAULT_TIMEOUT_MS, parseConfig } from "@/lib/config-core";

const SECRET = "s".repeat(32);

describe("parseConfig", () => {
  it("uses the defaults with only a secret", () => {
    expect(parseConfig({ CJI_SESSION_SECRET: SECRET })).toEqual({
      apiBaseUrl: DEFAULT_API_BASE_URL,
      sessionSecret: SECRET,
      sessionSecretPrevious: null, // Spec 15
      timeoutMs: DEFAULT_TIMEOUT_MS,
      trustedProxyHops: 0, // Spec 15
    });
  });

  it("normalises the base URL", () => {
    const config = parseConfig({ CJI_SESSION_SECRET: SECRET, CJI_API_BASE_URL: "https://api.example.test/cji/" });
    expect(config.apiBaseUrl).toBe("https://api.example.test/cji");
  });

  it.each([
    [{}, "CJI_SESSION_SECRET"],
    [{ CJI_SESSION_SECRET: "short" }, "CJI_SESSION_SECRET"],
    [{ CJI_SESSION_SECRET: SECRET, CJI_API_BASE_URL: "not a url" }, "CJI_API_BASE_URL"],
    [{ CJI_SESSION_SECRET: SECRET, CJI_API_BASE_URL: "ftp://x.test" }, "CJI_API_BASE_URL"],
    [{ CJI_SESSION_SECRET: SECRET, CJI_API_BASE_URL: "http://user:pw@x.test" }, "CJI_API_BASE_URL"],
    [{ CJI_SESSION_SECRET: SECRET, CJI_API_TIMEOUT_MS: "fast" }, "CJI_API_TIMEOUT_MS"],
    [{ CJI_SESSION_SECRET: SECRET, CJI_API_TIMEOUT_MS: "5" }, "CJI_API_TIMEOUT_MS"],
  ])("rejects %j", (env, key) => {
    let error: unknown;
    try {
      parseConfig(env);
    } catch (exc) {
      error = exc;
    }
    expect(error).toBeInstanceOf(ConfigError);
    expect((error as ConfigError).problems.join(" ")).toContain(key);
    expect((error as ConfigError).message).not.toContain("short");
  });
});

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    return statSync(path).isDirectory() ? sourceFiles(path) : /\.(ts|tsx)$/.test(name) ? [path] : [];
  });
}

describe("no public configuration", () => {
  it("never reads NEXT_PUBLIC_ variables (OD-133)", () => {
    const offenders = sourceFiles(join(import.meta.dirname, "..", "..", "src")).filter((file) =>
      readFileSync(file, "utf8").includes("NEXT_PUBLIC_"),
    );
    expect(offenders).toEqual([]);
  });

  it("guards every module that reads secrets with server-only", () => {
    const src = join(import.meta.dirname, "..", "..", "src");
    for (const rel of ["lib/config.ts", "lib/session.ts", "lib/api/loaders.ts"]) {
      expect(readFileSync(join(src, rel), "utf8").startsWith('import "server-only";'), rel).toBe(true);
    }
  });
});
