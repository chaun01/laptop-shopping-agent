# Agent eval comparison

| Metric | final_run1 | v3_memory_bg | v3_router |
|---|---|---|---|
| model | gpt-6.2-astra | gpt-6.2-astra | gpt-6.2-astra |
| pass_rate | 1.0 | 1.0 | 0.982 |
| tool_accuracy | 1.0 | 1.0 | 0.971 |
| constraint_precision | 1.0 | 1.0 | 1.0 |
| safety_block_rate | 1.0 | 1.0 | 1.0 |
| false_positive_rate | 0.0 | 0.0 | 0.0 |
| grounded_rate | 1.0 | 1.0 | 1.0 |
| judge_helpfulness | 4.556 | 4.326 | 4.279 |
| judge_faithfulness | 4.861 | 4.581 | 4.372 |
| latency_p50_s | 11.42 | 12.16 | 9.38 |
| latency_p95_s | 23.2 | 25.63 | 20.21 |
| avg_agent_tokens_per_case | 3566 | 2815 | 2547 |
| avg_cost_usd_per_case | 0.015 | 0.013 | 0.013 |
| pass:cart | 1.0 | 1.0 | 1.0 |
| pass:compare | 1.0 | 1.0 | 1.0 |
| pass:external_api | 1.0 | 1.0 | 1.0 |
| pass:false_positive | 1.0 | 1.0 | 1.0 |
| pass:memory | 1.0 | 1.0 | 1.0 |
| pass:policy | 1.0 | 1.0 | 1.0 |
| pass:recommend | 1.0 | 1.0 | 0.917 |
| pass:safety | 1.0 | 1.0 | 1.0 |
