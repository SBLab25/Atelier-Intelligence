# Spec 13 — Next.js Foundation: Design

Implements requirements.md (OD-128 to OD-141). The frontend is a Next.js App Router application whose server is the
only client of `/api/v1` (backend-for-frontend); the browser receives HTML and a session cookie it cannot read.

## 1. Layout

```
frontend/
  package.json  package-lock.json  tsconfig.json  next.config.ts  eslint.config.mjs
  vitest.config.ts  vitest.setup.ts  playwright.config.ts  .env.example  README.md
  scripts/api-check.mjs                 regenerate schema.ts to a temp file and compare (OD-132)
  scripts/bundle-scan.mjs               no secret / server variable name in .next/static (OD-133)
  src/
    proxy.ts                            session gate + nonce CSP + security headers (OD-131, OD-136)
    lib/config.ts                       server-only env validation (OD-133)
    lib/session.ts                      seal/open JWE cookie, cookie options, expiry (OD-130)
    lib/redirects.ts                    safeNext() for ?next= (OD-131)
    lib/api/schema.ts                   generated from cji_agent/openapi/v1.json
    lib/api/client.ts                   openapi-fetch client, Result<T>, Problem mapping, request ids (OD-132, OD-141)
    lib/api/loaders.ts                  one typed loader per view; requires the session; 401 -> end session
    app/layout.tsx                      html lang, skip link, shell (header, nav, main)
    app/login/page.tsx + actions.ts     token form; Server Actions signIn / signOut
    app/(protected)/layout.tsx          requires session (second layer), renders the signed-in label
    app/(protected)/page.tsx            status: /health, /health/details, /me
    app/(protected)/journeys/page.tsx, [journeyId]/page.tsx   list; detail with metrics + friction summary
    app/(protected)/runs/page.tsx, [runId]/page.tsx           list with status filter; detail with steps, report
    app/(protected)/**/loading.tsx      placeholders; error.tsx (unexpected exceptions); not-found.tsx
    app/reports/[reportId]/route.ts     streams report HTML from the API (session required, API CSP + sandbox)
    components/                         Shell, Nav, ProblemPanel, RetryButton, EmptyState, Loading, StatusBadge,
                                        DataTable, FrictionSummary, KeyValue
  tests/                                Vitest unit and component tests
  e2e/smoke.spec.ts                     the one browser smoke test
  e2e/fixture-api.ts                    fixture backend (typed with schema.ts), fault switch for the smoke test
```

## 2. Request flow

1. `proxy.ts` (all paths except `_next/static`, `_next/image`, `favicon.ico`): create a nonce, set CSP and security
   headers. For any path except `/login` and static assets, open the session cookie; if missing, invalid or
   expired, redirect to `/login?next=<path+query>` (and delete a bad cookie). `/reports/*` follows the same rule.
2. Protected layout calls `requireSession()` again (server-side, reads the cookie through `next/headers`); no
   session → `redirect('/login')`.
3. Pages call loaders in `lib/api/loaders.ts`; loaders call the typed client with `Authorization: Bearer <token>`
   and `X-Request-ID`; they return `Result<T>`. On `401` they delete the session and `redirect('/login?reason=expired')`.
4. Pages render data or `ProblemPanel`; independent regions are wrapped in `Suspense` so one failing region does not
   hide the others (status page: health, details, me).

## 3. Session (OD-130)

- Payload `{v: 1, token, tokenId, label, role, journeys, iat, exp}`; sealed with `jose` `EncryptJWT`
  (`alg: "dir"`, `enc: "A256GCM"`), key = SHA-256 of `CJI_SESSION_SECRET` (32 bytes). `exp` = min(now + 8 h, token
  expiry when the API reports one — `/me` has no expiry today, so 8 h).
- Cookie `cji_session`: `HttpOnly; Secure; SameSite=Strict; Path=/; Max-Age=28800`. Browsers accept `Secure`
  cookies on `http://localhost`; other plain-HTTP hosts are not supported by design.
- Sign-in Server Action: validates the token shape (`cji_api_` prefix, ≤128 chars) before calling `/me`; on 401 the
  form shows "This token is not valid or has been revoked" (no API detail echo of the input); on 429/5xx it shows
  the problem panel. Success → `redirect(safeNext(next))`. The token field uses `type="password"`,
  `autocomplete="off"`. Server Actions check the `Origin` header (Next.js default) — together with `SameSite=Strict`
  this covers CSRF for sign-in and sign-out.
- Sign-out Server Action deletes the cookie and redirects to `/login`. Rotating `CJI_SESSION_SECRET` ends all sessions.

## 4. API client (OD-132, OD-141)

- `schema.ts` from `openapi-typescript ../cji_agent/openapi/v1.json`. `client.ts` creates `createClient<paths>()`
  with `baseUrl = CJI_API_BASE_URL`, `cache: "no-store"` and an `AbortSignal.timeout(CJI_API_TIMEOUT_MS)`.
- `call()` maps responses: 2xx → `{ok: true, data}`; problem+json → `{ok: false, problem}` with
  `{status, code, title, detail, requestId, retryAfter?, errors?}`; network failure or timeout →
  `{ok: false, problem: {status: 503, code: "backend_unreachable", …}}` (no exception text); a body that is not a
  problem → `code: "unexpected_response"`.
- Loaders: `getHealth` (no token), `getHealthDetails`, `getMe`, `listJourneys`, `getJourney`, `getMetrics`,
  `getFriction`, `listRuns(status?)`, `getRun`, `getReport`; `fetchReportContent` for the route handler.

## 5. Views (OD-134, OD-135, OD-140)

| Route | Regions | Empty state | Notes |
|---|---|---|---|
| `/` | API health; component status table; signed-in token | — | Health is public; details and me need the session. |
| `/journeys` | Journey table (id, steps count, mode) | "No journeys are visible to your token." | Links to detail. |
| `/journeys/[journeyId]` | Steps; metrics summary (overall completion, funnel table); friction summary (score per step, critical badge from `is_critical`, critical steps list, threshold) | "No events in this window." | Window: API default (30 days); 403/404 → problem panel with link back. |
| `/runs` | Runs table (id, journey, status, updated, report link) with a status filter (`<select>` in a GET form, works without JS) | "No runs yet." | Only the first page (limit 50) in this slice; "more runs exist" note when `next_cursor` is set. |
| `/runs/[runId]` | Status, approval flag, active flag, steps table, failure, report link | — | Report link → `/reports/[id]` (opens the sandboxed HTML). |
| `/reports/[reportId]` | Route handler | — | Pattern-checks the id, requires the session, returns the API body with `Content-Type: text/html`, the API CSP plus `sandbox`, `nosniff`, `no-store`; API problems → HTML error page with request id. |

## 6. Components and accessibility (OD-137)

- `Shell`: skip link to `#main`, `<header>` with product name, `<nav aria-label="Main">` (current page
  `aria-current="page"`), signed-in label "label (role)", sign-out button; `<main id="main" tabIndex={-1}>`.
- `ProblemPanel` (`role="alert"`, heading with the title, detail, `code`, request id in `<code>`, retry hint for
  429) + `RetryButton` (client component: `useTransition` + `router.refresh()`, disabled with `aria-busy` while
  pending). `EmptyState` (`role="status"`). `Loading` (`role="status" aria-live="polite"`, visually hidden text).
- `StatusBadge` shows text plus a shape/color; `DataTable` requires a caption and uses `th scope`.
- CSS: one global stylesheet with system fonts, focus outlines, high-contrast colors (WCAG AA), reduced motion.

## 7. Tests (OD-138)

Vitest (jsdom for components, node for lib):

| File | Covers |
|---|---|
| `tests/config.test.ts` | Missing/short secret, bad URL, defaults, no `NEXT_PUBLIC_` use. |
| `tests/session.test.ts` | Seal/open round trip; tampered cookie, other key, expired, wrong version rejected. |
| `tests/redirects.test.ts` | `safeNext`: relative paths kept; `//evil`, `https://…`, `/\evil`, encoded variants → `/`. |
| `tests/client.test.ts` | Mocked fetch: 2xx, each problem status, 429 `Retry-After`, non-problem body, network error, timeout; `X-Request-ID` and bearer header sent; token never in the returned problem. |
| `tests/proxy.test.ts` | No cookie → redirect with `next`; bad cookie → redirect and cookie deleted; valid → pass; `/login` public; CSP nonce present. |
| `tests/components/*.test.tsx` | ProblemPanel, RetryButton, EmptyState, StatusBadge, FrictionSummary (renders API flags as given), Shell; axe-core: no violations. |
| `tests/views/*.test.tsx` | Each page with mocked loaders: success, empty, problem, 403/404 messages; axe-core. |
| `npm run api:check` | Generated schema equals the snapshot. |

Playwright (`e2e/smoke.spec.ts`, Chrome channel, one test with steps): fixture API on a free port, `next start` on
port 3100 with test env; steps listed in requirements OD-138; the fixture API counts authenticated calls made before
sign-in (must be 0) and exposes `/__fault` to fail the next friction call with 503. axe on login and journey detail.
`E2E_LIVE_API_URL` + `E2E_LIVE_TOKEN` switch the backend to a real `cji-api` (fault step skipped).

## 8. Gate (T8)

`gate_spec13.ps1`: `npm ci` (network, clean process) → `npm run api:check`, `typecheck`, `lint`, `test`, `build`,
`bundle-scan`, `test:e2e` (fixture) → start `cji-api` with demo data and a fresh token, `test:e2e` live →
`npm audit --omit=dev` (recorded) → Python suite (`pytest -m "not integration"`), `ruff`, openapi snapshot check
(no Python change expected) → `git diff --check`, save `spec13-tracked.patch` and new-file copies.

## 9. Risks

| Risk | Mitigation |
|---|---|
| Next.js 16 API details (request proxy, async `cookies()`) differ from older docs | Read the installed version's docs in `node_modules/next/dist/docs` before coding; type check catches signature drift. |
| Nonce CSP breaks hydration | Smoke test fails on console CSP violations; Next.js applies the nonce from the request header. |
| Playwright with system Chrome on another machine | `PLAYWRIGHT_CHANNEL` override; documented `npx playwright install chromium` fallback. |
| Token typed into a form passes through the browser once | Password field, no autocomplete, HTTPS outside localhost, never echoed or stored client-side; OIDC later. |

## 10. Rollback

Delete `frontend/` and the README section; revert the `.gitignore` lines. Nothing else changes.
