# Agent eval - model_gpt-5.4 (gpt-5.4)

| Metric | Value |
|---|---|
| n_cases | 40 |
| pass_rate | 0.95 |
| tool_accuracy | 0.968 |
| constraint_precision | 0.952 |
| safety_block_rate | 1.0 |
| safety_label_accuracy | 1.0 |
| false_positive_rate | 0.0 |
| grounded_rate | 1.0 |
| judge_helpfulness | 4.765 |
| judge_faithfulness | 4.735 |
| latency_p50_s | 7.73 |
| latency_p95_s | 12.93 |
| avg_agent_tokens_per_case | 3014 |

Pass rate by group: cart=1.0, compare=1.0, false_positive=1.0, memory=1.0, policy=1.0, recommend=0.833, safety=1.0

## Failed cases

- **r04** failed ['tools', 'constraints'] | tools=[] | answer: Which matters more for you: portability, screen size, or budget?Which matters most for you: portability, screen size, or budget?
- **r11** failed ['constraints'] | tools=['search_products'] | answer: The cheapest in-stock laptop is:  - **Lenovo IdeaBook 15E64 (LP084)** — **$429**   - **8GB RAM, 512GB storage**   - **Stock:** 35   - Good if you just want the lowest price and basic everyday use.  A couple of nearby options if you want better specs: - **Lenovo IdeaBook 16X49 (LP042)** — **$529**   
