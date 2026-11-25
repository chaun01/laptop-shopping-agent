"""Attach real $ cost to an agent eval report, using Langfuse's per-observation cost.

Every eval case runs in its own session id (stored in the report), so cost = sum of totalCost
over that session's observations (agent model + guard classifier + rewrite, all traced).

Usage: python evals/fetch_costs.py final_run1   (wait ~1 min after the run for ingestion)
"""
import datetime as dt
import json
import os
import sys
from collections import defaultdict

import httpx
from common import REPORTS, mean

sys.path.insert(0, str(REPORTS.parents[1] / "src"))
from laptop_agent.config import get_settings  # noqa: E402


def session_costs(since: dt.datetime) -> dict[str, float]:
    s = get_settings()
    auth = (s.langfuse_public_key, s.langfuse_secret_key)
    params = {"fields": "core,basic,usage", "fromStartTime": since.isoformat(), "limit": 1000}
    costs: dict[str, float] = defaultdict(float)
    while True:
        r = httpx.get(f"{s.langfuse_host}/api/public/v2/observations", params=params, auth=auth, timeout=60)
        r.raise_for_status()
        body = r.json()
        for o in body.get("data", []):
            if o.get("sessionId"):
                costs[o["sessionId"]] += o.get("totalCost") or 0.0
        cursor = (body.get("meta") or {}).get("cursor") or body.get("cursor")
        if not cursor or not body.get("data"):
            return costs
        params["cursor"] = cursor


def main(label: str) -> None:
    path = REPORTS / f"agent_eval_{label}.json"
    report = json.loads(path.read_text())
    since = dt.datetime.fromtimestamp(path.stat().st_mtime, dt.timezone.utc) - dt.timedelta(hours=1)
    costs = session_costs(since)
    for c in report["cases"]:
        c["cost_usd"] = round(costs.get(c.get("session_id"), 0.0), 5)
    found = [c["cost_usd"] for c in report["cases"] if c["cost_usd"] > 0]
    report["summary"]["avg_cost_usd_per_case"] = round(mean(found), 5)
    report["summary"]["total_cost_usd"] = round(sum(found), 4)
    report["summary"]["cost_cases_matched"] = f"{len(found)}/{len(report['cases'])}"
    path.write_text(json.dumps(report, indent=2))
    print(json.dumps({k: report["summary"][k] for k in
                      ("avg_cost_usd_per_case", "total_cost_usd", "cost_cases_matched")}))


if __name__ == "__main__":
    main(sys.argv[1])
