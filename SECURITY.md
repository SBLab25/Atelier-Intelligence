# Security Policy & Vulnerability Disclosure

## Supported Versions
Security updates are actively maintained on the latest release and the `main` branch.

| Version | Supported |
| ------- | --------- |
| 1.x / `main` | :white_check_mark: |
| < 1.0   | :x: |

## Reporting a Vulnerability
We take the security of this project and customer telemetry data with enterprise rigor. If you discover a potential vulnerability or credential leak, please report it responsibly:

1. **Do not** open a public issue or discuss the vulnerability publicly.
2. Email details to: `security@cji.io` (or the repository administrator).
3. Include:
   - Type of vulnerability (e.g. CSRF, SQL Injection, Auth Bypass, Tenant Isolation Leak).
   - Step-by-step reproduction instructions or proof of concept.
   - Any suggested mitigations.

## Automated Secret Scanning & Zero-Exposure Policy
- **Strict Git Hygiene**: No `.env`, private keys, database passwords, or tracker API tokens may be checked into version control.
- **Continuous Gate**: Pull requests and commits must pass `python cji_agent/scripts/secret_scan.py` before merging.
- **Tenant Isolation**: Row-level access controls and tenant tokens (`account_id`) are enforced on every database read, stream, and analytical calculation.
