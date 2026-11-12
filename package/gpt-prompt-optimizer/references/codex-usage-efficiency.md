# Codex usage and execution budget

Use when the user asks to balance task quality against Codex allowance, time, or cost. Do not append a budget report to an ordinary rewrite.

Establish which resource constrains the user: elapsed time, API bill, subscription allowance, or human intervention. API token prices and Codex credit consumption are not interchangeable. Verify live plan and model information before stating rates or multipliers. This skill intentionally stores no fixed Codex multiplier.

Record the actual model, effective reasoning, execution mode, completed outcome, relevant checks, retries, tool calls, and agent count when available. Include elapsed time and usage only when measured. Do not estimate a percentage gain from a shorter prompt alone.

Compare candidates on the same task:
- preserve working effort during migration;
- reduce unnecessary context, repeated checks, and redundant handoffs first;
- test another effort or mode separately;
- use additional agents only when their independent work can justify coordination cost;
- stop when the requested result is verified.

Fast mode, pro mode, reasoning effort, and product intelligence labels are distinct controls. Verify support and billing on the actual surface before recommending changes. A recommendation is not authorization to spend or change account configuration.

For long tasks, document the scope ceiling and acceptance evidence. Add a numeric call, time, or cost budget when it is known or genuinely needed. Do not invent an available subscription balance or force an arbitrary three-cycle cap.

Current reference to recheck: [Managing Astra usage](https://help.openai.com/en/articles/20001516-managing-usage-with-gpt-6-astra-in-work-and-codex).