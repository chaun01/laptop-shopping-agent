"""Retrieval eval: compare v1 (dense) vs v2 variants on 30 queries with spec-based ground truth.

Metrics per query (top-5):
  P@5      share of returned laptops that satisfy every constraint
  Hit@1    top result satisfies every constraint
  MRR      1 / rank of the first relevant result
  Latency  seconds per query

Usage: python evals/run_retrieval_eval.py [--variants v1,v2_no_rerank,v2]
"""
import argparse
import json
import time

from common import REPORTS, all_products, load_jsonl, mean, pct, satisfies

from laptop_agent.rag.retriever import retrieve_products_v1, retrieve_products_v2

K = 5
VARIANTS = {
    "v1_dense": lambda q: retrieve_products_v1(q, k=K),
    "v2_hybrid_no_rewrite": lambda q: retrieve_products_v2(q, k=K, rewrite=False, rerank=False)[0],
    "v2_rewrite_filters": lambda q: retrieve_products_v2(q, k=K, rewrite=True, rerank=False)[0],
    "v2_full_rerank": lambda q: retrieve_products_v2(q, k=K, rewrite=True, rerank=True)[0],
}


def evaluate(name: str, fn, cases: list[dict], products: dict) -> dict:
    per_case = []
    for c in cases:
        n_relevant = sum(satisfies(p, c["constraints"]) for p in products.values())
        t0 = time.perf_counter()
        hits = fn(c["query"])
        latency = time.perf_counter() - t0
        rel = [satisfies(products[h["product_id"]], c["constraints"]) for h in hits[:K]]
        first = next((i for i, r in enumerate(rel) if r), None)
        per_case.append({"id": c["id"], "query": c["query"], "n_relevant_in_catalog": n_relevant,
                         "returned": [h["product_id"] for h in hits[:K]], "relevant": rel,
                         "p_at_5": sum(rel) / K, "hit_at_1": float(bool(rel and rel[0])),
                         "mrr": 1 / (first + 1) if first is not None else 0.0,
                         "latency_s": round(latency, 2)})
    lat = [r["latency_s"] for r in per_case]
    summary = {"variant": name, "p_at_5": mean([r["p_at_5"] for r in per_case]),
               "hit_at_1": mean([r["hit_at_1"] for r in per_case]), "mrr": mean([r["mrr"] for r in per_case]),
               "latency_p50_s": pct(lat, 0.5), "latency_p95_s": pct(lat, 0.95)}
    print(f"{name:22} P@5={summary['p_at_5']:.3f} Hit@1={summary['hit_at_1']:.3f} MRR={summary['mrr']:.3f} "
          f"p50={summary['latency_p50_s']}s p95={summary['latency_p95_s']}s")
    return {"summary": summary, "cases": per_case}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--variants", default=",".join(VARIANTS))
    args = ap.parse_args()
    cases, products = load_jsonl("retrieval.jsonl"), all_products()
    infeasible = [c["id"] for c in cases if not any(satisfies(p, c["constraints"]) for p in products.values())]
    if infeasible:
        print(f"WARNING: no relevant products exist for {infeasible}")
    results = {n: evaluate(n, VARIANTS[n], cases, products) for n in args.variants.split(",")}

    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "retrieval_eval.json").write_text(json.dumps(results, indent=2))
    lines = ["# Retrieval eval (30 queries, top-5, spec-based ground truth)", "",
             "| Variant | P@5 | Hit@1 | MRR | Latency p50 | Latency p95 |", "|---|---|---|---|---|---|"]
    for r in results.values():
        s = r["summary"]
        lines.append(f"| {s['variant']} | {s['p_at_5']:.3f} | {s['hit_at_1']:.3f} | {s['mrr']:.3f} | "
                     f"{s['latency_p50_s']}s | {s['latency_p95_s']}s |")
    (REPORTS / "retrieval_eval.md").write_text("\n".join(lines) + "\n")
    print(f"\nreport -> {REPORTS / 'retrieval_eval.md'}")


if __name__ == "__main__":
    main()
