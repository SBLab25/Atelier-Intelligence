"""
Spec 06 follow-up edit 3.
- LLM fallbacks also catch OSError: the existing contract tests disable the network with the built-in
  ConnectionError, and requests.RequestException is itself an OSError subclass.
- README: data-dir row names data/last_run.json; test_docs skips URL paths such as /tracker.js.
"""
import pathlib

REPO = pathlib.Path(__file__).resolve().parents[5]
APP = REPO / "cji_agent"
OLD = "(requests.RequestException, KeyError, IndexError, ValueError, TypeError)"
NEW = "(requests.RequestException, OSError, KeyError, IndexError, ValueError, TypeError)"


def replace(path, old, new, count):
    t = path.read_text(encoding="utf-8")
    assert t.count(old) == count, (path.name, old[:50], t.count(old))
    path.write_text(t.replace(old, new), encoding="utf-8")


replace(APP / "mcp_servers/insight_server.py", OLD, NEW, 1)
replace(APP / "mcp_servers/report_server.py", OLD, NEW, 1)
replace(APP / "mcp_servers/ingestion_intelligence_server.py", OLD, NEW, 2)
replace(APP / "mcp_servers/ingestion_intelligence_server.py",
        "except (RuntimeError, ValueError, requests.RequestException):",
        "except (RuntimeError, ValueError, OSError):", 1)
replace(REPO / "README.md", "| Parquet, checkpoints, `last_run.json`, ChromaDB. |",
        "| Parquet, checkpoints, `data/last_run.json`, ChromaDB. |", 1)
replace(APP / "tests/test_docs.py", 'if token.startswith(RUNTIME_PREFIXES) or "<" in token:',
        'if token.startswith(RUNTIME_PREFIXES) or token.startswith("/") or "<" in token:', 1)
print("fix 3 applied")
