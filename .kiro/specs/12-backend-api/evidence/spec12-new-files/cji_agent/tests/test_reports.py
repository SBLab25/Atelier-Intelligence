"""
Spec 10 — safe deterministic reports (design §9).

Every untrusted field gets a payload corpus; the output is checked by parsing (tests/_report_checks.py):
nothing executable, no URLs, one CSP meta matching the one style block, one JSON data block. Snapshots of a
basic, an empty and a malicious report are compared byte for byte (`pytest --update-report-snapshots`).
No servers, network or databases; files are written only below tmp_path.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from tests._report_checks import (
    check_contract,
    check_inert,
    elements,
    report_data,
    text_content,
)

APP_ROOT = Path(__file__).resolve().parent.parent
SRC = APP_ROOT / "src" / "cji"                       # the package sources (Spec 11)
SNAPSHOTS = Path(__file__).resolve().parent / "snapshots"
NAME = re.compile(r"cji_report_[a-z0-9_-]{1,64}_[A-Za-z0-9-]{1,64}\.html")

PAYLOADS = [
    "<script>alert(1)</script>",
    '"><img src=x onerror=alert(1)>',
    "'><svg onload=alert(1)>",
    "</title><script>alert(1)</script>",
    "</style><script>alert(1)</script>",
    "</script><script>alert(1)</script>",
    "<!--<script>alert(1)//-->",
    "<![CDATA[<script>alert(1)</script>]]>",
    "javascript:alert(1)",
    "data:text/html,<script>alert(1)</script>",
    '<a href="javascript:alert(1)">x</a>',
    "<iframe srcdoc='<script>alert(1)</script>'></iframe>",
    "{{7*7}} ${7*7} <%= 7*7 %>",
    "\u2028\u2029</script>",
    "\u202egnp.exe",
    "<math><mtext><table><mglyph><style><img src=x onerror=alert(1)>",
    "&lt;script&gt;already-escaped",
    "<style>@import url(//evil.example)</style>",
    '" style="background:url(javascript:alert(1))',
    "<svg><use href=\"data:image/svg+xml,<svg onload=alert(1)>\"/></svg>",
]

FIELDS = ["journey_name", "narrative", "insight.step_id", "insight.title", "insight.root_cause",
          "insight.suggested_fix", "funnel.step_id", "friction.step_id", "narrative_model", "run_id"]


def basic_input(**over):
    args = {
        "journey_name": "user_onboarding",
        "mode": "demo",
        "narrative": "Completion falls sharply at email verification.\n\nWe recommend sending a code instead.",
        "insights": [
            {"step_id": "email_verification", "title": "Friction at email_verification", "priority": 2,
             "root_cause": "Users wait for the email.", "suggested_fix": "Send a one-time code instead.",
             "insight_id": "ins-1", "category": "UX", "evidence": ["e1"], "priority_score": 4.5},
            {"step_id": "payment_info", "title": "Friction at payment_info", "priority": 3,
             "root_cause": "Card form errors.", "suggested_fix": "Validate fields inline."},
        ],
        "funnel_data": [
            {"step_id": "landing_page", "users": 1489, "drop_off_pct": 10.34},
            {"step_id": "email_verification", "users": 1037, "drop_off_pct": 36.93},
            {"step_id": "payment_info", "users": 387, "drop_off_pct": 35.92},
        ],
        "friction_scores": [
            {"step_id": "email_verification", "score": 72, "is_critical": True, "signals": ["dwell"]},
            {"step_id": "payment_info", "score": 41, "is_critical": False},
        ],
        "run_id": "run-basic-1",
        "generated_at": "2026-01-01T00:00:00Z",
        "narrative_source": "fallback",
        "narrative_model": "",
    }
    args.update(over)
    return args


def empty_input(**over):
    return {"journey_name": "j", "mode": "demo", "narrative": "", "insights": [], "funnel_data": [],
            "friction_scores": [], "run_id": "run-empty-1", **over}


def with_payload(field, payload, base=None):
    args = basic_input() if base is None else base
    if field.startswith("insight."):
        args["insights"] = [{**args["insights"][0], field.split(".", 1)[1]: payload}]
    elif field.startswith("funnel."):
        args["funnel_data"] = [{**args["funnel_data"][0], "step_id": payload}]
    elif field.startswith("friction."):
        args["friction_scores"] = [{**args["friction_scores"][0], "step_id": payload}]
    else:
        args[field] = payload
    return args


def malicious_input():
    p = PAYLOADS
    return basic_input(
        journey_name=p[3], narrative="\n".join(p), run_id=p[10], narrative_model=p[1], mode=p[2],
        insights=[{"step_id": p[i], "title": p[i + 1], "priority": 1 + i % 5, "root_cause": p[i + 2],
                   "suggested_fix": p[i + 3]} for i in range(0, 16, 4)],
        funnel_data=[{"step_id": s, "users": 10 * (i + 1)} for i, s in enumerate(p[:6])],
        friction_scores=[{"step_id": s, "score": 50 + i, "is_critical": i % 2 == 0} for i, s in enumerate(p[6:12])],
    )


@pytest.fixture
def reports(monkeypatch, tmp_path):
    """export_report writing into tmp_path/reports; returns (export, reports_dir)."""
    from cji.mcp_servers import report_server as rs

    directory = tmp_path / "reports"
    monkeypatch.setattr(rs, "REPORTS_DIR", directory)
    return rs.export_report, directory


def html_of(res):
    assert res.get("report_path"), res
    return Path(res["report_path"]).read_text(encoding="utf-8")


def files_under(root):
    return sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file())


def render(args):
    from cji.reporting import ReportInput
    from cji.reporting import render as _render

    return _render(ReportInput.model_validate(args))


# ═══════════════════════════════════════════════════════════════════════════════════════════════════
# XSS payloads render inert
# ═══════════════════════════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("field", FIELDS)
@pytest.mark.parametrize("payload", PAYLOADS, ids=[f"p{i}" for i in range(len(PAYLOADS))])
def test_payload_renders_inert_in_every_field(reports, field, payload):
    export, _ = reports
    html = html_of(export(**with_payload(field, payload)))
    assert check_inert(html) == []
    assert check_contract(html) == []
    # The text is still there for the reader, as text (not markup). Identifiers are trimmed, and str.strip()
    # also removes U+2028/U+2029 at the edges.
    expected = payload.strip()[:20]
    shown = text_content(html) + json.dumps(report_data(html))
    assert expected in shown or json.dumps(expected)[1:-1] in shown


def test_payload_text_is_escaped_not_dropped(reports):
    export, _ = reports
    html = html_of(export(**basic_input(narrative=PAYLOADS[0], insights=[
        {"step_id": "s", "title": PAYLOADS[1], "priority": 1}])))
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "&quot;&gt;&lt;img src=x onerror=alert(1)&gt;" in html
    assert "<script>alert" not in html and "<img" not in html


def test_bidi_controls_are_character_references_in_attributes():
    from cji.reporting.escape import attr

    assert attr("a\u202eb\u2066c") == "a&#x202e;b&#x2066;c"
    assert attr('"<>&\'') == "&quot;&lt;&gt;&amp;&#x27;"


def test_json_block_cannot_close_the_script_or_open_a_comment():
    from cji.reporting.escape import json_block

    out = json_block({"k": "</script><!--<script>\u2028&"})
    assert "<" not in out and ">" not in out and "&" not in out
    assert json.loads(out) == {"k": "</script><!--<script>\u2028&"}


def test_json_block_rejects_nan():
    from cji.reporting.escape import json_block

    with pytest.raises(ValueError):
        json_block({"x": float("nan")})


def test_mode_is_allow_listed(reports):
    export, _ = reports
    html = html_of(export(**basic_input(mode='demo" onclick="x')))
    assert check_inert(html) == []
    assert '<span class="badge unknown">UNKNOWN MODE</span>' in html


def test_renderer_source_has_no_dangerous_sinks():
    src = (SRC / "reporting" / "render.py").read_text(encoding="utf-8")
    for sink in ('style="', "href=", "src=", "<link", "<img", "javascript:", "http://", "https://", "on" + "load"):
        assert sink not in src, sink
    assert src.count("<script") == 1 and 'type="application/json"' in src


# ═══════════════════════════════════════════════════════════════════════════════════════════════════
# Self-contained output contract and provenance
# ═══════════════════════════════════════════════════════════════════════════════════════════════════

def test_basic_report_satisfies_the_contract(reports):
    export, directory = reports
    res = export(**basic_input())
    html = html_of(res)
    assert check_contract(html) == [] and check_inert(html) == []
    data = html.encode("utf-8")
    assert res["sha256"] == hashlib.sha256(data).hexdigest()
    assert res["schema"] == "cji-report/1"
    assert res["file_size_kb"] == round(len(data) / 1024, 2)
    assert Path(res["report_path"]).parent == directory.resolve()


def test_provenance_block_records_the_inputs(reports):
    from cji.reporting import ReportInput

    export, _ = reports
    args = basic_input(narrative_source="llm", narrative_model="openai/gpt-oss-120b")
    data = report_data(html_of(export(**args)))
    assert data["schema"] == "cji-report/1"
    assert data["run_id"] == "run-basic-1" and data["journey"] == "user_onboarding" and data["mode"] == "demo"
    assert data["generated_at"] == "2026-01-01T00:00:00Z"
    assert data["input_sha256"] == ReportInput.model_validate(args).input_sha256()
    assert data["narrative"] == {"source": "llm", "model": "openai/gpt-oss-120b"}
    assert data["counts"] == {"insights": [2, 2], "funnel_steps": [3, 3], "friction_rows": [2, 2]}
    assert data["truncated"] == {}
    assert data["funnel"] == [{"step_id": "landing_page", "users": 1489},
                              {"step_id": "email_verification", "users": 1037},
                              {"step_id": "payment_info", "users": 387}]
    assert data["renderer"].startswith("cji-report-renderer/")


def test_footer_shows_the_provenance(reports):
    export, _ = reports
    text = text_content(html_of(export(**basic_input(narrative_source="llm", narrative_model="m-1"))))
    for fact in ("run-basic-1", "cji-report/1", "llm", "m-1"):
        assert fact in text
    assert "Generated: 2026-01-01 00:00:00 UTC" in text


def test_missing_generated_at_is_shown_as_not_recorded(reports):
    export, _ = reports
    html = html_of(export(**basic_input(generated_at="")))
    assert "Generated: not recorded" in text_content(html)
    assert report_data(html)["generated_at"] == ""


def test_generated_at_must_be_utc_iso(reports):
    export, _ = reports
    res = export(**basic_input(generated_at="yesterday <b>"))
    assert res["report_path"] is None and res["code"] == "report_invalid_input"
    assert "generated_at" in res["error"] and "<b>" not in res["error"]


def test_report_meaning_is_preserved(reports):
    export, _ = reports
    html = html_of(export(**basic_input()))
    text = text_content(html)
    order = [text.index(h) for h in ("Customer Journey Intelligence Report", "Executive Summary",
                                     "Funnel Analysis", "Friction by step", "Top Prioritised Insights")]
    assert order == sorted(order)
    assert "[Priority 2] - email_verification" in text
    for line in ("Issue:", "Friction at email_verification", "Root Cause:", "Users wait for the email.",
                 "Recommendation:", "Send a one-time code instead."):
        assert line in text
    assert '<span class="badge demo">DEMO MODE</span>' in html
    assert "<title>CJI Report - user_onboarding</title>" in html
    assert "Completion falls sharply at email verification.\n\nWe recommend" in text


def test_friction_table_lists_scores_in_input_order(reports):
    export, _ = reports
    html = html_of(export(**basic_input()))
    rows = re.findall(r"<tr><td>(.*?)</td><td>(.*?)</td><td>(.*?)</td></tr>", html)
    assert rows == [("email_verification", "72.0", "Yes"), ("payment_info", "41.0", "—")]


# ═══════════════════════════════════════════════════════════════════════════════════════════════════
# Chart behaviour (OD-81)
# ═══════════════════════════════════════════════════════════════════════════════════════════════════

def test_chart_has_one_bar_per_step_in_order_scaled_to_the_largest(reports):
    export, _ = reports
    html = html_of(export(**basic_input(funnel_data=[
        {"step_id": "a", "users": 100}, {"step_id": "b", "users": 50}, {"step_id": "c", "users": 0}])))
    bars = [r for r in elements(html, "rect") if r.get("class") == "bar"]
    assert [float(r["width"]) for r in bars] == [600.0, 300.0, 0.0]
    svg = html[html.index("<svg"):html.index("</svg>")]
    assert re.findall(r"<title>(.*?)</title>", svg) == ["a: 100 users", "b: 50 users", "c: 0 users"]
    assert [t for t in re.findall(r'<text class="label"[^>]*>(.*?)</text>', svg)] == ["a", "b", "c"]
    assert elements(html, "svg")[0]["viewbox"] == "0 0 860 132"


def test_chart_labels_are_shortened_but_the_title_keeps_the_full_step(reports):
    export, _ = reports
    long_step = "s" * 100
    html = html_of(export(**basic_input(funnel_data=[{"step_id": long_step, "users": 1234567}])))
    svg = html[html.index("<svg"):html.index("</svg>")]
    assert f"<title>{long_step}: 1,234,567 users</title>" in svg
    assert re.findall(r'<text class="label"[^>]*>(.*?)</text>', svg) == ["s" * 31 + "…"]


def test_chart_with_all_zero_users_has_zero_width_bars(reports):
    export, _ = reports
    html = html_of(export(**basic_input(funnel_data=[{"step_id": "a", "users": 0}, {"step_id": "b", "users": 0}])))
    assert [float(r["width"]) for r in elements(html, "rect") if r.get("class") == "bar"] == [0.0, 0.0]


# ═══════════════════════════════════════════════════════════════════════════════════════════════════
# Determinism and snapshots
# ═══════════════════════════════════════════════════════════════════════════════════════════════════

def test_same_input_gives_byte_identical_files_and_names(reports):
    export, directory = reports
    first = export(**basic_input())
    a = Path(first["report_path"]).read_bytes()
    second = export(**basic_input())
    assert first["report_path"] == second["report_path"] and first["sha256"] == second["sha256"]
    assert Path(second["report_path"]).read_bytes() == a
    assert files_under(directory) == [Path(first["report_path"]).name]


def test_rendering_does_not_depend_on_hash_seed_or_clock():
    # `python -c` puts the working directory (cji_agent/) first on the import path.
    code = ("import hashlib; from tests.test_reports import basic_input, render; "
            "print(hashlib.sha256(render(basic_input()).encode()).hexdigest())")
    digests = set()
    for seed in ("1", "2"):
        env = {**os.environ, "PYTHONHASHSEED": seed, "TZ": "Asia/Kolkata" if seed == "1" else "UTC"}
        out = subprocess.run([sys.executable, "-c", code], check=False, cwd=APP_ROOT, env=env, capture_output=True,
                             text=True, timeout=120)
        assert out.returncode == 0, out.stderr[-2000:]
        digests.add(out.stdout.strip())
    assert len(digests) == 1


@pytest.mark.parametrize("name, make", [("basic", basic_input), ("empty", empty_input),
                                        ("malicious", malicious_input)])
def test_snapshot(request, name, make):
    html = render(make()).encode("utf-8")
    path = SNAPSHOTS / f"report_{name}.html"
    if request.config.getoption("--update-report-snapshots"):
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(html)
    assert path.exists(), f"missing snapshot {path.name}; run pytest --update-report-snapshots"
    assert html == path.read_bytes(), f"{path.name} changed; review and run pytest --update-report-snapshots"
    text = html.decode("utf-8")
    assert check_inert(text) == [] and check_contract(text) == []


# ═══════════════════════════════════════════════════════════════════════════════════════════════════
# Empty, large and malformed inputs
# ═══════════════════════════════════════════════════════════════════════════════════════════════════

def test_empty_report(reports):
    export, _ = reports
    html = html_of(export(**empty_input()))
    text = text_content(html)
    assert check_contract(html) == [] and check_inert(html) == []
    assert "No funnel data." in text and "No critical insights generated." in text
    assert "Friction by step" not in text
    assert elements(html, "svg") == []
    assert report_data(html)["counts"] == {"insights": [0, 0], "funnel_steps": [0, 0], "friction_rows": [0, 0]}


def test_minimal_call_without_optional_arguments(reports):
    export, _ = reports
    res = export(journey_name="j", narrative="n", friction_scores=[], insights=[], funnel_data=[], mode="demo")
    html = html_of(res)
    assert NAME.fullmatch(Path(res["report_path"]).name)
    assert report_data(html)["narrative"] == {"source": "unknown", "model": ""}


def test_large_input_is_truncated_visibly(reports):
    export, _ = reports
    many = [{"step_id": f"s{i}", "title": "T" * 500, "priority": 1 + i % 5, "root_cause": "R" * 5000,
             "suggested_fix": "F" * 5000} for i in range(2000)]
    res = export(**basic_input(insights=many, narrative="N" * 10_000,
                               funnel_data=[{"step_id": f"f{i}", "users": i} for i in range(150)],
                               friction_scores=[{"step_id": f"f{i}", "score": 10} for i in range(150)]))
    html = html_of(res)
    assert check_contract(html) == [] and check_inert(html) == []
    cards = [d for d in elements(html, "div") if d.get("class") == "insight-card"]
    assert len(cards) == 50
    text = text_content(html)
    assert "Showing 50 of 2000 insights." in text
    assert "Narrative shortened to 4000 characters." in text
    data = report_data(html)
    assert data["counts"] == {"insights": [50, 2000], "funnel_steps": [100, 150], "friction_rows": [100, 150]}
    assert data["truncated"]["insights"] == 1950 and data["truncated"]["narrative"] == 10_000
    assert data["truncated"]["insights.0.title"] == 500 and data["truncated"]["insights.0.root_cause"] == 5000
    assert len(data["funnel"]) == 100
    assert "N" * 3999 + "…" in text and "N" * 4000 not in text


def test_worst_case_within_limits_is_written_or_refused_explicitly(reports):
    export, directory = reports
    lt = "<" * 5000
    res = export(**basic_input(
        journey_name=lt, narrative=lt,
        insights=[{"step_id": lt, "title": lt, "priority": 1, "root_cause": lt, "suggested_fix": lt}] * 50,
        funnel_data=[{"step_id": lt + str(i), "users": i} for i in range(100)],
        friction_scores=[{"step_id": lt, "score": 1}] * 100, narrative_model=lt))
    if res["report_path"]:
        assert check_contract(html_of(res)) == []
    else:
        assert res["code"] == "report_too_large" and files_under(directory.parent) == []


def test_oversize_output_is_refused_and_no_file_is_left(reports, monkeypatch):
    from cji.reporting import output

    export, directory = reports
    monkeypatch.setattr(output, "MAX_REPORT_BYTES", 2_000)
    res = export(**basic_input())
    assert res == {"report_path": None, "file_size_kb": 0, "error": res["error"], "code": "report_too_large"}
    assert "2000" in res["error"]
    assert files_under(directory.parent) == []


MALFORMED = [
    ("insights", [None]), ("insights", ["text"]), ("insights", [1]), ("insights", "not a list"),
    ("insights", [{"title": "T", "priority": 1}]),                               # missing step_id
    ("insights", [{"step_id": "s", "priority": 1}]),                             # missing title
    ("insights", [{"step_id": "s", "title": "T", "priority": "2"}]),             # strict int
    ("insights", [{"step_id": "s", "title": "T", "priority": True}]),
    ("insights", [{"step_id": "s", "title": "T", "priority": 0}]),
    ("insights", [{"step_id": "s", "title": "T", "priority": 6}]),
    ("insights", [{"step_id": "s", "title": "<script>x</script>", "priority": None}]),
    ("insights", [{"step_id": "", "title": "T", "priority": 1}]),
    ("funnel_data", [1]), ("funnel_data", [{"step_id": "a", "users": "5"}]),
    ("funnel_data", [{"step_id": "a", "users": -1}]), ("funnel_data", [{"step_id": "a", "users": 1.5}]),
    ("funnel_data", [{"step_id": "a", "users": 10 ** 10}]), ("funnel_data", [{"users": 3}]),
    ("friction_scores", [{"step_id": "a", "score": float("nan")}]),
    ("friction_scores", [{"step_id": "a", "score": 101}]), ("friction_scores", [{"step_id": "a"}]),
    ("narrative", {"x": 1}), ("narrative", 5), ("narrative", None),
    ("journey_name", ""), ("journey_name", "   "), ("journey_name", None), ("journey_name", 7),
    ("narrative_source", "<b>made up</b>"),
]


@pytest.mark.parametrize("field, value", MALFORMED, ids=[f"{f}-{i}" for i, (f, _) in enumerate(MALFORMED)])
def test_malformed_input_fails_explicitly_without_a_file(reports, field, value):
    export, directory = reports
    res = export(**basic_input(**{field: value}))
    assert res["report_path"] is None and res["file_size_kb"] == 0
    assert res["code"] == "report_invalid_input"
    assert res["error"].startswith("invalid report input: ") and field in res["error"]
    assert "<script" not in res["error"] and "<b>" not in res["error"]
    assert files_under(directory.parent) == []


def test_invalid_input_error_lists_at_most_five_fields(reports):
    export, _ = reports
    res = export(**basic_input(insights=[None] * 20))
    assert res["code"] == "report_invalid_input"
    assert res["error"].count("insights.") == 5 and "(+15 more)" in res["error"]


def test_text_is_cleaned(reports):
    export, _ = reports
    html = html_of(export(**basic_input(narrative="a\x00b\x07c\r\nd\re\ud800f\x85g\x7fh\tok")))
    assert "abc\nd\ne\ufffdfgh\tok" in text_content(html)
    assert "\x00" not in html and "\ud800" not in html


# ═══════════════════════════════════════════════════════════════════════════════════════════════════
# File names and paths
# ═══════════════════════════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("journey, slug", [
    ("user_onboarding", "user_onboarding"), ("User Onboarding", "user_onboarding"),
    ("x/../../escaped", "x_______escaped"), ("x\\..\\..\\escaped", "x_______escaped"),
    ("/etc/passwd", "_etc_passwd"), ("C:\\Windows\\win.ini", "c__windows_win_ini"), ("a:b", "a_b"),
    ("CON", "con"), ("nul.html", "nul_html"), ("..", "__"), ("日本", "__"), ("j" * 300, "j" * 64),
    ("a\x00b", "ab"),
])
def test_file_name_is_a_slug_inside_the_reports_directory(reports, tmp_path, journey, slug):
    export, directory = reports
    res = export(**basic_input(journey_name=journey))
    path = Path(res["report_path"])
    assert path.name == f"cji_report_{slug}_run-basic-1.html" and NAME.fullmatch(path.name)
    assert path.parent == directory.resolve()
    assert files_under(tmp_path) == [f"reports{os.sep}{path.name}"]


@pytest.mark.parametrize("run_id", ["", "../../x", "a b", "run_1.2", "x" * 65, "<script>"])
def test_invalid_run_id_uses_the_input_hash(reports, run_id):
    from cji.reporting import ReportInput

    export, _ = reports
    args = basic_input(run_id=run_id)
    res = export(**args)
    digest = ReportInput.model_validate(args).input_sha256()[:16]
    assert Path(res["report_path"]).name == f"cji_report_user_onboarding_{digest}.html"
    assert export(**args)["report_path"] == res["report_path"]


def test_write_failure_is_explicit_and_leaves_no_temporary_file(reports, monkeypatch, tmp_path):
    from cji.reporting import output

    export, _ = reports

    def broken_replace(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr(output.os, "replace", broken_replace)
    res = export(**basic_input())
    assert res["report_path"] is None and res["code"] == "report_write_failed"
    assert "disk full" in res["error"]
    assert files_under(tmp_path) == []


def test_reports_directory_that_is_a_file_is_a_write_failure(monkeypatch, tmp_path):
    from cji.mcp_servers import report_server as rs

    blocker = tmp_path / "reports"
    blocker.write_text("not a directory", encoding="utf-8")
    monkeypatch.setattr(rs, "REPORTS_DIR", blocker)
    res = rs.export_report(**basic_input())
    assert res["report_path"] is None and res["code"] == "report_write_failed"
    assert files_under(tmp_path) == ["reports"]


def test_path_check_refuses_names_outside_the_directory(tmp_path):
    from cji.reporting.output import ReportPathError, write_report

    for name in ("../x.html", "sub/x.html", "x.txt", str(tmp_path / "abs.html")):
        with pytest.raises(ReportPathError):
            write_report("<!DOCTYPE html>", tmp_path / "reports", name)
    assert files_under(tmp_path) == []


# ═══════════════════════════════════════════════════════════════════════════════════════════════════
# Dashboard Insights page (OD-92)
# ═══════════════════════════════════════════════════════════════════════════════════════════════════

def test_dashboard_insights_page_escapes_report_content():
    full = (SRC / "dashboard.py").read_text(encoding="utf-8")
    start = full.index('elif page == "Insights":')
    end = full.find("\nelif page ==", start + 1)
    src = full[start:] if end < 0 else full[start:end]     # the other pages are F-49 (dashboard prompt)
    for escaped in ("{html.escape(narrative)}", "{html.escape(step_lbl)}", "{html.escape(action)}",
                    "{html.escape(r.name)}"):
        assert escaped in src, escaped
    for raw in (">{narrative}<", ">{step_lbl}<", ">{action}<", "📄 {r.name}<"):
        assert raw not in src, raw
