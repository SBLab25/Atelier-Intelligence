/**
 * Server log lines (Spec 15, OD-159). In production (`next start`) one JSON object per line with named fields, the
 * same shape as the Python services; otherwise `[cji-frontend] event key=value`. Values are data: messages are never
 * built from user input, and callers must not pass tokens or cookies.
 */
export type Level = "info" | "warning" | "error";
type Fields = Readonly<Record<string, string | number | boolean | null | undefined>>;

export function formatLine(level: Level, event: string, fields: Fields, production: boolean, now: Date = new Date()): string {
  if (production) {
    const entry: Record<string, unknown> = {
      ts: now.toISOString(),
      level: level.toUpperCase(),
      logger: "cji.frontend",
      message: event,
      service: "cji-frontend",
    };
    for (const [key, value] of Object.entries(fields)) {
      if (value !== undefined) {
        entry[key] = value;
      }
    }
    return JSON.stringify(entry);
  }
  const parts = Object.entries(fields)
    .filter(([, value]) => value !== undefined)
    .map(([key, value]) => `${key}=${String(value)}`);
  return ["[cji-frontend]", event, ...parts].join(" ");
}

export function log(level: Level, event: string, fields: Fields = {}): void {
  const line = formatLine(level, event, fields, process.env.NODE_ENV === "production");
  if (level === "error") {
    console.error(line);
  } else if (level === "warning") {
    console.warn(line);
  } else {
    console.info(line);
  }
}
