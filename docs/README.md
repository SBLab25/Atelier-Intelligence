# Documentation index

**Current behaviour** is described by the repository `README.md` (checked against the code by
`cji_agent/tests/test_docs.py`). **Changes and decisions** since the baseline are recorded per Spec in
`.kiro/specs/`. The documents in the status table are kept unchanged as history or design intent and carry a
banner saying so (added in Spec 06).

## Current guides

| Document | Use it for |
|---|---|
| `docs/frontend-migration.md` | Moving from Streamlit to the Next.js frontend (Spec 14): running both side by side, what matches, intentional differences, rollback, and what is still open before Streamlit can be retired. |
| `docs/deployment.md` | Installing, upgrading and rolling back CJI on one host behind a TLS proxy (Spec 15). |
| `docs/operations.md` | Limits, AI budgets, secrets and their rotation, development-only behaviour, runbooks (Spec 15). |
| `docs/release-checklist.md` | The generated release check: every production control with result, evidence, owner and blocker (Spec 15). |

## Status of each document

| Document | Status | Use it for |
|---|---|---|
| `Project_Memory.md` | Superseded | Session history up to April 2026. Contradicts itself ("no application code exists" and "98 % complete"). |
| `Project_status.md` | Superseded | Feature summary as of April 2026 (v2.0 smart ingestion). |
| `docs/development_status.md` | Superseded | The stdio/DuckDB deadlock investigation; fixed by moving MCP to SSE. |
| `docs/1-Product-Requirements.md` | Historical design reference | Product intent, personas, functional requirements. |
| `docs/2-User-Stories-and-Acceptance-Criteria.md` | Historical design reference | User stories and original acceptance gates. |
| `docs/3-Information-Architecture.md` | Historical design reference | Information model and navigation intent. |
| `docs/4-System-Architecture.md` | Historical design reference | Layering and design principles. |
| `docs/5-Database-Schema.md` | Historical design reference | Original storage design. |
| `docs/6-API-Contracts.md` | Historical design reference | Original collector and MCP tool contracts (two lines corrected in Spec 02). |
| `docs/7-Monorepo-Structure.md` | Historical design reference | Original file layout and module rules. |
| `docs/8-Scoring-Engine-Spec.md` | Historical design reference | Friction-score algorithm; still matches `mcp_servers/friction_engine_server.py` in intent. |
| `docs/9-Engineering-Score-Definitions.md` | Historical design reference | Metric definitions. |
| `docs/10-Development-Phases.md` | Historical design reference | Original build plan. |
| `docs/11-Environment-and-DevOps.md` | Historical design reference | Original environment design. |
| `docs/12-Testing-Strategy.md` | Historical design reference | Original test plan. |
| `docs/13-Architecture_Diagram.md` | Historical design reference | Early architecture diagram. |
| `Project Details/ARCHITECTURE.md` | Historical design reference | Earlier copy of the architecture document. |
| `Project Details/MVP_TECH_DOC.md` | Historical design reference | Earlier build reference. |
| `Project Details/PRD.md` | Historical design reference | Earlier copy of the PRD. |
| `Project Details/SYSTEM_DESIGN.md` | Historical design reference | Earlier implementation contract. |

Planning inputs at the repository root (`refactoring.md`, `kiro_upgrade_guide.md`, `kiro_upgrade_prompts.md`,
`antigravity_upgrade_prompts.md`, `free_plan_workflow.md`, `project_summary.md`) are working documents for the
refactor and are not covered here.

## Known divergences between the historical documents and the code

| Topic | Historical documents say | Code does (see `README.md`) |
|---|---|---|
| Realtime storage | DuckDB `live_events` table | PostgreSQL (Supabase): `live_events` from the collector and `tracking_events` from file imports |
| MCP transport | stdio, four servers | SSE, five servers on ports 8001–8005 from the service registry (`settings/services.py`); start them with `run_servers.py` |
| Configuration | `config.py` reads `os.getenv` at import; `config.py` imports only stdlib | Typed settings in `settings/` with a service registry; `config.py` is a compatibility facade; `python -m settings check` |
| LLM access | `litellm.completion` with `LLM_MODEL`, Anthropic first | Insight and report servers call the Groq HTTP API directly; ingestion tries Anthropic then Groq; rule-based fallbacks without keys |
| Data access | Mode checks inside each MCP tool | One repository chosen from `CJI_MODE` (`repositories/`, Spec 05); mode mismatch between CLI and servers stops the run |
| Domain types | Separate model definitions per layer | One domain package (`domain/`, Spec 03) |
| Collector | Open admin endpoint, default keys, `POST /collect` | `POST /collect/batch`; fails closed outside development; per-journey keys; admin key required (Spec 02) |
| Dashboard | Reads DuckDB/Parquet | Reads PostgreSQL in both modes plus `data/last_run.json`; upload appends by default (Spec 06) |
| Report | Plotly charts | Chart.js from a CDN; all dynamic HTML escaped (Spec 02) |
| Test layout | `sys.path.insert(0, "..")` in every test file | `tests/conftest.py` sets the path once; packaging is planned for Spec 11 |
| Defaults | `JOURNEY_NAME=onboarding`, `CJI_ADMIN_KEY=change-me-in-production` | `user_onboarding`; shipped admin keys are refused |
