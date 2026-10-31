// Spec 13, OD-132: the generated API types must match the backend's OpenAPI snapshot.
// Regenerates src/lib/api/schema.ts into a temporary file and compares it with the committed one.
import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const snapshot = join(root, "..", "cji_agent", "openapi", "v1.json");
const committed = join(root, "src", "lib", "api", "schema.ts");
const dir = mkdtempSync(join(tmpdir(), "cji-api-check-"));
const fresh = join(dir, "schema.ts");
const cli = join(root, "node_modules", "openapi-typescript", "bin", "cli.js");

try {
  execFileSync(process.execPath, [cli, snapshot, "--output", fresh], { stdio: "pipe" });
  const normalise = (text) => text.replace(/\r\n/g, "\n");
  if (normalise(readFileSync(fresh, "utf8")) !== normalise(readFileSync(committed, "utf8"))) {
    console.error("src/lib/api/schema.ts is out of date with ../cji_agent/openapi/v1.json; run: npm run api:generate");
    process.exitCode = 1;
  } else {
    console.info("api:check: src/lib/api/schema.ts matches ../cji_agent/openapi/v1.json");
  }
} finally {
  rmSync(dir, { recursive: true, force: true });
}
