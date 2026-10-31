# CJI frontend (Next.js)

Web frontend for Customer Journey Intelligence on the `/api/v1` backend (`cji-api`). Spec 13: a thin, read-only
slice: status, journeys with the friction summary, workflow runs and report status. The Streamlit dashboard stays
available for comparison.

## Run

```bash
cd frontend
npm ci                                  # exact versions from package-lock.json
cp .env.example .env.local              # set CJI_SESSION_SECRET (32+ random characters)
npm run build && npm start              # http://localhost:3000
```

`cji-api` must be reachable at `CJI_API_BASE_URL` (default `http://127.0.0.1:8006`). Sign in with a token from
`cji-api-token create --label <name> --role viewer --journey <journey>`. Development server: `npm run dev`.

| Variable | Default | Meaning |
|---|---|---|
| `CJI_API_BASE_URL` | `http://127.0.0.1:8006` | Backend base URL; used by the Next.js server only. |
| `CJI_SESSION_SECRET` | none (required) | Key of the encrypted session cookie, 32+ characters. Changing it signs everyone out. |
| `CJI_API_TIMEOUT_MS` | `10000` | Timeout of one backend request. |

There are no `NEXT_PUBLIC_` variables: nothing from the configuration is sent to the browser.

## Security model

- **Backend-for-frontend.** The browser talks only to the Next.js server. The server calls `/api/v1` with the
  user's token; the token never reaches browser JavaScript.
- **Session.** After sign-in (`GET /api/v1/me` checks the token) the token is stored in the `cji_session` cookie,
  encrypted (JWE `dir`/`A256GCM`, key from `CJI_SESSION_SECRET`), `HttpOnly`, `Secure`, `SameSite=Strict`, at most
  8 hours. Sign-out deletes it; an API 401 ends it.
- **Protected routes.** `src/proxy.ts` redirects every request without a valid session to `/login`; every data
  loader checks the session again. `?next=` only accepts same-origin paths.
- **Headers.** Per-request nonce Content-Security-Policy, `frame-ancestors 'none'`, `nosniff`, `no-referrer`.
  Report HTML is served through `/reports/<id>` with the API's CSP plus `sandbox`.
- **No business logic here.** Scores, critical steps, statuses and funnels are shown as the API returns them.

## Checks

```bash
npm run typecheck     # tsc --noEmit, strict
npm run lint          # ESLint: Next.js, TypeScript, strict jsx-a11y
npm test              # api:check (types match ../cji_agent/openapi/v1.json) + Vitest unit/component tests
npm run test:e2e      # next build + one Playwright smoke test against a fixture API (installed Chrome)
npm run bundle:scan   # after a build: no secret, server variable or token in .next/static
```

- `npm run api:generate` regenerates `src/lib/api/schema.ts` after the backend contract changes.
- The smoke test runs `next start` on port 3100 and a fixture API on port 18006. Set
  `E2E_LIVE_API_URL=http://127.0.0.1:8006` and `E2E_LIVE_TOKEN=<token>` to run it against a real `cji-api`; the
  fault-injection step is skipped in that mode.
- Playwright uses the installed Chrome (`PLAYWRIGHT_CHANNEL=msedge` for Edge). Without either, run
  `npx playwright install chromium` and set `PLAYWRIGHT_CHANNEL=chromium`.

## Layout

```
src/proxy.ts                  session gate, CSP and security headers
src/lib/config*.ts            server-only configuration
src/lib/session*.ts           encrypted session cookie
src/lib/api/                  generated schema, typed client, problems, loaders
src/app/                      pages: /login, /, /journeys, /journeys/[id], /runs, /runs/[id], /reports/[id]
src/components/, src/views/   accessible components and per-page views (loading, empty, error states)
tests/                        Vitest tests; e2e/ Playwright smoke test and fixture API
```
