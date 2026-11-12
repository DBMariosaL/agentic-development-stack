# Configuration and migration

Scope: API configuration unless explicitly labeled otherwise. Maintained target and verification date: [current-model.md](current-model.md). Recheck model-specific details before presenting them as current.

## Compatibility gates

| Item | GPT-6 Astra |
| --- | --- |
| Model | `gpt-6-astra` |
| Effort values | `low`, `medium`, `high`, `xhigh`, `max` |
| Context / maximum output | 1,050,000 / 128,000 tokens |
| Input / output modalities | Text and images / text |

Source: [model card](https://developers.openai.com/api/docs/models/gpt-6-astra). Context capacity is not a recommendation to load everything.

Tool calling requires Responses; Chat Completions remains usable for supported text workflows. Remove `temperature`, `top_p`, `top_logprobs`, Chat Completions `logprobs`, and Responses `message.output_text.logprobs` from `include`. Migrate `none` or `minimal` effort to a tested `low` candidate; otherwise preserve effective effort initially. EU data residency excludes Astra `fast` and `priority` service tiers. [Migration guidance](https://developers.openai.com/api/docs/guides/latest-model)

Do not infer API `ultra` from a Codex UI label or invent a `gpt-6-astra-pro` slug. The Astra guide lists pro-mode support, but the linked reasoning-mode section still describes GPT-5.6 specifically at verification. Reverify Astra syntax and access before recommending a runnable pro configuration.

## Choose effort through evidence

For an existing workflow, preserve its effective effort while establishing the migration baseline. For a new workload, use `low` for simple bounded transformations; compare `medium` and `high` for substantive work. Higher efforts are candidates when difficult failures justify their extra resources. These are workload recommendations, not a claimed Astra default. Do not silently change an explicitly selected model or budget.

Keep prose length separate from reasoning. Where supported, `text.verbosity` controls response detail; a short final answer does not require shallow reasoning. Verify the current request schema before emitting SDK code.

## Async tools and steering

Async functions/custom tools use `async: true`. The application runs the job and returns its output with the original `call_id`. A prompt alone does not implement a scheduler. Allow independent work while results are pending; require dependent conclusions to wait. Track completion, errors, and cancellation in the harness. [Async tools](https://developers.openai.com/api/docs/guides/async-tool-calling)

Astra steering uses Responses WebSockets. It does not undo actions or cancel already-started tools. A queued update is not proof it has been applied. Preserve completed work and feed results into the current continuation; avoid duplicate side effects. [Mid-turn steering](https://developers.openai.com/api/docs/guides/steering)

## Reasoning changes and history

`configuration_update` changes effort between responses in Astra standard, single-agent mode. Keep request-level effort stable for caching. Preserve update order; adjacent updates are invalid. Do not combine with automatic compaction/truncation or the standalone compact endpoint. An explicit `compaction_trigger` is supported; reapply the desired update afterward. Response effort metadata still reports request-level effort. [Reasoning updates](https://developers.openai.com/api/docs/guides/reasoning#change-reasoning-mid-conversation)

Preserve tool calls, results, and required opaque reasoning items when replaying history. Do not reconstruct them from a prose summary or request private reasoning. Validate state handling separately from prompt wording.

## Caching and output contracts

For GPT-5.6 and later, use `prompt_cache_options.ttl: "30m"` instead of legacy `prompt_cache_retention`. Stable prefixes aid reuse; cache writes and reads have different billing. Verify actual usage rather than promising savings. [Caching](https://developers.openai.com/api/docs/guides/prompt-caching)

Use Structured Outputs for parsed responses and function schemas for tool inputs. Validate semantics as well as JSON shape; refusal and incomplete responses need application handling. Missing source data must have an allowed representation. [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs)

## Migration experiment

Save the old prompt, effective configuration, tools, and expected behavior. First make required compatibility changes. Compare that runnable baseline with a candidate prompt on identical cases; tune effort separately. Record errors and regressions, not just successful examples. If endpoint or handler changes are outside the requested scope, identify that implementation dependency rather than claiming a prompt-only migration is complete.