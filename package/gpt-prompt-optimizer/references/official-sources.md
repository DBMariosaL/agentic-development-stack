# Source discipline and future updates

Use official, feature-specific documentation for volatile model and API claims. Search the exact target and open the matching page; a search snippet or a generic "latest" title is insufficient. Preserve explicit older-model targets.

Prefer model cards and API guides for compatibility, product documentation for Codex/ChatGPT surfaces, and official release material for behavioral claims. Author reports can suggest experiments but do not establish supported parameters. If a supplied source is inaccessible, record the limitation instead of citing a secondary reproduction as the original.

## Sources checked for this update, 2026-09-10

| Source | Purpose |
| --- | --- |
| [Astra guidance](https://developers.openai.com/api/docs/guides/latest-model) | Behavior and migration |
| [Exact Astra Markdown guide](https://developers.openai.com/api/docs/guides/latest-model/gpt-6-astra.md) | Explicit target content; read via HTTP when web rendering failed |
| [Astra model card](https://developers.openai.com/api/docs/models/gpt-6-astra) | Identifier, effort support and limits |
| [Release overview](https://openai.com/index/gpt-6-astra/) | Professional artifacts and reported capabilities |
| [Reasoning](https://developers.openai.com/api/docs/guides/reasoning) | Effort updates, state and compatibility |
| [Async tools](https://developers.openai.com/api/docs/guides/async-tool-calling) | Application job handling |
| [Steering](https://developers.openai.com/api/docs/guides/steering) | WebSocket updates and pending actions |
| [Caching](https://developers.openai.com/api/docs/guides/prompt-caching) | Prefix reuse, TTL and billing distinction |
| [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs) | Parsed output contracts |
| [Evaluation](https://developers.openai.com/api/docs/guides/evaluation-best-practices) | Representative comparisons |
| [Hosted optimizer](https://developers.openai.com/api/docs/guides/prompt-optimizer) | Dataset requirements and manual review |
| [Astra usage](https://help.openai.com/en/articles/20001516-managing-usage-with-gpt-6-astra-in-work-and-codex) | Separate subscription accounting |

Initial [X post](https://x.com/pvncher/status/2095991462416490862): direct retrieval failed; not treated as verified primary content.

The general reasoning-best-practices page still contains older o-series versus GPT distinctions. Do not transfer those model-specific statements to Astra. The reasoning-mode section describes GPT-5.6 while Astra guidance lists pro support: keep the exact Astra pro configuration unresolved until sufficiently specific documentation establishes it.

## Maintain without renaming

1. Research the explicitly requested release. Confirm the identifier, current guide, behaviors, limitations, and supported surface.
2. Replace the dated facts in `current-model.md` and relevant compatibility guidance in `model-configuration.md`. Update this source record.
3. Reassess existing workarounds against the new evidence. Preserve domain constraints and passing behavior; do not perform a global model-name substitution.
4. Adapt only affected examples and regression cases. Keep skill slug `gpt-prompt-optimizer`, display name `GPT Prompt Optimizer`, and invocation stable.
5. Validate frontmatter, internal links, UI metadata, preserved utilities, and realistic use cases. Distinguish static checks, behavioral exercises, and real model benchmarks.

Record a verification date and uncertainty for durable claims. If official pages disagree, identify the inconsistency and prefer the specific applicable contract; do not conceal the conflict with a guessed value.