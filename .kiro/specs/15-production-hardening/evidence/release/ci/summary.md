# CI summary

Run 2026-10-29T13:42:52; stages: format, lint, types, unit, integration, browser, scans.

| Stage | Step | Result | Detail | Seconds |
|---|---|---|---|---|
| format | ruff format --check (ci/formatted.txt) | pass | exit 0 | 0 |
| lint | ruff check | pass | 92 findings (ratchet <= 92) | 0 |
| lint | bandit -c pyproject.toml -r src | pass | Low 25 / Medium 10 / High 0 (ratchet <= 25/10/0) | 2 |
| lint | eslint (npm run lint) | pass | exit 0 | 8 |
| types | mypy (project config) | pass | 33 errors (ratchet <= 33) | 94 |
| types | mypy --strict (strict set) | pass | 0 errors | 49 |
| types | tsc --noEmit (npm run typecheck) | pass | exit 0 | 3 |
| types | api:check (types = openapi/v1.json) | pass | exit 0 | 6 |
| unit | pytest -m 'not integration and not recovery' | pass | 1288 passed, 1 skipped, 9 deselected, 1 warning in 181.01s (0:03:01) | 188 |
| unit | vitest | pass | Tests  138 passed (138) | 31 |
| integration | pytest pgserver + recovery suite | pass | 24 passed in 193.24s (0:03:13) | 196 |
| browser | next build | pass | exit 0 | 16 |
| browser | playwright (fixture API specs) | pass | exit 0 | 51 |
| browser | bundle scan (.next/static) | pass | exit 0 | 1 |
| scans | secret scan (tree and history) | pass | exit 0 | 64 |

Result: PASS (15 of 15 steps passed).
