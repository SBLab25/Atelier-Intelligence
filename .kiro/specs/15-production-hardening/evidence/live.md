# Live phase (gate C)

- cji-db migrate up: exit 0
- cji-ingest-json demo events: exit 0
- processes started; API and collector ready: True
- collector: admin with a wrong key HTTP 403; key create HTTP 200; marker batch HTTP 200
- API: bad token HTTP 401; ingestion validate HTTP 201, write HTTP 201; run awaiting_approval -> approve HTTP 202 -> completed; reports listed 1
- next build (marker session key): exit 0
- browser tests against the live API (smoke + live): exit 0 ['5 passed (13.4s)']
- Next.js page with a sealed session HTTP 200; /readyz HTTP 200
- rotation: {'api_token': {'rotate_exit': 0, 'old_after': 401, 'new_after': 200}, 'tracker_key': {'revoke': 200, 'batch_after': 401}}
- metrics: ok=True missing={'api': [], 'collector': [], 'cji-insight': []}
- cji-ops status: exit 0 -> 1 after stopping cji-insight
- cji-backup create exit 0, restore exit 0
- logs: ok=True 333 lines; not JSON or missing fields: none; request gate-run-cf51d005c644 -> run 964d022a-497e-4c48-8dbc-1b59a0f33410: 24 API lines, 3 MCP lines; Next.js trace 6627d0d5732b4799ad9b7f5936d178e3 in 3 API lines
- trace: ok=True services=['cji-friction-engine', 'cji-journey-data', 'cji-report', 'workflow']
- audit: ok=True 22 records, 13 actions; missing: none; forbidden fields: none
