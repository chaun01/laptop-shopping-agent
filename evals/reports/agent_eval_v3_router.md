# Agent eval - v3_router (gpt-6.2-astra)

| Metric | Value |
|---|---|
| n_cases | 56 |
| pass_rate | 0.982 |
| tool_accuracy | 0.971 |
| constraint_precision | 1.0 |
| safety_block_rate | 1.0 |
| safety_label_accuracy | 0.923 |
| false_positive_rate | 0.0 |
| grounded_rate | 1.0 |
| judge_helpfulness | 4.279 |
| judge_faithfulness | 4.372 |
| latency_p50_s | 9.38 |
| latency_p95_s | 20.21 |
| avg_agent_tokens_per_case | 2547 |

Pass rate by group: cart=1.0, compare=1.0, external_api=1.0, false_positive=1.0, memory=1.0, policy=1.0, recommend=0.917, safety=1.0

## Failed cases

- **r04** failed ['tools', 'constraints'] | tools=[] | answer: What’s your budget in USD?What’s your budget in USD?
