# Agent eval comparison

| Metric | optimized | model_gpt-5.4 | model_gpt-4o |
|---|---|---|---|
| model | gpt-6.2-astra | gpt-5.4 | gpt-4o |
| pass_rate | 1.0 | 0.95 | 0.925 |
| tool_accuracy | 1.0 | 0.968 | 0.935 |
| constraint_precision | 1.0 | 0.952 | 1.0 |
| safety_block_rate | 1.0 | 1.0 | 1.0 |
| false_positive_rate | 0.0 | 0.0 | 0.0 |
| grounded_rate | 1.0 | 1.0 | 0.971 |
| judge_helpfulness | 4.588 | 4.765 | 4.559 |
| judge_faithfulness | 4.235 | 4.735 | 4.559 |
| latency_p50_s | 11.61 | 7.73 | 6.83 |
| latency_p95_s | 18.98 | 12.93 | 9.09 |
| avg_agent_tokens_per_case | 3548 | 3014 | 2336 |
| pass:cart | 1.0 | 1.0 | 1.0 |
| pass:compare | 1.0 | 1.0 | 1.0 |
| pass:false_positive | 1.0 | 1.0 | 1.0 |
| pass:memory | 1.0 | 1.0 | 1.0 |
| pass:policy | 1.0 | 1.0 | 1.0 |
| pass:recommend | 1.0 | 0.833 | 0.833 |
| pass:safety | 1.0 | 1.0 | 0.889 |
