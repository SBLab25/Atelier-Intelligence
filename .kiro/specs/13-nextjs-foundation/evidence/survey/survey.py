"""Spec 13 survey: tools, repo layout, prompt text, API facts the frontend depends on."""
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

REPO = Path(r"C:\Users\sovan\Documents\Projects\TCS-CJI")
out = []


def run(cmd, cwd=None):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=60, cwd=cwd, shell=isinstance(cmd, str))
        return (p.stdout + p.stderr).strip()[:600]
    except Exception as exc:  # noqa: BLE001
        return f"ERR {type(exc).__name__}: {exc}"


out.append("== tools")
for tool in ("node", "npm", "npx", "pnpm", "yarn", "git"):
    path = shutil.which(tool)
    out.append(f"{tool}: {path} {run([path, '--version']) if path else ''}")
for exe in (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Google\Chrome\Application\chrome.exe"):
    out.append(f"{exe}: {os.path.exists(exe)}")
pw = Path(os.environ.get("LOCALAPPDATA", "")) / "ms-playwright"
out.append(f"playwright browsers dir: {pw.exists()} {sorted(p.name for p in pw.iterdir()) if pw.exists() else ''}")
out.append(f"npm config proxy: {run('npm config get proxy')} https-proxy: {run('npm config get https-proxy')} "
           f"registry: {run('npm config get registry')}")
out.append(f"env proxies: { {k: v for k, v in os.environ.items() if 'proxy' in k.lower()} }")

out.append("\n== repo top level")
out.append(", ".join(sorted(p.name for p in REPO.iterdir())))
for name in ("frontend", "web", "cji_web", "cji_agent/frontend"):
    out.append(f"{name}: {(REPO / name).exists()}")
out.append("package.json files: " + ", ".join(str(p.relative_to(REPO)) for p in REPO.rglob("package.json")
                                              if "node_modules" not in p.parts)[:600])
out.append("gitignore node lines: " + ", ".join(l for l in (REPO / ".gitignore").read_text(encoding="utf-8", errors="replace")
                                                 .splitlines() if re.search(r"node|next|frontend", l, re.I)))
out.append(f"git status --short (first 15):\n{run(['git', '-C', str(REPO), 'status', '--short'])[:900]}")

out.append("\n== prompt 12")
prompts = (REPO / "kiro_upgrade_prompts.md").read_text(encoding="utf-8", errors="replace")
m = re.search(r"(#+[^\n]*Prompt 12.*?)(?=\n#+[^\n]*Prompt 13|\Z)", prompts, re.S)
out.append(m.group(1)[:3500] if m else "Prompt 12 heading not found; headings: " +
           "; ".join(re.findall(r"^#+.*$", prompts, re.M)[:40]))

out.append("\n== API facts")
doc = json.loads((REPO / "cji_agent" / "openapi" / "v1.json").read_text(encoding="utf-8"))
out.append(f"openapi {doc['openapi']} version {doc['info']['version']}; {len(doc['paths'])} paths")
for path, item in doc["paths"].items():
    for method, op in item.items():
        out.append(f"  {method.upper()} {path} -> {sorted(op['responses'])}")
settings_services = (REPO / "cji_agent" / "src" / "cji" / "settings" / "services.py").read_text(encoding="utf-8")
out.append("frontend registry line: " + "; ".join(l.strip() for l in settings_services.splitlines() if "frontend" in l))
load = (REPO / "cji_agent" / "src" / "cji" / "settings" / "load.py").read_text(encoding="utf-8")
out.append("cors dev defaults: " + "; ".join(l.strip() for l in load.splitlines() if "3000" in l)[:600])
streamlit = REPO / "cji_agent" / "src" / "cji" / "dashboard.py"
out.append(f"dashboard.py lines: {len(streamlit.read_text(encoding='utf-8').splitlines())}")
out.append("dashboard pages: " + ", ".join(sorted(re.findall(r'"([^"]+ track)"', streamlit.read_text(encoding="utf-8")))))
Path(__file__).with_suffix(".txt").write_text("\n".join(out) + "\n", encoding="utf-8")
