"""
Spec 15 (R15): docs/operations.md lists every limit setting the code reads, and nothing the code does not read.
"""

from __future__ import annotations

import re
from pathlib import Path

from cji.settings import KNOWN_KEYS

DOC = Path(__file__).resolve().parents[2] / "docs" / "operations.md"
LIMIT = re.compile(r"(RATE|MAX|TIMEOUT|LIMIT|BYTES|DEADLINE|ATTEMPTS|RETENTION|PER_MIN|BUDGET|ITERATIONS)")


def _limits_table() -> set[str]:
    text = DOC.read_text(encoding="utf-8")
    section = text.split("## Limits", 1)[1].split("\n## ", 1)[0]
    return set(re.findall(r"^\| `([A-Z][A-Z0-9_]+)` \|", section, re.MULTILINE))


def test_every_limit_setting_is_documented():
    expected = {k for k in KNOWN_KEYS if LIMIT.search(k)}
    assert expected - _limits_table() == set()


def test_documented_limits_exist():
    assert _limits_table() - set(KNOWN_KEYS) == set()


def test_every_backticked_setting_in_the_document_exists():
    names = set(
        re.findall(
            r"`((?:CJI|LLM|LANGCHAIN|GROQ|ANTHROPIC|OPENAI|DATABASE|SUPABASE|MAX)_[A-Z0-9_]+)`",
            DOC.read_text(encoding="utf-8"),
        )
    )
    frontend_only = {"CJI_SESSION_SECRET", "CJI_SESSION_SECRET_PREVIOUS"}
    assert names - set(KNOWN_KEYS) - frontend_only == set()


def test_the_secrets_table_names_its_tests_and_they_exist():
    text = DOC.read_text(encoding="utf-8")
    section = text.split("## Secrets", 1)[1].split("\n## ", 1)[0]
    named = set(re.findall(r"`(test_[a-z0-9_]+)`", section))
    tests = Path(__file__).resolve().parent
    defined = {
        m
        for p in tests.glob("test_*.py")
        for m in re.findall(r"^def (test_\w+)", p.read_text(encoding="utf-8"), re.MULTILINE)
    }
    assert named and named - defined == set()
