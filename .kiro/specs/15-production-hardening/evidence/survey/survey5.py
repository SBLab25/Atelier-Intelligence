import re
from pathlib import Path

ROOT = Path(r"c:\Users\sovan\Documents\Projects\TCS-CJI")
APP = ROOT / "cji_agent"
SRC = APP / "src/cji"
out = []


def grep(rel: Path, pat: str, limit: int = 30) -> None:
    rx = re.compile(pat)
    n = 0
    for i, line in enumerate(rel.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        if rx.search(line):
            out.append(f"{rel.relative_to(ROOT)}:{i}: {line.strip()[:170]}")
            n += 1
            if n >= limit:
                break


grep(SRC / "tools/ingest_json.py", r"to_sql|CREATE|tracking_events|if_exists")
grep(SRC / "api/idempotency.py", r"connect|path|db|ttl|expire|class ")
grep(SRC / "settings/load.py", r'"CJI_MODE"|choice\("CJI_MODE"|LANGCHAIN_PROJECT|dotenv|\.env')
grep(SRC / "api/app.py", r"idempot|IdempotencyStore|checkpoints_db|limiter|RateLimiter")
for name in ("test_workflow.py", "test_packaging.py", "test_collector.py", "test_api_contract.py", "test_api_units.py",
             "test_repositories.py"):
    grep(APP / "tests" / name, r"subprocess|\.kill\(|terminate\(|Popen|pgserver|signal\.", 12)
grep(SRC / "api/middleware.py", r"x-forwarded|forwarded|client\b|_client", 10)
grep(SRC / "collector/security.py", r"forwarded|hops|class |def ", 20)
grep(SRC / "settings/model.py", r"rate_per|max_body|max_upload|max_active|timeout|run_max|price", 40)
spec09 = ROOT / ".kiro/specs/09-durable-workflow/tasks.md"
if spec09.exists():
    grep(spec09, r"(?i)kill|crash|recover|resume", 12)
Path(r"C:\Users\sovan\.kiro\s15_survey5.txt").write_text("\n".join(out).encode("ascii", "replace").decode(),
                                                        encoding="ascii")
print("ok")
