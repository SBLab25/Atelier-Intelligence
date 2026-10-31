# Moving from Streamlit to the Next.js frontend

Spec 14 (frontend parity). The Next.js frontend (`frontend/`, port 3000) now covers ingestion with validation,
journey and funnel analytics, friction drill-down, run start, approval and resume, insights with provenance, and
report preview and download. **Streamlit (`cji-dashboard`, port 8501) and the CLI (`cji`) are unchanged and stay
available as the operational fallback.** Nothing is removed in Spec 14; §6 lists what is still open before Streamlit
can be retired.

## 1. Run the three side by side

| Service | Start | Port | Reads |
|---|---|---|---|
| API | `cji-api` | 8006 | the configured repository (demo: Parquet, realtime: PostgreSQL), the checkpoint store, `reports/` |
| Next.js | `cd frontend && npm ci && npm run build && npm start` | 3000 | only the API (`CJI_API_BASE_URL`) |
| Streamlit | `cji-dashboard` | 8501 | PostgreSQL directly and `data/last_run.json` |
| MCP servers | `cji-servers` (as for the CLI) | see `cji-settings` | needed by runs started from Next.js or the CLI |

Sign in to Next.js with an API token: `cji-api-token create --label me --role operator --journey user_onboarding`
(viewer: read only; operator: start, approve, resume, validate and append files; admin: also replace all events).

## 2. Feature map

| Feature | Streamlit | CLI | Next.js page | API |
|---|---|---|---|---|
| Ingestion | sidebar upload, writes at once | `cji-ingest-json`, `cji --ingest` | `/ingest`: validate → review → write | `POST /ingestions/validations`, `POST /ingestions` |
| Journey and funnel | Overview, Journey pages | — | `/journeys/[id]` with window selector | `/journeys/{id}/metrics` |
| Friction drill-down | Friction page | — | `/journeys/[id]/steps/[step]` | `/friction`, `/events` (operator), `/insights` |
| Start a run | Run button (blocking, auto-approve) | `cji --run [--auto-approve]` | `/runs/new` | `POST /runs` |
| Approval, resume | — | `--approve`, `--resume` | buttons on `/runs/[id]` | `POST /runs/{id}/approval`, `/resume` |
| Insights, provenance | Insights page | report footer | `/runs/[id]` results | `GET /runs/{id}/results` |
| Reports | 8 newest, download | path printed | `/reports`, preview and download | `/reports`, `/reports/{id}/content?disposition=attachment` |
| Business KPIs, audience, heatmaps, track selector | Overview, Journey | — | **not available** | — |

## 3. Intentional differences

1. **Numbers come from the engine, not from Streamlit's SQL** (OD-142). Streamlit queries `tracking_events`,
   `live_events` and `demo_events` with no time window; Next.js shows the API's repository data for a chosen window
   (default 30 days). Measured on the demo events (45,283 rows, `evidence/parity/streamlit-diff.md`):
   - users per step are identical on the same rows (1,489 → 234 for the 8 steps);
   - Streamlit's "Avg Errors" is a count of error events (e.g. 296 at `sign_up_form`), the engine reports an error
     rate per user (22.17 %);
   - Streamlit's dwell averages all events including zero-duration ones (6.2 s at `sign_up_form`), the engine
     averages per user (19.1 s);
   - **friction**: Streamlit's fallback formula (used when `last_run.json` is missing) marks no step critical
     (highest 40.5 at `email_verification`); the engine marks 4 critical (`sign_up_form` 72, `email_verification`
     90, `plan_selection` 63, `payment_info` 85; threshold 60). Next.js always shows the engine's scores.
2. **No rule-based "insights".** Streamlit fills the Insights page with fixed sentences when no run exists (F-72).
   Next.js shows only stored run insights, each labelled: written by the language model (model, provider), fallback
   text (with the gateway's reason), or not recorded (runs from before Spec 14).
3. **Ingestion validates first.** The same parser runs, but nothing is written until the user confirms; dropped
   rows (event types outside the taxonomy) and repaired timestamps are counted. Uploads are limited to 10 MiB
   (Streamlit: 200 MB); larger files go through `cji-ingest-json`. Replacing all events needs the admin role and a
   confirmation. Unreadable timestamps are now really set to the write time (F-81: the in-place fill had no effect
   under pandas copy-on-write, so such rows were stored without a time; this also changes Streamlit and the CLI).
4. **Runs are not blocking.** Streamlit waits up to 180 s for `cji --run --auto-approve`; Next.js starts the run in
   the API process, shows it at once and refreshes every 5 s. Approval is a separate step unless "approve
   automatically" is ticked. One run per API process at a time (`CJI_API_MAX_ACTIVE_RUNS`).
5. **Reports open in a sandboxed tab** (no scripts) and can be downloaded; the list is paged instead of 8 newest.
6. **Roles.** Streamlit has none. In Next.js, actions a token cannot perform stay visible but disabled with the role
   they need; events are listed for operators only.
7. **`last_run.json`** is still written by CLI runs only. Runs started or approved through the API do not update it,
   so Streamlit can show an older run than Next.js (F-79).

## 4. Parity tolerances (requirements §4)

| Value | Compared | Tolerance | Evidence |
|---|---|---|---|
| Run status, steps, approval | Next.js ↔ API ↔ `cji --status` | identical | `evidence/parity/parity.txt` |
| Friction scores, critical steps, insights, fixes, narrative of a run | API ↔ checkpoint ↔ `last_run.json` (CLI run) | identical | same |
| Live metrics, funnel, completion | API ↔ `services.analytics` | identical | same |
| Live friction | API ↔ `score_steps` on the same metrics | identical | same |
| Displayed values | page ↔ API JSON | percentages 1 decimal, counts integers, dwell seconds 1 decimal | Playwright `journey.spec.ts`, `live.spec.ts` |
| Streamlit SQL panels | Streamlit ↔ engine | not ported; measured above | `streamlit-diff.md` |

## 5. Rollback and fallback

- **Rollback of the frontend:** stop the Next.js process. Nothing else depends on it.
- **Rollback of the new API write operations:** set `CJI_API_WRITE_OPERATIONS=false` and restart `cji-api`.
  `POST /runs`, `POST /runs/{id}/resume`, `POST /ingestions/validations` and `POST /ingestions` are then not
  served (404, or 405 where a GET exists on the same path); reading, approval (Spec 12) and Streamlit are unaffected.
- **Interrupted runs:** a run driven by the API stops when the API process stops. Its checkpoint stays; resume it from
  its Next.js page or with `cji --resume --thread-id <run id>`.
- **Operational fallback:** every capability of Streamlit and the CLI is unchanged: `cji-dashboard`, `cji --run`,
  `cji --approve`, `cji --resume`, `cji --status`, `cji-ingest-json`.

## 6. Retiring Streamlit: checklist

| Condition (Prompt 13) | Status after Spec 14 |
|---|---|
| Core results match documented tolerances | Met for demo data (`parity.txt`); not yet repeated on realtime PostgreSQL data |
| Migration and rollback instructions exist | Met (this document) |
| Browser and integration tests pass | Met in the Spec 14 gate (see `.kiro/specs/14-frontend-parity/tasks.md`) |
| Users have an operational fallback | Met while Streamlit and the CLI stay |
| Open | Decide whether business KPIs, audience, heatmaps and the track selector move to the API and Next.js or are dropped; repeat the parity check on realtime data |
