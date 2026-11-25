"""Compare agent eval runs side by side (e.g. baseline vs optimized vs another model).

Usage: python evals/compare_reports.py baseline luna mini
Writes evals/reports/comparison.md
"""
import json
import sys

from common import REPORTS

METRICS = ["model", "pass_rate", "tool_accuracy", "constraint_precision", "safety_block_rate",
           "false_positive_rate", "grounded_rate", "judge_helpfulness", "judge_faithfulness",
           "latency_p50_s", "latency_p95_s", "avg_agent_tokens_per_case", "avg_cost_usd_per_case"]


def main(labels: list[str]) -> None:
    runs = {l: json.loads((REPORTS / f"agent_eval_{l}.json").read_text())["summary"] for l in labels}
    lines = ["# Agent eval comparison", "", "| Metric | " + " | ".join(labels) + " |",
             "|---|" + "---|" * len(labels)]
    for m in METRICS:
        lines.append(f"| {m} | " + " | ".join(str(runs[l].get(m)) for l in labels) + " |")
    groups = sorted({g for r in runs.values() for g in r["pass_rate_by_group"]})
    for g in groups:
        lines.append(f"| pass:{g} | " + " | ".join(str(runs[l]["pass_rate_by_group"].get(g)) for l in labels) + " |")
    out = "\n".join(lines) + "\n"
    (REPORTS / "comparison.md").write_text(out)
    print(out)


if __name__ == "__main__":
    main(sys.argv[1:] or ["baseline"])
