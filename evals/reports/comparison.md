# Agent eval comparison

| Metric | optimized | final_run1 | final_run2 |
|---|---|---|---|
| model | gpt-6.2-astra | gpt-6.2-astra | gpt-6.2-astra |
| pass_rate | 1.0 | 1.0 | 1.0 |
| tool_accuracy | 1.0 | 1.0 | 1.0 |
| constraint_precision | 1.0 | 1.0 | 1.0 |
| safety_block_rate | 1.0 | 1.0 | 1.0 |
| false_positive_rate | 0.0 | 0.0 | 0.0 |
| grounded_rate | 1.0 | 1.0 | 1.0 |
| judge_helpfulness | 4.588 | 4.556 | 4.611 |
| judge_faithfulness | 4.235 | 4.861 | 4.833 |
| latency_p50_s | 11.61 | 11.42 | 11.68 |
| latency_p95_s | 18.98 | 23.2 | 20.87 |
| avg_agent_tokens_per_case | 3548 | 3566 | 3743 |
| avg_cost_usd_per_case | None | 0.015 | 0.016 |
| pass:cart | 1.0 | 1.0 | 1.0 |
| pass:compare | 1.0 | 1.0 | 1.0 |
| pass:external_api | None | 1.0 | 1.0 |
| pass:false_positive | 1.0 | 1.0 | 1.0 |
| pass:memory | 1.0 | 1.0 | 1.0 |
| pass:policy | 1.0 | 1.0 | 1.0 |
| pass:recommend | 1.0 | 1.0 | 1.0 |
| pass:safety | 1.0 | 1.0 | 1.0 |
