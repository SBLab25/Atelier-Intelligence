# Recovery suite (Spec 15, OD-169)

Real processes on loopback ports with a temporary home; the database cases use their own PostgreSQL.
Generated from the gate's `RECOVERY_LOG`: 7 of 7 cases passed.

| Case | Expected | Observed | Result |
|---|---|---|---|
| database outage | readiness 503 and requests 503 while PostgreSQL is down; ready again without a restart | during outage {'api_ready': 503, 'api_metrics': 503, 'collector_ready': 503, 'collect': 503}; recovered=True; after {'api_metrics': 200, 'collect': 200} | pass |
| MCP server killed during a run | run failed at the report step; after the server is back, resume completes | status after kill=failed failure={'worker': 'report_worker', 'code': 'connect_failed', 'message': "could not connect to MCP service 'cji-report' (connect_failed)", 'retryable': True, 'attempts': 1}; resume HTTP 202; final=completed  | pass |
| API killed during a background run | after a restart the run is resumable and completes | killed while running; after restart status=running active=False; resume HTTP 202; final=completed | pass |
| LLM provider unreachable | run completes; insights and narrative carry provenance source=fallback | final=completed; insight sources=['fallback']; narrative source=fallback | pass |
| reports directory unwritable | report step fails with a failure code; after the fix resume completes and writes the report | paused=awaiting_approval; approval HTTP 202; status=failed failure={"worker": "report_worker", "code": "report_write_failed", "message": "report export failed (report_write_failed): reports directory is not usable: Cannot create a file when that file already exists", "retryable": true, "attempts": 1}; a new run meanwhile: HTTP 202, ended failed report_write_failed; resume HTTP 202; final=completed; reports=1 | pass |
| corrupt token file | authenticated requests 503 service_misconfigured and readiness 503; normal again once the file is restored, without a restart | before 200; broken {'request': 503, 'ready': 503}; restored ok=True | pass |
| rate-limit flood | 429 with Retry-After once the per-token limit is used; 200 after the wait | statuses [200, 200, 200, 200, 200, 429, 429, 429]; Retry-After 12s; after the wait 200 | pass |
