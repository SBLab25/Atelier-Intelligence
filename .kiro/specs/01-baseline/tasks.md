# Spec 01 — Baseline and Onboarding: Tasks

Scope: Prompt 0 only. Later Specs get their own `requirements.md`, `design.md` and `tasks.md`
when they start (design §6). `[x]` means the evidence exists in `evidence/`. A check that could
not run is recorded as NOT RUN, never as passed.

## Tasks

- [x] **T1 Read inputs.** All named documents and the three process documents; selected `cji_agent/` modules. Coverage limits: requirements §1.
- [x] **T2 Create branch** `phase-01-baseline` from `main` at `8523e47`. Log: `a1-git-branch.log`.
- [x] **T3 Build a reproducible environment.** uv CPython 3.12.13; venv at `C:\Users\sovan\.venvs\cji-baseline-312`; 196 packages installed, exit 0. Logs: `a2`–`a6`, `constraints-baseline-2026-10-27.txt`.
- [x] **T4 Run tests.** 127 passed, 1 collection error (B-01), 2 integration deselected; integration run offline: 2 failed (B-02). Logs: `b2`, `b3`, `b3b`, `b3-pytest-junit.xml`.
- [x] **T5 Run lint, type and security checks (report-only).** ruff 266, mypy 52, bandit 0 high / 25 medium / 300 low, pip-audit 30 advisories in 8 packages. Logs: `b1`, `b4`–`b6`.
- [x] **T6 Smoke-test entry points.** MCP servers start; demo pipeline (default journey: B-03; overridden: works); ingest (B-04, B-05); collector (B-06); Streamlit health check. Logs: `c1`–`c6`, `c3b`, `c4b`, `c5b`.
- [x] **T7 Confirm no runtime source changed.** git status identical before and after (`b0`, `b7`, `c7`, `c8`); tracked `events.parquet` hash unchanged; `git diff --check` exit 0.
- [x] **T8 Record startup commands, versions, install requirements, ports, storage, environment variables.** requirements §3–§8.
- [x] **T9 Record conflicts and the baseline failure register.** design §4–§5.
- [x] **T10 Map the roadmap to the owner's Prompt order and assign every finding.** design §6.
- [ ] **T11 Owner review** of the three files. Blocking: the guide (§6) says to review all three artifacts before allowing implementation.
- [ ] **T12 Owner decisions** OD-14, OD-15, OD-18, OD-19. Blocking for Spec 02.

## Gate evidence

| Check | Command | Exit | Result |
|---|---|---|---|
| Environment | `uv venv … --python 3.12` + `uv pip install -r requirements.txt -r requirements-dev.txt` | 0 | 3.12.13, 196 packages |
| Unit tests | `pytest tests -m "not integration" --continue-on-collection-errors` | 1 | 127 passed, 1 error (B-01) |
| Integration | `pytest tests -m integration` (offline) | 1 | 2 failed, environmental (B-02) |
| Lint | `ruff check . --statistics` | 1 | 266 findings (B-07) |
| Types | `mypy . --exclude .venv` | 1 | 52 errors (B-08) |
| Security | `bandit -r . -x ./.venv` | 1 | 0 high, 25 medium (B-09) |
| Dependencies | `pip-audit -r constraints… --no-deps --disable-pip` | 1 | 30 advisories (B-10) |
| MCP servers | `python run_servers.py` | — | 8001–8005 listening |
| Demo pipeline | `main.py --mode demo --run --auto-approve` | 0 | Analyses nothing (B-03) |
| Demo pipeline | same, with `JOURNEY_NAME=user_onboarding` | 0 | Report generated, 49 s |
| Ingest | `main.py --ingest --file probe.csv --run --auto-approve` | 0 | 404 on 8004 (B-04) |
| Collector | `uvicorn collector.api:app` / `uvicorn cji_agent.collector.api:app` | — | Import errors (B-06) |
| Streamlit | `streamlit run dashboard.py --server.headless true` | — | `/_stcore/health` = ok |
| Syntax | `ast.parse` ×56; `node --check` ×2 | 0 | Clean |
| Repo unchanged | `git status --short` before and after; `git diff --check` | 0 | Identical; clean |
| NOT RUN | realtime mode, real LLM calls, browser session, `--generate-data`, approval resume | — | Need PostgreSQL, keys, a browser, or would overwrite tracked data |

## Rules for every later Spec (from this baseline)

1. Run tests and smoke checks with the protected environment (requirements §8). For a demo
   pipeline run, also set `JOURNEY_NAME=user_onboarding` until Spec 03 resolves D-31.
2. Compare against the B register (design §4). A failure not on it is new: log it as F-xx.
3. Use the baseline venv `C:\Users\sovan\.venvs\cji-baseline-312` or rebuild from
   `constraints-baseline-2026-10-27.txt`.
4. Stage files by name. `.kiro/` and the process documents stay out of git.
5. Never run `--generate-data` or the test suite with a real `DATABASE_URL`.
