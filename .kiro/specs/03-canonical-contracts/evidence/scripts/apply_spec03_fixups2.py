"""Spec 03 fix-up 2: ingestion_worker annotates CJIState.errors with the domain type
(mypy arg-type error introduced by errors: list[WorkflowError]). Anchors verified first."""
import pathlib
import sys

APP = pathlib.Path(__file__).resolve().parents[5] / "cji_agent"
REL = "agents/ingestion_worker.py"
PAIRS = [
    ("from state import CJIState, IngestionResult, WorkerStatus\n",
     "from state import CJIState, IngestionResult, WorkerStatus, WorkflowError\n"),
    ('    errors:         list[dict]            = list(state.get("errors", []))\n',
     '    errors:         list[WorkflowError]   = list(state.get("errors", []))\n'),
]


def main() -> int:
    path = APP / REL
    raw = path.read_bytes().decode("utf-8")
    nl = "\r\n" if "\r\n" in raw else "\n"
    text = raw
    for old, new in PAIRS:
        o, n = old.replace("\n", nl), new.replace("\n", nl)
        if text.count(o) != 1:
            print(f"NOT APPLIED: anchor found {text.count(o)}x: {old!r}")
            return 1
        text = text.replace(o, n)
    path.write_bytes(text.encode("utf-8"))
    print(f"patched {REL}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
