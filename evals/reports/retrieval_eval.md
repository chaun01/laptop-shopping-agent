# Retrieval eval (30 queries, top-5, spec-based ground truth)

| Variant | P@5 | Hit@1 | MRR | Latency p50 | Latency p95 |
|---|---|---|---|---|---|
| v1_dense | 0.520 | 0.533 | 0.634 | 0.4s | 0.83s |
| v2_hybrid_no_rewrite | 0.587 | 0.667 | 0.726 | 0.39s | 0.42s |
| v2_rewrite_filters | 0.840 | 0.933 | 0.933 | 3.07s | 3.96s |
| v2_full_rerank | 0.853 | 0.967 | 0.967 | 5.61s | 11.89s |
