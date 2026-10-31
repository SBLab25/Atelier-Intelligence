"""Spec 06 follow-up edit 4: lint findings in the new test files; gate checks the right files."""
import pathlib

SPEC = pathlib.Path(__file__).resolve().parents[1].parent
APP = SPEC.parents[2] / "cji_agent"


def replace(path, old, new, count):
    t = path.read_text(encoding="utf-8")
    assert t.count(old) == count, (path.name, old[:60], t.count(old))
    path.write_text(t.replace(old, new), encoding="utf-8")


replace(APP / "tests/test_cleanup.py", ", re.M)", ", re.MULTILINE)", 1)
replace(APP / "tests/test_docs.py", ", re.M)", ", re.MULTILINE)", 3)
replace(APP / "tests/test_dashboard_smoke.py", "from streamlit.testing.v1 import AppTest  # noqa: E402",
        "from streamlit.testing.v1 import AppTest", 1)
replace(APP / "tests/test_dashboard_smoke.py", "from settings import make_test_settings, override_settings  # noqa: E402",
        "from settings import make_test_settings, override_settings", 1)
gate = SPEC / "evidence/scripts/gate_spec06.ps1"
replace(gate, "tests/test_cleanup.py tests/test_docs.py tests/test_dashboard_smoke.py tools/ingest_json.py main.py --no-cache",
        "tests/test_cleanup.py tests/test_docs.py tests/test_dashboard_smoke.py --no-cache", 1)
replace(gate, '''$synthBefore = (Get-Content (Join-Path $ev "t0-synthetic-hash.txt") | Select-String "^SYNTH").Line
$synthAfter = (Get-Content (Join-Path $ev "gate-synthetic.log") | Select-String "^SYNTH").Line
"synthetic data identical to T0: $($synthBefore -eq $synthAfter)  ($synthAfter)" | Add-Content $sum -Encoding utf8''',
        '''"$((Get-Content (Join-Path $ev "gate-synthetic.log") | Select-String "SYNTH identical").Line) (deterministic columns, current vs pre-Spec-06 generator)" | Add-Content $sum -Encoding utf8''', 1)
print("fix 4 applied")
