"""
Spec 14 parity check (requirements §4, design §7). Compares what Next.js shows (the API's JSON; rendering parity is
checked by the Playwright specs) with the CLI and the engine for the same run and data.

usage: parity_check.py --api URL --token TOKEN --run RUN_ID [--cli-run RUN_ID] --out DIR [--journey ID] [--days N]
  --run      a run started and approved through the API (Next.js)
  --cli-run  a run completed by `cji --run --auto-approve` (its data/last_run.json is compared too)
Writes DIR/parity.json and DIR/parity.txt; exit 1 when any check fails.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Any

FRICTION_KEYS = ("step_id", "score", "is_critical", "signals", "confidence")
INSIGHT_KEYS = ("insight_id", "step_id", "title", "root_cause", "category", "suggested_fix", "fix_effort", "priority")
FIX_KEYS = ("insight_id", "step_id", "suggested_fix", "priority", "priority_score")


class Checks:
    def __init__(self) -> None:
        self.items: list[dict[str, Any]] = []

    def eq(self, name: str, left: Any, right: Any) -> None:
        ok = left == right
        entry: dict[str, Any] = {"check": name, "ok": ok}
        if not ok:
            entry["left"], entry["right"] = left, right
        self.items.append(entry)

    @property
    def failed(self) -> int:
        return sum(1 for i in self.items if not i["ok"])


def get(api: str, token: str, path: str) -> Any:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    req = urllib.request.Request(api + path, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})
    with opener.open(req, timeout=60) as resp:  # noqa: S310 - loopback URL given on the command line
        return json.loads(resp.read().decode("utf-8"))


def pick(items: list[dict[str, Any]], keys: tuple[str, ...]) -> list[dict[str, Any]]:
    return [{k: i.get(k) for k in keys} for i in items]


def cli_status(run_id: str) -> dict[str, Any]:
    exe = Path(sys.executable).with_name("cji.exe")
    out = subprocess.run([str(exe), "--status", "--thread-id", run_id], capture_output=True, text=True, timeout=120,
                         check=True, env=os.environ.copy())
    text = out.stdout[out.stdout.index("{"):]
    return json.loads(text)


def compare_run(c: Checks, api: str, token: str, run_id: str, label: str) -> dict[str, Any]:
    from cji.settings import get_settings
    from cji.workflow.runtime import Workflow

    run = get(api, token, f"/api/v1/runs/{run_id}")
    results = get(api, token, f"/api/v1/runs/{run_id}/results")
    status = cli_status(run_id)
    c.eq(f"{label}: status API = CLI --status", run["status"], status.get("status"))
    c.eq(f"{label}: human_approved API = CLI", run["human_approved"], bool(status.get("human_approved")))
    cli_steps = {k: (v or {}).get("status") for k, v in (status.get("steps") or {}).items()}
    c.eq(f"{label}: step statuses API = CLI", {k: v.get("status") for k, v in run["steps"].items()}, cli_steps)
    _status, values = asyncio.run(Workflow(get_settings().storage.checkpoints_db).inspect(run_id))
    c.eq(f"{label}: friction scores API = checkpoint", pick(results["friction_scores"], FRICTION_KEYS),
         pick(values.get("friction_scores") or [], FRICTION_KEYS))
    c.eq(f"{label}: critical steps API = checkpoint", results["critical_steps"], values.get("critical_steps") or [])
    c.eq(f"{label}: insights API = checkpoint", pick(results["insights"], INSIGHT_KEYS),
         pick(values.get("insights") or [], INSIGHT_KEYS))
    c.eq(f"{label}: prioritized fixes API = checkpoint (order kept)", pick(results["prioritized_fixes"], FIX_KEYS),
         pick(values.get("prioritized_fixes") or [], FIX_KEYS))
    c.eq(f"{label}: narrative API = checkpoint", results["narrative"], values.get("narrative") or None)
    prov = values.get("insight_provenance") or {}
    c.eq(f"{label}: insight provenance API = checkpoint",
         [i["provenance"]["source"] for i in results["insights"]],
         [(prov.get(i.get("insight_id")) or {}).get("source", "not_recorded") for i in values.get("insights") or []])
    c.eq(f"{label}: narrative provenance API = checkpoint", results["narrative_provenance"]["source"],
         (values.get("narrative_provenance") or {}).get("source", "not_recorded"))
    return results


def compare_last_run(c: Checks, results: dict[str, Any]) -> None:
    from cji.settings import get_settings

    path = get_settings().storage.last_run_file
    last = json.loads(path.read_text(encoding="utf-8"))
    c.eq("cli run: friction scores API = last_run.json", pick(results["friction_scores"], FRICTION_KEYS),
         pick(last.get("friction_scores") or [], FRICTION_KEYS))
    c.eq("cli run: critical steps API = last_run.json", results["critical_steps"], last.get("critical_steps") or [])
    c.eq("cli run: insights API = last_run.json", pick(results["insights"], INSIGHT_KEYS),
         pick(last.get("insights") or [], INSIGHT_KEYS))
    c.eq("cli run: prioritized fixes API = last_run.json", pick(results["prioritized_fixes"], FIX_KEYS),
         pick(last.get("prioritized_fixes") or [], FIX_KEYS))
    c.eq("cli run: narrative API = last_run.json", results["narrative"], last.get("narrative") or None)


def compare_live(c: Checks, api: str, token: str, journey_id: str, days: int) -> None:
    from cji.analytics.friction import score_steps
    from cji.repositories import event_repository
    from cji.services import analytics, journeys
    from cji.settings import get_settings

    settings = get_settings()
    journey = journeys.get_journey(settings, journey_id)
    if journey is None:
        c.eq("journey configured", journey_id, None)
        return
    repo = event_repository(settings)
    try:
        window = analytics.window_for(days, None)
        direct = analytics.journey_metrics(repo, journey, window)
        threshold = settings.budgets.friction_score_threshold
        friction = analytics.journey_friction(repo, journey, window, threshold)
    finally:
        repo.close()
    metrics = get(api, token, f"/api/v1/journeys/{journey_id}/metrics?days={days}")
    c.eq("live: step metrics API = services.analytics", metrics["steps"], json.loads(json.dumps(direct.steps)))
    c.eq("live: funnel API = services.analytics", metrics["funnel"], json.loads(json.dumps(direct.funnel)))
    c.eq("live: completion API = services.analytics", metrics["overall_completion_pct"], direct.overall_completion_pct)
    api_friction = get(api, token, f"/api/v1/journeys/{journey_id}/friction?days={days}")
    c.eq("live: friction API = services.analytics", api_friction["scores"], json.loads(json.dumps(friction["scores"])))
    rescored = score_steps(direct.steps, threshold=threshold)
    c.eq("live: friction API = score_steps(metrics)", pick(api_friction["scores"], FRICTION_KEYS),
         pick(rescored["scores"], FRICTION_KEYS))
    c.eq("live: critical steps API = score_steps", api_friction["critical_steps"], rescored["critical_steps"])


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--api", required=True)
    p.add_argument("--token", required=True)
    p.add_argument("--run", required=True)
    p.add_argument("--cli-run")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--journey", default="user_onboarding")
    p.add_argument("--days", type=int, default=30)
    args = p.parse_args(argv)
    c = Checks()
    compare_run(c, args.api, args.token, args.run, "api run")
    if args.cli_run:
        results = compare_run(c, args.api, args.token, args.cli_run, "cli run")
        compare_last_run(c, results)
    compare_live(c, args.api, args.token, args.journey, args.days)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "parity.json").write_text(json.dumps(c.items, indent=2, default=str), encoding="utf-8")
    lines = [f"{'PASS' if i['ok'] else 'FAIL'}  {i['check']}" for i in c.items]
    lines.append(f"\n{len(c.items) - c.failed} of {len(c.items)} checks passed")
    (args.out / "parity.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 1 if c.failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
