# CJI (Customer Journey Intelligence) - Project Summary

Covers the project's functionality and design, and all work done in the chat sessions up to now.
No secrets or tokens are written here.

## 1. What the project does

CJI analyses how customers move through a product journey (for example `user_onboarding`). It collects events, computes funnel and
friction metrics, runs an agent workflow that produces insights and a report, and shows the results to people.

| Capability | Description |
|---|---|
| Event collection | A FastAPI **collector** (`cji-collector`, port 8000) receives events from a JavaScript tracker (`tracker.js`, `cji-snippet`) with tracker keys, rate limits and CORS rules. Files can also be ingested (`cji-ingest-json`, the web Ingest page). |
| Storage | Postgres/Supabase through `DATABASE_URL`; checkpoints and reports on local disk (`data/`, `reports/`). Migrations: `cji-db`. Backups: `cji-backup`. |
| Analysis | Journey steps, per-step metrics, funnel, friction scores and drill-down (`cji-friction-engine`, `cji-journey-data`). |
| Agent workflow | A LangGraph workflow over five MCP servers (ports 8001-8005, started by `cji-servers`): ingestion intelligence, journey data, friction engine, insight, report. A run goes `running` -> `awaiting_approval` -> `approved` -> `completed` or `failed`. Insights record whether they came from the LLM or a fallback. LLM calls have a budget, retries and deadlines (Groq by default). |
| Backend API | `cji-api` (port 8006) serves a versioned JSON API under `/api/v1` with role-based API tokens (`cji-api-token`): viewer, operator, admin. |
| Web frontend | Next.js app in `frontend/` (port 3000). It signs in with an API token that stays on the server inside an encrypted HttpOnly session cookie. |
| Other front ends | Streamlit dashboard (`cji-dashboard`, port 8501) and the CLI remain available. |
| Operations | `cji-settings check` validates configuration, `cji-ops`, structured JSON logs, health and readiness endpoints, a local CI runner and a release check (`ci/`). |

### Architecture

```
Browser -> Next.js frontend :3000 (server holds the token) -> cji-api :8006 (/api/v1)
                                                                  |-> Postgres / Supabase
                                                                  |-> MCP servers :8001-8005 (LangGraph workflow, LLM)
Tracker (tracker.js) -> collector :8000 -> Postgres
```

### Web pages (`frontend/src/app`)

| Route | Content |
|---|---|
| `/login` | Token sign-in (Atelier design); shows a notice after sign-out or expiry |
| `/` (alias `/dashboard`) | New dashboard: journeys, runs, reports and API status with live data |
| `/journeys`, `/journeys/[id]`, `/journeys/[id]/steps/[step]` | Journey list, funnel, step metrics, friction drill-down, events |
| `/runs`, `/runs/new`, `/runs/[id]` | Start, approve and resume runs; results with insight provenance |
| `/reports` | Report list, preview and download |
| `/ingest` | Event file upload with validation feedback |
| `/healthz`, `/readyz` | Health and readiness |

## 2. Upgrade history (Specs 01-15)

Done as a staged production refactor, one Spec per prompt from `kiro_upgrade_prompts.md`. All uncommitted on branch `phase-02-security`.

- **Specs 01-14:** security hardening, settings and configuration validation, collector hardening, database and migrations, the MCP/LangGraph workflow, the LLM layer, the `/api/v1` backend, the Next.js frontend (Spec 13) and event-file ingestion (Spec 14).
- **Spec 15 - production hardening** (version 0.15.0):
  - Local CI (`ci/run_ci.py`, 15 checks), release check (`ci/release_check.py`), sensitive-data scan, secret scan, rollback drill (using the 0.11.0 wheel), generated `docs/release-checklist.md`.
  - Hand-written metrics and traces. Lint and type ratchets: ruff <= 92, mypy <= 33, bandit H0.
  - The report error no longer leaks the server path; the canary scan found 0 violations.
  - Final gate: CI 15/15, pytest 1288 passed / 1 skipped, integration 24 passed, Vitest 138, parity 31/31, live browser 5/5.
- **Principal-engineer review:** decision was **not ready**. The format failure in `ci/release_check.py` was fixed at your request; the other findings were left open.

**Release check: NOT READY (6 blocked, 0 failed).** These need you:
1. 23 Python advisories (chromadb, langchain-core, langgraph and its checkpoint packages). Version caps in `pyproject.toml` stop upgrades; `ci/exceptions.json` is empty.
2. A live tracker key ("Live Web Demo Key", fingerprint `8aa90e8de3b9c744`) is in git history. Revoke it with `POST /admin/api-keys/revoke` or confirm it is inactive.
3. An example key in `docs/6-API-Contracts.md` (fingerprint `54d5b3115cb8abb1`).
4. Supabase backups and a restore test.
5. `cji-backup create`, then `cji-db migrate up` on the real Supabase database.
6. TLS proxy and process supervision on the host.

Record each item in `ci/owner-evidence.json` (keys: `supabase_backups`, `supabase_migrations`, `release_host`, `tracker_key_history`, `example_key_docs`).

Open review findings (not fixed):
- Streamlit `dashboard.py` uses `unsafe_allow_html` 83 times with 4 escapes.
- Tracker keys are stored in plaintext (`collector/api.py`).
- Concurrent ingest should use `ON CONFLICT DO NOTHING` (`tools/ingest_json.py`).
- Docs need "superseded" banners and env-variable rows; the runs list is limited to 50.

## 3. This session's work (in order)

1. **Spec 15 finished and gated.** Final gate rerun, record written, scratch files deleted.
2. **Started the project** for manual testing.
   - Created `frontend/.env.local` (random session secret, API base URL). It is git-ignored.
   - Created an operator API token for testing (not recorded here).
   - Added `start-cji.ps1` and `stop-cji.ps1` in the project root.
3. **Backend start error fixed.** `CJI_ENV=production` requires `CJI_API_CURSOR_SECRET`. A random value was appended to `cji_agent/.env`; nothing else in that file changed, including `SUPABASE_DATABASE_URL`. `cji-settings check --role api` returns ok. The `COLLECTOR_PORT` / `COLLECTOR_HOST` deprecation warnings are harmless.
4. **New design review.** `front-end/` turned out to be a Vite + React app (an AI Studio export) on task and time-tracking mock data, not Next.js. You chose to port the design into the Next.js app.
5. **Design port into `frontend/`:**
   - Installed Tailwind v4 (`postcss.config.mjs`) and self-hosted fonts (Plus Jakarta Sans, Space Grotesk, Material Symbols) because the content security policy only allows same-origin assets.
   - Your `index.css` became `src/app/atelier.css`. Tailwind's reset is left out and the old `globals.css` was moved into a lower-priority CSS layer with the Atelier palette, so the existing pages keep working.
   - New `AtelierNavbar.tsx` and `Shell.tsx`: pill navigation, a "Signed in as" chip and a confirmed sign-out dialog.
   - New login page and form in the Atelier look, still token-based because the backend has no email/password login.
   - Sign-out now returns to `/login` with a "you have safely signed out" notice.
   - Your original `front-end/src` was copied to `frontend/design-reference/` (excluded from the build); `front-end/` itself is untouched.
6. **New dashboard on real data.** `/` replaced the old Status page (stat cards, journey list, recent runs, latest reports, API status). The nav tab was renamed "Dashboard" and the unit test updated. `/dashboard` redirects to `/`.
7. **Stale server fixed.** The "old dashboard" and "not found" came from a frontend server started before the changes. It was stopped, `.next` was cleared and it was restarted.

**Checks:** typecheck passes, the production build passes, component tests pass (18/18), `/login` serves the new design, and `/dashboard` redirects to the login page when signed out. The signed-in dashboard was not viewed by me. The full Vitest suite and the Playwright e2e specs have not been rerun since the design change; the e2e specs still look for the old "Status" label.

## 4. Design (Atelier)

- **Look:** warm off-white surface (`#fbf9f6`), white rounded cards (24-32 px), a near-black primary (`#050508`) and an amber accent (`#fdbb45` / `#7f5700`). The tokens are in `src/app/atelier.css`.
- **Fonts:** Plus Jakarta Sans for text, Space Grotesk for numbers and labels. Icons use Material Symbols.
- **Layout:** a sticky translucent header with a pill navigation bar. The dashboard uses a hero card, four stat cards and card lists. The login is a centred card with soft glows.
- **Not wired:** the mock-data screens (Analytics, Team, Projects, Time Operations, Intelligence Hub) have no CJI API equivalent. They are kept in `frontend/design-reference/` until you decide how they map to journeys, runs and insights.

## 5. How to run

```powershell
# Both servers in their own windows
cd C:\Users\sovan\Documents\Projects\TCS-CJI
powershell -ExecutionPolicy Bypass -File .\start-cji.ps1
powershell -ExecutionPolicy Bypass -File .\stop-cji.ps1     # stop ports 8006 and 3000

# By hand
cd cji_agent; C:\Users\sovan\.venvs\cji-baseline-312\Scripts\cji-api.exe       # API on 8006
cd frontend;  npm run dev                                                      # frontend on 3000
C:\Users\sovan\.venvs\cji-baseline-312\Scripts\cji-servers.exe                 # MCP servers 8001-8005 (needed for runs)
C:\Users\sovan\.venvs\cji-baseline-312\Scripts\cji-api-token.exe create --label me --role operator --journey user_onboarding
```

Runs that call the LLM also need `GROQ_API_KEY` in `cji_agent/.env` (it is currently unset). Open http://localhost:3000 and sign in with the token.

## 6. Rules followed during this work

- No git commit or push; the project is separate from GitHub.
- The real `SUPABASE_DATABASE_URL` was never read, used or removed.
- Tests run in a protected environment (dead proxy, dummy keys and database URLs).
- Streamlit and the CLI are kept.
- Checks are reported as passed only when they ran.
- You asked for low-token, fast work because of limited credits.
