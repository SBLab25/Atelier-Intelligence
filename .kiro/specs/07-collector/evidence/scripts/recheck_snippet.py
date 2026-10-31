"""Spec 07 T7 re-check after the post-gate fix to tracker/snippet_generator.py (UP017 in the generated verify script)."""
import os
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[5]
APP = ROOT / "cji_agent"
EV = ROOT / ".kiro" / "specs" / "07-collector" / "evidence"
env = {**os.environ, "HTTP_PROXY": "http://127.0.0.1:9", "HTTPS_PROXY": "http://127.0.0.1:9",
       "NO_PROXY": "localhost,127.0.0.1", "DATABASE_URL": "postgresql://baseline:baseline@127.0.0.1:1/baseline",
       "SUPABASE_DATABASE_URL": "postgresql://baseline:baseline@127.0.0.1:1/baseline", "CJI_MODE": "demo",
       "JOURNEY_NAME": "user_onboarding", "PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8",
       "GROQ_API_KEY": "baseline-offline-dummy", "ANTHROPIC_API_KEY": "baseline-offline-dummy",
       "OPENAI_API_KEY": "baseline-offline-dummy", "LANGCHAIN_API_KEY": "baseline-offline-dummy",
       "LANGCHAIN_TRACING_V2": "false"}
env.pop("CJI_TEST_DATABASE_URL", None)
out = tempfile.mkdtemp(prefix="cji_s07_snip_")
steps = [
    [sys.executable, "tracker/snippet_generator.py", "--journey", "user_onboarding",
     "--api-key", "cji_live_0123456789abcdef", "--output", out],
    [sys.executable, "-m", "ruff", "check", os.path.join(out, "verify_tracker.py"), "tracker/snippet_generator.py",
     "--no-cache", "--output-format", "concise"],
    [sys.executable, "-m", "pytest", "tests/test_settings.py", "tests/test_cleanup.py", "tests/test_docs.py",
     "-p", "no:cacheprovider", "-m", "not integration", "-q"],
]
log = []
for cmd in steps:
    r = subprocess.run(cmd, cwd=APP, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
    log.append(f"$ {' '.join(cmd[1:4])} ... exit={r.returncode}\n{r.stdout[-3000:]}{r.stderr[-1500:]}")
(EV / "gate-recheck-snippet.log").write_text("\n".join(log), encoding="utf-8")
