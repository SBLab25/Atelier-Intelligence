// Gate helper (Spec 15): seal a session cookie for an API token with the frontend's own code, so the gate can call
// Next.js pages directly (trace-propagation check) without driving the sign-in form.
// Input (environment): CJI_SESSION_SECRET, SEAL_TOKEN, SEAL_TOKEN_ID, SEAL_LABEL, SEAL_ROLE, SEAL_JOURNEYS (comma list).
// Output: the cookie value on stdout. Run with cwd = frontend/ (node --disable-warning=ExperimentalWarning).
import { pathToFileURL } from "node:url";
import { resolve } from "node:path";

const core = pathToFileURL(resolve(process.cwd(), "src/lib/session-core.ts")).href;
const { sealSession } = await import(core);
const env = process.env;
const sealed = await sealSession(
  {
    token: env.SEAL_TOKEN ?? "",
    tokenId: env.SEAL_TOKEN_ID ?? "",
    label: env.SEAL_LABEL ?? "gate",
    role: env.SEAL_ROLE ?? "viewer",
    journeys: (env.SEAL_JOURNEYS ?? "").split(",").filter(Boolean),
  },
  env.CJI_SESSION_SECRET ?? "",
);
process.stdout.write(sealed.value);
