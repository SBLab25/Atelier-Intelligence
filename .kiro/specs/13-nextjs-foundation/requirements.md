# Spec 13 — Next.js Foundation: Requirements

Source: `kiro_upgrade_prompts.md`, Prompt 12 ("Create the Next.js frontend foundation against the tested /api/v1
contract"); guide row "13 Next.js Foundation" and §10 "Spec 13". Builds on Spec 12 (the `/api/v1` contract, its
OpenAPI snapshot `cji_agent/openapi/v1.json`, token roles and problem responses) and Spec 04 (service registry:
`frontend` = port 3000).

**Status:** written 2026-10-28; approved (defaults OD-128 to OD-141); **implemented** 2026-10-29, gate passed (record, findings G-1 to G-3 and deviations D-1 to D-8 in tasks.md).

## 1. Current state (surveyed after Spec 12)

There is no frontend code in the repository: no `package.json` outside the Python virtual environment, no Node
entries in `.gitignore`. Users see data through the Streamlit dashboard (`cji-dashboard`, 1386 lines, direct SQL and
`data/last_run.json`), the CLI and, since Spec 12, `cji-api`.

Evidence: `evidence/survey/` (`survey.py`/`survey.txt`: tools, repository layout, the API operations;
`versions.py`/`versions.txt`: current npm package versions, engines and peer ranges).

### Findings

| ID | Finding | Source |
|---|---|---|
| F-64 | **No frontend exists.** The registry reserves `frontend` on port 3000 (Spec 04); `cji-api` allows `http://localhost:3000` and `http://127.0.0.1:3000` as CORS origins in development (OD-126). | survey.txt |
| F-65 | **The API credential is a bearer token** (`cji_api_…`, role and journey list, optional expiry). A token readable by browser JavaScript would be exposed to any XSS for its whole lifetime, and a browser calling the API directly needs CORS and holds the token in memory or storage. | `cji.api.auth` |
| F-66 | **Toolchain:** Node 24.18.1, npm 11.16.0; no pnpm or yarn. Chrome and Edge are installed; no Playwright browser download exists. The working shell has the protected environment (dead proxy), so package installs run in a separate process with network access; tests and builds run offline. | survey.txt |
| F-67 | **Latest versions do not fit together.** TypeScript 7.0.2 is outside the peer ranges of `typescript-eslint` 8.72 (`<6.1.0`) and `openapi-typescript` 7.13 (`^5.x`); ESLint 10 is outside `eslint-plugin-jsx-a11y` 6.10 (`≤9`). Next.js 16.4.3 needs Node ≥20.9; Vitest 5 and jsdom 30 need Node ≥22.12. | versions.txt |
| F-68 | **The contract is machine-readable:** OpenAPI 3.1, 15 operations, every error `application/problem+json` with `code` and `request_id`; report content is `text/html` with a restrictive CSP. Typed models can be generated from the snapshot instead of written by hand. | `openapi/v1.json` |
| F-69 | **Production error pages hide server messages.** In a Next.js production build an error thrown in a Server Component reaches `error.tsx` only as a digest, so API problems must be returned as values to stay visible. | Next.js docs |

## 2. Decisions (defaults; confirm or change before implementation)

| ID | Topic | Default | Rejected alternatives |
|---|---|---|---|
| OD-128 | Location and package manager | New top-level `frontend/` (sibling of `cji_agent/`), **npm** with a committed-style `package-lock.json`, `npm ci` for installs, `engines.node >=22.12`. Runs on its own: `npm ci && npm run build && npm start`. | Inside `cji_agent/` (a Python package); pnpm/yarn (not installed); a monorepo tool (one app). |
| OD-129 | Versions | Next.js 16.4, React 19.3, **TypeScript 5.9** (latest 5.x, F-67), ESLint 9 with `eslint-config-next` 16 and `eslint-plugin-jsx-a11y`, Vitest 5 + jsdom + Testing Library, Playwright 1.64 using the **installed Chrome** (`channel: "chrome"`, no browser download). Exact versions in `package.json` (no ranges) plus the lockfile. | Latest TypeScript 7 / ESLint 10 (break the lint and codegen tools); Jest (slower ESM setup); downloading Playwright browsers. |
| OD-130 | Authentication | **Server-side session (backend-for-frontend).** The login page takes an API token issued with `cji-api-token`; a Server Action checks it with `GET /api/v1/me` and stores it in an encrypted cookie `cji_session` (JWE `dir`/`A256GCM` with `jose`, key from `CJI_SESSION_SECRET`): `HttpOnly`, `Secure`, `SameSite=Strict`, `Path=/`, 8 h maximum and never longer than the token's own expiry. All API calls run on the Next.js server; browser JavaScript never receives the token. Logout deletes the cookie. | Token in `localStorage` or a readable cookie and browser-side fetch (XSS exposes it, F-65); OIDC (no identity provider yet; later Spec); NextAuth/Auth.js (a framework for one credential type). |
| OD-131 | Protected routes | Two layers: the Next.js request proxy (`proxy.ts`) redirects requests without a valid session to `/login?next=<path>`, and every data loader requires the session again. An API 401 deletes the session and redirects to `/login?reason=expired`. `next` accepts only same-origin relative paths. | Proxy-only checks (one bypass exposes data); client-side guards (data is fetched before the guard runs). |
| OD-132 | Typed API client | `openapi-typescript` generates `src/lib/api/schema.ts` from `../cji_agent/openapi/v1.json` (file kept in the repo); `openapi-fetch` provides typed calls; one wrapper turns non-2xx responses into a typed `Problem`. `npm run api:check` regenerates to a temporary file and fails on any difference; it runs in `npm test`. | Hand-written types (drift); generating a full client SDK (more code, same types). |
| OD-133 | Configuration | Server-only environment: `CJI_API_BASE_URL` (default `http://127.0.0.1:8006`), `CJI_SESSION_SECRET` (required, ≥32 characters), `CJI_API_TIMEOUT_MS` (default 10000). **No `NEXT_PUBLIC_*` variables.** Modules that read them import `server-only`, so importing them into client code fails the build. A test scans the built client bundle for the secret and the variable names. `frontend/.env.example` documents the keys; `.env.local` is ignored. | Public variables for the API URL (not needed: the browser never calls the API); a config file with secrets. |
| OD-134 | Views (read-only slice) | Shell with header, navigation, signed-in token label and role, logout. Pages: `/` status (`/health`, `/health/details`, `/me`), `/journeys`, `/journeys/[id]` (steps, metrics summary, **friction summary**: scores and critical steps exactly as the API returns them), `/runs` (status filter), `/runs/[id]` (steps, failure, report), `/reports/[id]` (route handler that streams the API's report HTML with the API's CSP plus `sandbox`). | Approval, events and insights pages in this slice (POST with idempotency keys and paging belong to Spec 14 parity). |
| OD-135 | Loading, empty, retry, error | Data loaders return `Result<T> = {ok: true, data} \| {ok: false, problem}` instead of throwing (F-69). Each data region: `loading.tsx`/Suspense placeholder with `aria-busy`; an explicit empty message; a `ProblemPanel` (`role="alert"`: title, detail, code, request id; for 429 the `Retry-After` wait) with a **Retry** button (`router.refresh()`). 401 → login; 403 → "not allowed for your token"; 404 → not-found message; unexpected exceptions → `error.tsx` with retry. | Throwing to `error.tsx` (message hidden in production); toasts only (not persistent, not reachable for screen readers). |
| OD-136 | Security headers | The proxy sets a per-request nonce CSP: `default-src 'self'; script-src 'self' 'nonce-…' 'strict-dynamic'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'`, plus `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `X-Frame-Options: DENY`; `poweredByHeader: false`. Report HTML keeps the API's stricter CSP. | Static CSP with `'unsafe-inline'` scripts; no CSP. |
| OD-137 | Accessibility | Semantic landmarks, skip link, one `h1` per page, labelled form fields with error text linked by `aria-describedby`, tables with captions and `scope`, status shown as text (not color only), visible focus, live regions for loading and errors, `lang="en"`. Checked by `eslint-plugin-jsx-a11y`, `axe-core` in component tests (no violations) and `@axe-core/playwright` in the smoke test (no serious or critical violations). | A component library (Radix/shadcn: more dependencies than a six-page slice needs). |
| OD-138 | Tests | **Vitest** unit and component tests: config validation, session seal/open and expiry, safe redirects, problem mapping, API wrapper (mocked fetch), each view's success/empty/error states, axe checks. **One Playwright smoke test** against `next start` and a small **fixture API** (Node, responses typed against the generated schema): unauthenticated redirect, bad token message, sign-in, status, journey list and detail with friction, runs and report status, an injected 503 shown and recovered with Retry, logout. The gate also runs the smoke test against a real `cji-api` with demo data and a real token (fault-injection step skipped). | Mock Service Worker (browser-side mocking does not cover server-side fetches); smoke test only against a live backend (frontend not testable on its own). |
| OD-139 | Streamlit and the Python app | Untouched: `cji-dashboard` stays for comparison until Spec 14. No Python code changes; the README gains a "Frontend" section; repository `.gitignore` gains `frontend/node_modules`, `.next`, Playwright outputs. | Removing or redirecting the dashboard (Spec 14 decides with parity evidence). |
| OD-140 | Business logic | The frontend formats and links only: friction scores, critical flags, statuses and funnels come from the API unchanged; no recomputation or thresholds in TypeScript. A unit test asserts the friction view renders the API's `is_critical` and `critical_steps` as given. | Client-side scoring or sorting rules. |
| OD-141 | Request ids and logging | The server sends `X-Request-ID` on each API call (one id per page request) and shows the API's `request_id` in problem panels; server logs record method, path, status and request id, never the token or cookie. | Logging request headers. |

## 3. Requirements

1. **R1 TypeScript:** `strict: true` plus `noUncheckedIndexedAccess`, `exactOptionalPropertyTypes`,
   `noImplicitOverride`; `npm run typecheck` (`tsc --noEmit`) passes with no errors.
2. **R2 Typed client:** every API call goes through the generated types (OD-132); the generated file matches the
   snapshot (`npm run api:check`).
3. **R3 Configuration:** the server refuses to start or render with a missing/short `CJI_SESSION_SECRET` or an
   invalid `CJI_API_BASE_URL`, with a clear message; no secret or server variable appears in browser code (OD-133).
4. **R4 Authentication boundary:** without a valid session no page except `/login` renders data and no API call is
   made with a token; API 401 ends the session (OD-130, OD-131).
5. **R5 Views:** shell, status, journey list/detail with friction summary, runs and report status (OD-134).
6. **R6 States:** loading, empty, error with retry for every data region; API problems visible with code and request
   id and recoverable without a full reload (OD-135).
7. **R7 Accessibility:** OD-137 checks pass.
8. **R8 Security headers:** OD-136 on every response.
9. **R9 Tests:** `npm run lint`, `npm run typecheck`, `npm test` (unit/component + `api:check`) and
   `npm run test:e2e` (one Playwright smoke test) pass offline.
10. **R10 Independence:** the frontend builds and runs with only Node and `npm ci`; the Python app is not needed
    except as the backend URL; Streamlit keeps working (Python suite unchanged).

## 4. Non-goals

- Feature parity with Streamlit, approval and other mutations, events and insights views (Spec 14).
- OIDC or user accounts (later Spec); multi-instance session stores (sessions are stateless cookies).
- Deployment, containers, observability (Spec 15).

## 5. Acceptance criteria (Prompt 12)

| Criterion | Evidence |
|---|---|
| Type check, lint, unit tests and browser smoke test pass | Gate logs for `npm run typecheck`, `npm run lint`, `npm test`, `npm run test:e2e` (fixture API) and the live run against `cji-api`. |
| Unauthenticated users cannot access protected data | Unit tests of the proxy and loaders; smoke test: every protected path without a session redirects to `/login` and the fixture API records **no** authenticated call; tampered and expired cookies are rejected. |
| API errors are visible and recoverable | Component tests per problem status (401/403/404/422/429/500/503); smoke test: injected 503 shows the problem panel with request id, Retry restores the data. |
