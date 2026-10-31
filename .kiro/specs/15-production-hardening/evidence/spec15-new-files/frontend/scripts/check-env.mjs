// npm run check:env (Spec 15, OD-171): validate the Next.js server configuration before starting it.
// Reads the process environment, then .env.production.local / .env.local (process values win), and applies the
// same rules as the server (src/lib/config-core.ts, loaded with Node's TypeScript type stripping).
// Exit 0 when valid, 1 with one line per problem otherwise. Never prints a value.
import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("..", import.meta.url));
const env = { NODE_ENV: "production" };
for (const name of [".env.local", ".env.production.local"]) {
  const path = `${root}${name}`;
  if (!existsSync(path)) {
    continue;
  }
  for (const line of readFileSync(path, "utf8").split(/\r?\n/)) {
    const match = /^\s*([A-Z0-9_]+)\s*=\s*(.*?)\s*$/.exec(line);
    if (match && !line.trimStart().startsWith("#")) {
      env[match[1]] = match[2].replace(/^(['"])(.*)\1$/, "$2");
    }
  }
}
Object.assign(env, Object.fromEntries(Object.entries(process.env).filter(([key]) => key.startsWith("CJI_"))));

const { ConfigError, parseConfig } = await import("../src/lib/config-core.ts");
try {
  const config = parseConfig(env);
  console.info(`frontend configuration ok (API ${new URL(config.apiBaseUrl).host}, trusted proxy hops ${config.trustedProxyHops})`);
} catch (exc) {
  if (!(exc instanceof ConfigError)) {
    throw exc;
  }
  for (const problem of exc.problems) {
    console.error(`- ${problem}`);
  }
  process.exit(1);
}
