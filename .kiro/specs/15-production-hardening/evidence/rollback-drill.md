# Rollback drill

`python ci/rollback_drill.py` (Spec 15, OD-175), 2026-10-29 13:48, 3.6 min. Result: **PASS**.

| Flag | Result | Detail |
|---|---|---|
| restore_equal | pass | 3 tables equal=True, token file equal=True, create/verify/restore exit 0/0/0 |
| schema_rollback_ok | pass | versions up/down/up 2/1/2; 0.11.0 on version 1: completed |
| release_rollback_ok | pass | 0.11.0 completed, 0.15.0 completed (same=True), 0.11.0 again completed (same=True) |
| old_frontend_ok | pass | pre-Spec 15 frontend build + smoke test against the 0.15.0 API: passed |
| write_switch_ok | pass | CJI_API_WRITE_OPERATIONS=false: writes refused, reads served |

| # | Step | Command | Exit | Detail |
|---|---|---|---|---|
| 1 | build wheel 0.15.0 | `C:\Users\sovan\.venvs\cji-baseline-312\Scripts\python.exe -m pip wheel --no-deps --no-index --no-build-isolation -q -w C:\Users\sovan\.kiro\s15_gate_tmp\drill\w` | 0 |  |
| 2 | venv-old: create venv | `C:\Users\sovan\.venvs\cji-baseline-312\Scripts\python.exe -m venv C:\Users\sovan\.kiro\s15_gate_tmp\drill\venv-old` | 0 |  |
| 3 | venv-old: install cji_agent-0.11.0-py3-none-any.whl | `C:\Users\sovan\.kiro\s15_gate_tmp\drill\venv-old\Scripts\python.exe -m pip install --no-deps --no-index --no-cache-dir --disable-pip-version-check -q <repo>\.ki` | 0 |  |
| 4 | venv-old: installed version | `C:\Users\sovan\.kiro\s15_gate_tmp\drill\venv-old\Scripts\python.exe -c import importlib.metadata as m, cji, pathlib, sys; print(m.version('cji-agent'), pathlib.` | 0 | 0.11.0 True |
| 5 | venv-new: create venv | `C:\Users\sovan\.venvs\cji-baseline-312\Scripts\python.exe -m venv C:\Users\sovan\.kiro\s15_gate_tmp\drill\venv-new` | 0 |  |
| 6 | venv-new: install cji_agent-0.15.0-py3-none-any.whl | `C:\Users\sovan\.kiro\s15_gate_tmp\drill\venv-new\Scripts\python.exe -m pip install --no-deps --no-index --no-cache-dir --disable-pip-version-check -q C:\Users\s` | 0 |  |
| 7 | venv-new: installed version | `C:\Users\sovan\.kiro\s15_gate_tmp\drill\venv-new\Scripts\python.exe -c import importlib.metadata as m, cji, pathlib, sys; print(m.version('cji-agent'), pathlib.` | 0 | 0.15.0 True |
| 8 | demo events shifted to end 10 minutes ago | `-` | 0 | 45283 events spanning 29 days 23:18:15.686000; realtime window 43200 minutes |
| 9 | 0.11.0: cji-ingest-json events.csv | `C:\Users\sovan\.kiro\s15_gate_tmp\drill\venv-old\Scripts\python.exe -m cji.tools.ingest_json C:\Users\sovan\.kiro\s15_gate_tmp\drill\events.csv` | 0 | 13:45:20 \| INFO     \| [ingest] Wrote 45,283 rows -> PostgreSQL tracking_events (append) |
| 10 | 0.11.0: rows ingested | `count(*) tracking_events` | 0 | 45283 rows (file 45283) |
| 11 | token (operator) | `C:\Users\sovan\.kiro\s15_gate_tmp\drill\venv-old\Scripts\python.exe -m cji.api.tokens_cli --file C:\Users\sovan\.kiro\s15_gate_tmp\drill\sys-0.11.0-before\home\` | 0 | token created (value not recorded) |
| 12 | 0.11.0-before: analysis run | `POST /runs (auto_approve) + GET results, metrics` | 0 | status=completed failure=None; results HTTP 200; metrics HTTP 200 |
| 13 | cji-backup create | `C:\Users\sovan\.kiro\s15_gate_tmp\drill\venv-new\Scripts\python.exe -m cji.ops.backup --database-url-env DRILL_DATABASE_URL --pg-bin C:\Users\sovan\.venvs\cji-b` | 0 | 2026-10-29T13:45:59 \| cji.audit            \| INFO     \| {"action": "backup.create", "actor": "sovan", "kind": "security", "outcome": "ok", "rows": 45284, "service": "cji-backup", "target": "cji-backup-20261029T081557Z", "ts": "2026-10-29T08:15:59.193+00:00"} |
| 14 | cji-backup verify | `C:\Users\sovan\.kiro\s15_gate_tmp\drill\venv-new\Scripts\python.exe -m cji.ops.backup --pg-bin C:\Users\sovan\.venvs\cji-baseline-312\Lib\site-packages\pgserver` | 0 | backup verified |
| 15 | 0.15.0: cji-db migrate up | `C:\Users\sovan\.kiro\s15_gate_tmp\drill\venv-new\Scripts\python.exe -m cji.ops.db_cli --database-url-env DRILL_DATABASE_URL migrate up` | 0 | 2026-10-29T13:46:01 \| cji.audit            \| INFO     \| {"action": "migration.apply", "actor": "cji-db", "kind": "security", "mode": "up", "outcome": "ok", "service": "cji-db", "target": "0002_indexes", "ts": "2026-10-29T08:16:01.898+00:00"} |
| 16 | 0.15.0: schema version after up | `C:\Users\sovan\.kiro\s15_gate_tmp\drill\venv-new\Scripts\python.exe -m cji.ops.db_cli --database-url-env DRILL_DATABASE_URL migrate status --json` | 0 | } |
| 17 | token (operator) | `C:\Users\sovan\.kiro\s15_gate_tmp\drill\venv-new\Scripts\python.exe -m cji.api.tokens_cli --file C:\Users\sovan\.kiro\s15_gate_tmp\drill\sys-0.15.0\home\data\ap` | 0 | token created (value not recorded) |
| 18 | 0.15.0: analysis run | `POST /runs (auto_approve) + GET results, metrics` | 0 | status=completed failure=None; results HTTP 200; metrics HTTP 200 |
| 19 | 0.15.0 result = 0.11.0 result | `compare normalised results` | 0 | 3342 bytes compared, equal=True |
| 20 | token (viewer) | `C:\Users\sovan\.kiro\s15_gate_tmp\drill\venv-new\Scripts\python.exe -m cji.api.tokens_cli --file C:\Users\sovan\.kiro\s15_gate_tmp\drill\sys-0.15.0\home\data\ap` | 0 | token created (value not recorded) |
| 21 | old frontend: link node_modules | `cmd /c mklink /J C:\Users\sovan\.kiro\s15_gate_tmp\drill\frontend-old\node_modules <repo>\frontend\node_modules` | 0 | Junction created for C:\Users\sovan\.kiro\s15_gate_tmp\drill\frontend-old\node_modules <<===>> C:\Users\sovan\Documents\Projects\TCS-CJI\frontend\node_modules |
| 22 | old frontend: next build | `node node_modules/next/dist/bin/next build` | 1 |     at <unknown> (https://nextjs.org/docs/app/api-reference/config/next-config-js/turbopack#root-directory) |
| 23 | old frontend: next build (copied node_modules) | `node node_modules/next/dist/bin/next build` | 0 | ƒ  (Dynamic)  server-rendered on demand |
| 24 | old frontend: smoke test against the 0.15.0 API | `C:\Program Files\nodejs\npx.cmd playwright test smoke.spec.ts` | 0 |   1 passed (7.1s) |
| 25 | token (operator) | `C:\Users\sovan\.kiro\s15_gate_tmp\drill\venv-new\Scripts\python.exe -m cji.api.tokens_cli --file C:\Users\sovan\.kiro\s15_gate_tmp\drill\sys-write-off\home\data` | 0 | token created (value not recorded) |
| 26 | configuration rollback | `CJI_API_WRITE_OPERATIONS=false: POST /runs, GET /runs` | 0 | POST /runs HTTP 405 (expected 404/405); GET /runs HTTP 200 |
| 27 | cji-db migrate down --to 1 | `C:\Users\sovan\.kiro\s15_gate_tmp\drill\venv-new\Scripts\python.exe -m cji.ops.db_cli --database-url-env DRILL_DATABASE_URL migrate down --to 1` | 0 | 2026-10-29T13:47:38 \| cji.audit            \| INFO     \| {"action": "migration.apply", "actor": "cji-db", "kind": "security", "mode": "down", "outcome": "ok", "service": "cji-db", "target": "0002_indexes", "ts": "2026-10-29T08:17:38.030+00:00"} |
| 28 | schema version after down | `C:\Users\sovan\.kiro\s15_gate_tmp\drill\venv-new\Scripts\python.exe -m cji.ops.db_cli --database-url-env DRILL_DATABASE_URL migrate status --json` | 0 | } |
| 29 | token (operator) | `C:\Users\sovan\.kiro\s15_gate_tmp\drill\venv-old\Scripts\python.exe -m cji.api.tokens_cli --file C:\Users\sovan\.kiro\s15_gate_tmp\drill\sys-0.11.0-after-rollba` | 0 | token created (value not recorded) |
| 30 | 0.11.0-after-rollback: analysis run | `POST /runs (auto_approve) + GET results, metrics` | 0 | status=completed failure=None; results HTTP 200; metrics HTTP 200 |
| 31 | 0.11.0 after rollback = 0.11.0 before | `compare normalised results` | 0 | 3342 bytes compared, equal=True |
| 32 | cji-db migrate up (again) | `C:\Users\sovan\.kiro\s15_gate_tmp\drill\venv-new\Scripts\python.exe -m cji.ops.db_cli --database-url-env DRILL_DATABASE_URL migrate up` | 0 | 2026-10-29T13:48:14 \| cji.audit            \| INFO     \| {"action": "migration.apply", "actor": "cji-db", "kind": "security", "mode": "up", "outcome": "ok", "service": "cji-db", "target": "0002_indexes", "ts": "2026-10-29T08:18:14.867+00:00"} |
| 33 | schema version after the second up | `C:\Users\sovan\.kiro\s15_gate_tmp\drill\venv-new\Scripts\python.exe -m cji.ops.db_cli --database-url-env DRILL_DATABASE_URL migrate status --json` | 0 | } |
| 34 | cji-backup restore (fresh database and home) | `C:\Users\sovan\.kiro\s15_gate_tmp\drill\venv-new\Scripts\python.exe -m cji.ops.backup --database-url-env DRILL_RESTORE_URL --pg-bin C:\Users\sovan\.venvs\cji-ba` | 0 | 2026-10-29T13:48:17 \| cji.audit            \| INFO     \| {"action": "backup.restore", "actor": "sovan", "kind": "security", "outcome": "ok", "rows": 45284, "service": "cji-backup", "target": "cji-backup-20261029T081557Z", "ts": "2026-10-29T08:18:17.782+00:00"} |
| 35 | restore = source | `table_facts (rows, checksum) and token file hash` | 0 | tables equal: {'tracking_events': True, 'live_events': True, 'api_keys': True}; api_tokens.json equal: True |
