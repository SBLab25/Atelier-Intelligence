/**
 * Server start (Spec 15, OD-171): stop a production server whose configuration is invalid, instead of failing on the
 * first request. Development and tests keep the per-request check (the page explains the problem).
 */
export async function register(): Promise<void> {
  if (process.env.NEXT_RUNTIME !== "nodejs" || process.env.NODE_ENV !== "production") {
    return;
  }
  const { ConfigError, parseConfig } = await import("./lib/config-core");
  const { log } = await import("./lib/log");
  try {
    parseConfig(process.env);
  } catch (exc) {
    if (exc instanceof ConfigError) {
      for (const problem of exc.problems) {
        log("error", "configuration invalid", { problem });
      }
      process.exit(1);
    }
    throw exc;
  }
}
