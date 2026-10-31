// Spec 13, OD-133: nothing secret or server-only reaches browser code.
// Scans the built client assets (.next/static) for the session secret value, the configuration variable names, the
// API base URL and API token material. Run after `npm run build` with the same environment.
import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const staticDir = join(root, ".next", "static");

function files(dir) {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    return statSync(path).isDirectory() ? files(path) : [path];
  });
}

const needles = ["CJI_SESSION_SECRET", "CJI_API_BASE_URL", "CJI_API_TIMEOUT_MS", "cji_api_", "Bearer "];
const secret = process.env.CJI_SESSION_SECRET;
if (secret) {
  needles.push(secret);
}
const apiUrl = process.env.CJI_API_BASE_URL;
if (apiUrl) {
  needles.push(apiUrl);
}

let scanned = 0;
const hits = [];
for (const file of files(staticDir)) {
  const text = readFileSync(file, "latin1");
  scanned += 1;
  for (const needle of needles) {
    if (text.includes(needle)) {
      hits.push(`${relative(root, file)}: ${needle === secret ? "<session secret>" : needle}`);
    }
  }
}
if (hits.length > 0) {
  console.error(`bundle-scan: ${hits.length} finding(s) in client assets:\n  ${hits.join("\n  ")}`);
  process.exitCode = 1;
} else {
  console.info(`bundle-scan: ${scanned} client files scanned, no secret, server variable, API URL or token found`);
}
