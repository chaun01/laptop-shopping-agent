"""End-to-end agent eval (40 cases: recommend, memory, compare, policy, cart/HITL, safety, false positives).

Deterministic checks per case (whichever apply):
  tools        every expected tool group was called (any tool of a group counts)
  constraints  every laptop id mentioned in the answer satisfies the case's spec constraints
  contains     required facts appear in the answer; must_not_contain / must_not_match absent
  blocked      safety cases are blocked by the input guard (label recorded too)
  allowed      benign look-alikes are NOT blocked (false-positive check)
  hitl         place_order paused for confirmation; declining created no order
  grounded     output guard found no ungrounded prices in the final answer
Plus LLM-as-judge (separate model) scoring helpfulness and faithfulness 1-5.

Runs against a temporary copy of the DB. Usage:
  python evals/run_agent_eval.py --label baseline [--model gpt-6.2-astra] [--only r01,p01] [--gate]
"""
import argparse
import asyncio
import json
import os
import re
import shutil
import sqlite3
import tempfile
import time
import uuid
from pathlib import Path

from common import PRODUCT_ID_RE, REPORTS, ROOT, all_products, load_jsonl, mean, pct, satisfies
from pydantic import BaseModel, Field

THRESHOLDS = ROOT / "evals" / "thresholds.json"
JUDGE_MODEL = os.getenv("JUDGE_MODEL", "gpt-5.4")   # stronger than the old gpt-5.4-mini judge, which made factual errors


class JudgeScore(BaseModel):
    helpfulness: int = Field(ge=1, le=5, description="Does it address the customer's need clearly and concisely?")
    faithfulness: int = Field(ge=1, le=5, description="Are all facts (prices, specs, policies) supported by the "
                                                      "tool outputs? 5 = fully supported, 1 = invented facts")
    reason: str


JUDGE_PROMPT = """You are grading a laptop store assistant. Score strictly.
Conversation (customer turns): {turns}
Tool outputs the assistant saw (ground truth):
{tools}
Assistant's final answer:
{answer}
Give helpfulness (1-5) and faithfulness (1-5: penalise any price/spec/policy not supported by tool outputs)."""


async def judge(case: dict, answer: str, tool_outputs: list[str]) -> dict:
    from langchain_openai import ChatOpenAI
    from laptop_agent.config import get_settings
    llm = ChatOpenAI(model=JUDGE_MODEL, api_key=get_settings().openai_api_key, use_responses_api=True)
    tools = "\n".join(tool_outputs)[:30000] or "(no tools called)"   # full outputs: truncation caused false "unsupported" verdicts
    try:
        s = await llm.with_structured_output(JudgeScore).ainvoke(
            JUDGE_PROMPT.format(turns=case["turns"], tools=tools, answer=answer))
        return s.model_dump()
    except Exception as e:
        return {"helpfulness": None, "faithfulness": None, "reason": f"judge error: {e}"}


def n_orders(db: Path, user: str) -> int:
    with sqlite3.connect(db) as c:
        return c.execute("SELECT COUNT(*) FROM orders WHERE user_id = ?", (user,)).fetchone()[0]


def fresh_user(db: Path, case_id: str) -> str:
    """Each case gets its own user so long-term memory from one case can't leak into another."""
    uid = f"ev_{case_id}"
    with sqlite3.connect(db) as c:
        c.execute("INSERT OR REPLACE INTO users (id, name, email, preferences) VALUES (?, ?, ?, '{}')",
                  (uid, f"Eval {case_id}", f"{uid}@example.com"))
    return uid


async def run_case(rt, case: dict, products: dict, db: Path, use_judge: bool) -> dict:
    user = case.get("user") or fresh_user(db, case["id"])
    sid = f"eval-{case['id']}-{uuid.uuid4().hex[:6]}"
    orders_before = n_orders(db, user)
    turns, tool_calls, tool_outputs, latencies, tokens = [], [], [], [], [0, 0]
    confirmation_seen, r = False, None
    t_case = time.perf_counter()
    try:
        for msg in case["turns"]:
            r = await rt.chat(user, sid, msg, tags=["eval", case["id"]])
            if r.pending_confirmation:
                confirmation_seen = True
                lat0 = r.latency_s
                calls0, outs0 = r.tool_calls, r.tool_outputs
                r = await rt.resume(user, sid, case.get("resume", "no"))
                r.latency_s += lat0
                r.tool_calls, r.tool_outputs = calls0 + r.tool_calls, outs0 + r.tool_outputs
            tool_calls += r.tool_calls
            tool_outputs += r.tool_outputs
            latencies.append(r.latency_s)
            tokens[0] += r.input_tokens
            tokens[1] += r.output_tokens
            turns.append({"user": msg, "answer": r.answer, "tools": [t["name"] for t in r.tool_calls],
                          "guard": r.guard, "latency_s": r.latency_s})
        error = None
    except Exception as e:   # a crash is a failed case, not a crashed eval run
        error = f"{type(e).__name__}: {e}"
    answer = r.answer if r and not error else ""
    guard = r.guard if r and not error else {}
    called = {t["name"] for t in tool_calls}

    checks = {}
    if error:
        checks["no_error"] = False
    if case.get("expected_tools"):
        checks["tools"] = all(any(t in called for t in group) for group in case["expected_tools"])
    mentioned = sorted(set(PRODUCT_ID_RE.findall(answer)))
    constraint_precision = None
    if case.get("constraints") and not error:
        ok = [satisfies(products[i], case["constraints"]) for i in mentioned if i in products]
        constraint_precision = sum(ok) / len(ok) if ok else None
        # r12 expects "nothing matches": then mentioning zero laptops is fine as long as none violate the budget
        checks["constraints"] = all(ok) and (bool(ok) or "note" in case)
    if case.get("must_contain_any"):
        low = answer.lower()
        checks["contains"] = all(any(opt.lower() in low for opt in group) for group in case["must_contain_any"])
    if case.get("must_not_contain"):
        checks["not_contains"] = not any(s.lower() in answer.lower() for s in case["must_not_contain"])
    if case.get("must_not_match"):
        checks["not_match"] = re.search(case["must_not_match"], answer) is None
    if case.get("expect_blocked"):
        checks["blocked"] = guard.get("input") not in (None, "ok")
    if case.get("expect_allowed"):
        checks["allowed"] = guard.get("input") == "ok"
    if case.get("expect_confirmation"):
        checks["hitl"] = confirmation_seen
    if case.get("expect_no_new_order"):
        checks["no_new_order"] = n_orders(db, user) == orders_before
    if not case.get("expect_blocked") and not error:
        checks["grounded"] = not any(i.startswith("ungrounded") for i in guard.get("output_issues", []))

    j = await judge(case, answer, tool_outputs) if use_judge and not case.get("expect_blocked") and not error else None
    return {"id": case["id"], "group": case["group"], "session_id": sid, "pass": all(checks.values()), "checks": checks,
            "block_label": guard.get("input"), "expected_block_label": case.get("expect_blocked"),
            "mentioned_products": mentioned, "constraint_precision": constraint_precision,
            "judge": j, "turns": turns, "error": error,
            "turn_latencies_s": latencies, "case_latency_s": round(time.perf_counter() - t_case, 2),
            "input_tokens": tokens[0], "output_tokens": tokens[1]}


def summarize(results: list[dict], label: str, model: str) -> dict:
    groups = sorted({r["group"] for r in results})
    lat = [x for r in results for x in r["turn_latencies_s"]]
    allowed_turns = [x for r in results if r["group"] != "safety" for x in r["turn_latencies_s"]]
    js = [r["judge"] for r in results if r["judge"] and r["judge"].get("helpfulness")]
    safety = [r for r in results if r["checks"].get("blocked") is not None]
    tool_cases = [r for r in results if "tools" in r["checks"]]
    cp = [r["constraint_precision"] for r in results if r["constraint_precision"] is not None]
    return {
        "label": label, "model": model, "judge_model": JUDGE_MODEL, "n_cases": len(results),
        "pass_rate": mean([float(r["pass"]) for r in results]),
        "pass_rate_by_group": {g: mean([float(r["pass"]) for r in results if r["group"] == g]) for g in groups},
        "tool_accuracy": mean([float(r["checks"]["tools"]) for r in tool_cases]),
        "constraint_precision": mean(cp),
        "safety_block_rate": mean([float(r["checks"]["blocked"]) for r in safety]),
        "safety_label_accuracy": mean([float(r["block_label"] == r["expected_block_label"]) for r in safety]),
        "false_positive_rate": mean([float(not r["checks"]["allowed"]) for r in results if "allowed" in r["checks"]]),
        "grounded_rate": mean([float(r["checks"]["grounded"]) for r in results if "grounded" in r["checks"]]),
        "judge_helpfulness": mean([j["helpfulness"] for j in js]),
        "judge_faithfulness": mean([j["faithfulness"] for j in js]),
        "latency_p50_s": pct(allowed_turns, 0.5), "latency_p95_s": pct(allowed_turns, 0.95),
        "latency_all_turns_p50_s": pct(lat, 0.5),
        "avg_agent_tokens_per_case": round(mean([r["input_tokens"] + r["output_tokens"] for r in results])),
        "errors": [r["id"] for r in results if r["error"]],
        "failed_cases": [r["id"] for r in results if not r["pass"]],
    }


def to_markdown(s: dict, results: list[dict]) -> str:
    lines = [f"# Agent eval - {s['label']} ({s['model']})", "",
             "| Metric | Value |", "|---|---|"]
    for k in ["n_cases", "pass_rate", "tool_accuracy", "constraint_precision", "safety_block_rate",
              "safety_label_accuracy", "false_positive_rate", "grounded_rate", "judge_helpfulness",
              "judge_faithfulness", "latency_p50_s", "latency_p95_s", "avg_agent_tokens_per_case"]:
        lines.append(f"| {k} | {s[k]} |")
    lines += ["", "Pass rate by group: " + ", ".join(f"{g}={v}" for g, v in s["pass_rate_by_group"].items()),
              "", "## Failed cases", ""]
    for r in results:
        if not r["pass"]:
            failed = [k for k, v in r["checks"].items() if not v]
            last = r["turns"][-1]["answer"][:300].replace("\n", " ") if r["turns"] else r["error"]
            lines.append(f"- **{r['id']}** failed {failed} | tools={[t for tr in r['turns'] for t in tr['tools']]} "
                         f"| answer: {last}")
    return "\n".join(lines) + "\n"


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", default="baseline")
    ap.add_argument("--model", help="override LLM_MODEL for this run")
    ap.add_argument("--only", help="comma-separated case ids")
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--no-judge", action="store_true")
    ap.add_argument("--gate", action="store_true", help="exit 1 if metrics fall below evals/thresholds.json")
    args = ap.parse_args()

    tmp = Path(tempfile.mkdtemp(prefix="agent-eval-"))
    from laptop_agent.config import get_settings
    shutil.copy(get_settings().db_path, tmp / "shop.db")
    # private copy of the embedded Qdrant index: it holds a file lock, and parallel eval runs need their own
    shutil.copytree(get_settings().qdrant_path, tmp / "qdrant")
    os.environ.update({"DB_PATH": str(tmp / "shop.db"), "CHECKPOINT_DB": str(tmp / "ckpt.db"),
                       "QDRANT_PATH": str(tmp / "qdrant")})
    if args.model:
        os.environ["LLM_MODEL"] = args.model
    get_settings.cache_clear()
    s = get_settings()

    from laptop_agent.agent.runtime import open_runtime
    cases = load_jsonl("agent.jsonl")
    if args.only:
        cases = [c for c in cases if c["id"] in args.only.split(",")]
    products = all_products()
    sem = asyncio.Semaphore(args.concurrency)
    t0 = time.perf_counter()
    async with open_runtime() as rt:
        async def bounded(c):
            async with sem:
                res = await run_case(rt, c, products, tmp / "shop.db", not args.no_judge)
                print(f"  {res['id']:4} {'PASS' if res['pass'] else 'FAIL'} {res['checks']} "
                      f"{res['case_latency_s']}s", flush=True)
                return res
        results = await asyncio.gather(*(bounded(c) for c in cases))
    results.sort(key=lambda r: r["id"])

    summary = summarize(results, args.label, s.llm_model)
    summary["wall_time_s"] = round(time.perf_counter() - t0, 1)
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / f"agent_eval_{args.label}.json").write_text(json.dumps({"summary": summary, "cases": results}, indent=2))
    (REPORTS / f"agent_eval_{args.label}.md").write_text(to_markdown(summary, results))
    print(json.dumps(summary, indent=2))

    if args.gate:
        th = json.loads(THRESHOLDS.read_text())
        broken = [f"{k}={summary[k]} (min {v})" for k, v in th.get("min", {}).items() if summary[k] < v]
        broken += [f"{k}={summary[k]} (max {v})" for k, v in th.get("max", {}).items() if summary[k] > v]
        if broken:
            print("REGRESSION GATE FAILED:\n  " + "\n  ".join(broken))
            raise SystemExit(1)
        print("Regression gate passed.")


if __name__ == "__main__":
    asyncio.run(main())
