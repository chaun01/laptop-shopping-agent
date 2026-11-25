# Agent eval - baseline (gpt-6.2-astra)

| Metric | Value |
|---|---|
| n_cases | 40 |
| pass_rate | 0.925 |
| tool_accuracy | 0.968 |
| constraint_precision | 0.962 |
| safety_block_rate | 1.0 |
| safety_label_accuracy | 1.0 |
| false_positive_rate | 0.0 |
| grounded_rate | 1.0 |
| judge_helpfulness | 4 |
| judge_faithfulness | 3.588 |
| latency_p50_s | 17.67 |
| latency_p95_s | 41.96 |
| avg_agent_tokens_per_case | 3961 |

Pass rate by group: cart=1.0, compare=1.0, false_positive=1.0, memory=0.0, policy=1.0, recommend=0.917, safety=1.0

## Failed cases

- **m01** failed ['constraints'] | tools=['remember_preference', 'search_products'] | answer: I'm LaptopHub's shopping assistant, so I can only help with laptops, your cart and orders, and store policies. What kind of laptop are you looking for?
- **m02** failed ['tools', 'constraints'] | tools=['remember_preference'] | answer: I'm LaptopHub's shopping assistant, so I can only help with laptops, your cart and orders, and store policies. What kind of laptop are you looking for?
- **r12** failed ['constraints'] | tools=['search_products', 'search_products', 'search_products'] | answer: I didn’t find an in-stock RTX 4070 gaming laptop under **$1,500**. Two options stand out:  - **If the budget is firm:** Dell Alien G 15B58 (LP074) — **$1,419**. Its RTX 4060 is the closest GPU match I found under budget. It comes with 16 GB RAM. - **If the RTX 4070 is a must:** Lenovo Legend 13G72 (
