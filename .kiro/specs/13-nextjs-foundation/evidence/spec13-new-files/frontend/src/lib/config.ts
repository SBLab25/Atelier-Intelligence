import "server-only";

import { parseConfig, type ServerConfig } from "./config-core";

export type { ServerConfig } from "./config-core";
export { ConfigError, parseConfig } from "./config-core";

let cached: ServerConfig | undefined;

/** The validated server configuration (OD-133). Throws ConfigError on the first use when it is invalid. */
export function serverConfig(): ServerConfig {
  cached ??= parseConfig(process.env);
  return cached;
}

/** Test hook: forget the cached configuration. */
export function resetServerConfig(): void {
  cached = undefined;
}
