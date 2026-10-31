"""
Spec 06 removals (OD-34): copy each file to evidence/removed/, verify the copy,
then delete it. Writes the root .gitignore for run logs. Idempotent.
"""
from __future__ import annotations

import hashlib
import pathlib
import shutil

REPO = pathlib.Path(__file__).resolve().parents[5]
EVIDENCE = pathlib.Path(__file__).resolve().parents[1]
REMOVED = EVIDENCE / "removed"
FILES = [
    "check_parquet.py", "inspect_schemas.py", "query_test.py", "test_data_server.py",
    "test_duckdb_async.py", "test_load.py", "test_server.py", "test_threads.py",
    "err.log", "error.log", "out.log", "stderr.log", "main_log.txt", "main_log2.txt",
    "main_log3.txt", "main_log4.txt", "main_log5.txt", "ingest_ga4_log.txt",
    "parquet_check.txt", "schema_report.txt",
    "cji_agent/fix.py", "cji_agent/test_duckdb.py", "cji_agent/test_metadata_query.py",
    "cji_agent/test_pg.py", "cji_agent/test_servers.py", "cji_agent/verify_data.py",
    "cji_agent/dashboard2.py",
]
GITIGNORE = """# Run output at the repository root (Spec 06, OD-34)
/*.log
/main_log*.txt
"""


def sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    lines = []
    for rel in FILES:
        src = REPO / rel
        dst = REMOVED / rel
        if not src.exists():
            lines.append(f"absent   {rel} (copy present: {dst.exists()})")
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        if sha(src) != sha(dst):
            raise SystemExit(f"copy mismatch for {rel}; nothing deleted")
        digest = sha(src)[:16]
        src.unlink()
        lines.append(f"removed  {rel}  sha256={digest}")
    gi = REPO / ".gitignore"
    if not gi.exists():
        gi.write_text(GITIGNORE, encoding="utf-8")
        lines.append("created  .gitignore")
    else:
        lines.append(".gitignore exists; left unchanged")
    (EVIDENCE / "t2-removed.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
