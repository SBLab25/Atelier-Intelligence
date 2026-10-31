"""Spec 03 fix-ups after the first gate: lint findings introduced by Spec 03 code.
Anchors verified before writing; newline style preserved."""
import pathlib
import sys

APP = pathlib.Path(__file__).resolve().parents[5] / "cji_agent"
EDITS = {
    "agents/workers.py": [(
        "def _contract_errors(*found: WorkflowError | None) -> Dict[str, Any]:",
        "def _contract_errors(*found: WorkflowError | None) -> dict[str, Any]:",
    )],
    "state.py": [(
        '''__all__ = [
    "CJIState", "JourneyEvent", "StepMetrics", "FrictionScore", "Insight",
    "WorkerStatus", "IngestionResult", "WorkflowError",
]''', '''__all__ = [
    "CJIState",
    "FrictionScore",
    "IngestionResult",
    "Insight",
    "JourneyEvent",
    "StepMetrics",
    "WorkerStatus",
    "WorkflowError",
]''')],
}


def main() -> int:
    planned, problems = {}, []
    for rel, pairs in EDITS.items():
        path = APP / rel
        raw = path.read_bytes().decode("utf-8")
        nl = "\r\n" if "\r\n" in raw else "\n"
        text = raw
        for old, new in pairs:
            o, n = old.replace("\n", nl), new.replace("\n", nl)
            if text.count(o) != 1:
                problems.append(f"{rel}: anchor found {text.count(o)}x: {old[:60]!r}")
                continue
            text = text.replace(o, n)
        planned[path] = text
    if problems:
        print("NOT APPLIED:\n" + "\n".join(problems))
        return 1
    for path, text in planned.items():
        path.write_bytes(text.encode("utf-8"))
        print(f"patched {path.relative_to(APP)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
