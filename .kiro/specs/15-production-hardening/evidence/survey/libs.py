import importlib.metadata as md
import re
from pathlib import Path

SP = Path(r"C:\Users\sovan\.venvs\cji-baseline-312\Lib\site-packages")
out = []
for dist in ("fastmcp", "mcp", "uvicorn", "starlette", "fastapi", "pgserver", "pip-audit", "ruff", "SQLAlchemy",
             "psycopg2-binary", "langgraph", "langchain-core", "chromadb"):
    try:
        out.append(f"{dist}=={md.version(dist)}")
    except md.PackageNotFoundError:
        out.append(f"{dist}: not installed")
fm = SP / "fastmcp"
hits = [str(p.relative_to(SP)) for p in fm.rglob("*.py") if "def custom_route" in p.read_text(encoding="utf-8",
                                                                                              errors="replace")]
out.append(f"fastmcp custom_route defined in: {hits}")
bins = SP / "pgserver/pginstall/bin"
out.append("pgserver bin: " + ", ".join(sorted(p.name for p in bins.glob("*.exe")
                                               if re.match(r"pg_(dump|restore|ctl)|psql|postgres", p.name))))
srv = Path(r"c:\Users\sovan\Documents\Projects\TCS-CJI\cji_agent\src\cji\mcp_servers\_serve.py")
out.append(srv.read_text(encoding="utf-8"))
dash = Path(r"c:\Users\sovan\Documents\Projects\TCS-CJI\cji_agent\src\cji\dashboard_launcher.py")
out += [l for l in dash.read_text(encoding="utf-8").splitlines() if re.search(r"address|host|port|headless", l)]
Path(r"C:\Users\sovan\.kiro\s15_libs.txt").write_text("\n".join(out).encode("ascii", "replace").decode(),
                                                     encoding="ascii")
print("ok")
