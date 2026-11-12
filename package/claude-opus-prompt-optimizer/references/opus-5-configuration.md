# Claude Opus 5 Configuration Guide

Decision rules, not timeless facts. Anything with a number, an identifier, or a date must be re-verified in official Anthropic documentation before you present it as current. Details below were verified on 2026-09-04, with the tool and sampling rows re-checked on 2026-09-25.

Use this file only for workloads that stay on Claude Opus 5. As of 2026-09-22 Anthropic recommends starting most workloads on Claude Opus 5.5, which is cheaper per token and differs on defaults and four request shapes; see `references/opus-5-5-configuration.md`, including its migration checklist from Opus 5.

## Evidence labels

- `verified current` — confirmed in current official Anthropic documentation;
- `workload recommendation` — this skill's operating preference, to test on the user's own evals;
- `requires verification` — plausible but not confirmed for the target surface or date.

## Model

| Field | Value |
| --- | --- |
| Claude API ID and alias | `claude-opus-5` |
| Amazon Bedrock | `anthropic.claude-opus-5` (also reachable via `InvokeModel` on `bedrock-runtime`) |
| Google Cloud | `claude-opus-5` |
| Microsoft Foundry | `claude-opus-5` (deployment name is what you send) |
| Claude Platform on AWS | available; the models table shows no separate ID |
| Context window | 1M tokens, both default and maximum; no smaller variant |
| Max output | 128k tokens synchronous; 300k on the Batch API with the `output-300k-2026-03-24` beta header |
| Thinking | adaptive, on by default |
| Default effort | `high` |
| Reliable knowledge cutoff | May 2026 |
| Retirement commitment | not sooner than 2026-07-24 for Anthropic-operated platforms |
| Priority Tier | not supported |

Anthropic's routing advice now starts most workloads on Opus 5.5, not Opus 5, and moves to Fable 5.1 for demanding reasoning and long-horizon agentic work. Reasons to stay on Opus 5: a validated production baseline you cannot re-evaluate yet, a hard dependency on `thinking: disabled`, forced `tool_choice`, or `computer_20251124` on the Claude API, or a Priority Tier plan (neither model supports it). Choose the model that clears the quality bar, then test cheaper or faster alternatives on representative cases.

Every Claude model ID is a pinned snapshot, including the dateless IDs used from the 4.6 generation on.

## Effort

Accepted values: `low`, `medium`, `high`, `xhigh`, `max`. Default: `high`. Setting `effort` to `"high"` is exactly equivalent to omitting the parameter. Set it on `output_config.effort`. No beta header for the top-level parameter.

Opus 5 converts additional effort into better results more reliably than any earlier Opus model, so the level you choose carries more weight than it used to. It is also unusually efficient at the bottom of the ladder: `low` and `medium` produce strong quality at a fraction of the tokens and latency of higher settings.

| Workload | Baseline | Evidence |
| --- | --- | --- |
| Default starting point for anything | `high` | verified current |
| Routine work, latency-sensitive work, subagents | `low` or `medium`, used liberally wherever evals show quality holds | verified current |
| Demanding coding and agentic work | `xhigh` | verified current |
| Tasks that justify unconstrained token spending | `max` | verified current |
| Code review | a fast pass at lower effort, a thorough pass later | verified current |

If you carried effort settings over from an earlier model, run a fresh sweep rather than reusing them. Opus 4.8 and 4.7 guidance started at `xhigh` for coding and agentic work; Opus 5 starts at `high` and steps down more readily.

Effort affects **all** output tokens — text, tool calls and their arguments, and thinking. Lower effort produces fewer and terser tool calls, combines operations, and skips preamble; higher effort produces more tool calls, plans before acting, and writes fuller summaries. It does **not** reliably control visible response length; prompt for that instead.

`adaptive` is a thinking mode, not an effort value. Do not pass it as `effort`.

### Per-message effort (beta)

Opus 5 supports changing effort mid-conversation without invalidating the prompt cache. Add a `role: "system"` message with empty `content` and the new level in `output_config.effort`; it takes effect from the next `user` turn and holds until changed. Beta header: `mid-conversation-output-config-2026-07-01`.

An effort-only system message carries no text, so the placement rules for mid-conversation system messages do not apply — it can appear anywhere in `messages`.

Changing the **top-level** value between requests does not preserve cached prefixes, because top-level effort shapes the rendered prompt. If you rely on caching across a long session, either use per-message effort or pick a level and hold it.

## Thinking

Adaptive thinking is on by default. `thinking: {"type": "adaptive"}` remains valid and equivalent to the default. Thinking tokens bill as output tokens and count toward `max_tokens`.

Disabling thinking is possible but restricted: `thinking: {"type": "disabled"}` is accepted only at effort `high` or below. At `xhigh` or `max` it returns a 400. This is enforced on every request to Opus 5 and later models, and is a breaking change from Opus 4.8 where disabling thinking was independent of effort.

Recommendation, and it is close to unconditional: **keep thinking enabled and control cost with lower effort.** For most tasks, thinking enabled at `low` effort performs better than thinking disabled at similar cost, and disabling thinking introduces two output artifacts. See `references/behavior-fixes.md`.

Parsing consequence: a response can begin with `thinking` blocks before the first `text` block, empty at the default `display: "omitted"`. Select content blocks by `type`. Pass thinking blocks back complete and unmodified with tool results.

## max_tokens

A hard limit on total output — thinking plus response text — enforced per request. Reaching it truncates with `stop_reason: "max_tokens"`.

At `xhigh` or `max` effort, set at least 64k so the model has room to think and act across subagents and tool calls, then tune. On workloads migrated from Opus 4.8 that previously ran without thinking, revisit the value: thinking now consumes part of it.

## Task budgets (beta)

Beta header: `task-budgets-2026-03-13`. Supported on Opus 5, Opus 4.8, Opus 4.7, Fable 5.1, Mythos 5.1, Fable 5, Mythos 5. Not supported on Sonnet 5, Opus 4.6, Sonnet 4.6, Haiku 4.5, or on Claude Code and Cowork surfaces.

Shape, under `output_config`:

```json
{
  "effort": "high",
  "task_budget": { "type": "tokens", "total": 64000 }
}
```

- `type` is always `"tokens"`.
- `total` is the tokens Claude may spend across the agentic loop — thinking, tool calls, tool results, and output.
- `remaining` is optional and defaults to `total`. Pass it only when your own code compacts or rewrites history between requests, so the countdown continues rather than resetting.

Minimum accepted `total` is 20,000 tokens; smaller values return a 400.

How it behaves: the model sees a server-side countdown marker and paces itself, finishing gracefully as the budget depletes. The countdown counts what the model *sees* — generated tokens plus new content such as tool results — not the payload you resend, so a full-history resend does not double-count. The countdown is visible only to the model; there is no `task_budget` field in the response `usage` object.

Budgets are advisory. `max_tokens` remains the enforced ceiling. Because a budget spans a whole loop and `max_tokens` caps each request, the two are independent — neither must be at or below the other.

Two failure modes to check: an undersized budget produces refusal-like behavior, and a client that both resends full history and decrements `remaining` itself makes the model wrap up early. Set a generous budget and let the server track it.

Caching consequence: the countdown marker is injected server-side per request, so it does not match across requests; and if you mutate `remaining` per request, the changed value invalidates any cache prefix containing it. Set the budget once on the initial request where you can.

## Fast mode (research preview)

Set `speed: "fast"` with the `fast-mode-2026-02-01` beta header. Supported on Opus 5 and Opus 4.8 only. Access is gated — contact your account manager or join the waitlist.

- Up to 2.5x higher output tokens per second. Same model weights and behavior; no change to intelligence or capability.
- The gain is in output tokens per second, not time to first token, and is most visible with streaming.
- Claude API only, including Claude Managed Agents. Not on Bedrock, Claude Platform on AWS, Google Cloud, or Microsoft Foundry. Not available with the Batch API or a Priority Tier commitment.
- Pricing: $10 / MTok input and $50 / MTok output — double the standard Opus 5 rate, applied across the full context window. Prompt-caching and data-residency multipliers stack on top.
- Dedicated rate limits, separate from standard Opus limits, surfaced in `anthropic-fast-*` response headers. Exceeding them returns 429 with `retry-after`.
- `usage.speed` reports `"fast"` or `"standard"`.
- Switching between fast and standard invalidates the prompt cache; requests at different speeds do not share cached prefixes.

Recommend fast mode only when latency has clear business value and the user accepts double the token price. It is a speed lever, not a quality lever.

## Tools and output enforcement

Prefer structured outputs or strict tool use over prose format instructions. Expose only the tools the task needs, and use plain trigger phrasing ("Use this tool when...") rather than emphatic insistence, which overtriggers on recent models.

`verified current`: Opus 5 accepts forced tool use (`tool_choice` of type `any` or a named tool); Opus 5.5 rejects it with a 400, so avoid building new dependencies on it.

`verified current`: non-default `temperature`, `top_p`, or `top_k` return a 400 on Opus 4.7 and later models, which includes Opus 5. Omit them.

`verified current`: prefilled assistant responses on the last assistant turn are unsupported from the Claude 4.6 generation onward and return a 400, so do not design around prefill on Opus 5.

### Mid-conversation tool changes (beta)

New on Opus 5. Add or remove tools between turns while preserving the prompt cache, instead of resending a fixed tool list for the life of a session. Beta header: `mid-conversation-tool-changes-2026-07-01`.

## Prompt caching

Minimum cacheable prompt length on Opus 5 is 512 tokens, down from 1,024 on Opus 4.8 — prompts too short to cache before can now create entries with no code changes. Cache reads cost 10% of the base input price.

Values that participate in the rendered prompt break cache matching when they change: top-level `effort`, `task_budget` values, and `speed`. Use per-message effort and a fixed budget where caching matters.

## Refusals and fallback

The `fallbacks` parameter is in beta and supports a `"default"` mode that applies Anthropic's recommended fallback models by refusal category instead of a list you maintain. Use the `server-side-fallback-2026-07-01` beta header, which accepts both `"default"` and explicit model lists; the earlier `server-side-fallback-2026-06-01` header accepts explicit lists only.

Any production integration needs a refusal branch. Confirm the current refusal categories and permitted fallback targets for Opus 5 on the refusals-and-fallback page before recommending a configuration.

## Pricing

$5 / MTok input, $25 / MTok output — unchanged from Opus 4.8. Batch API requests are 50% off. Cache reads cost 10% of base input.

Cost caveat for migrations: because thinking is on by default and thinking tokens bill as output, a workload that ran without thinking on Opus 4.8 produces more output tokens per request at the same per-token rates. Re-baseline rather than assuming parity.

## Migration checklist from Opus 4.8

Opus 5 performs well out of the box on existing Opus 4.8 prompts, so preserve the baseline and change one variable at a time.

1. Update the model ID to `claude-opus-5`.
2. Handle thinking on by default: select content blocks by `type` rather than reading `content[0].text` or assuming the first streamed block is text; pass thinking blocks back complete and unmodified with tool results.
3. Find every `thinking: {"type": "disabled"}`. At `xhigh` or `max` it now returns a 400 — either lower effort to `high` or below, or remove the `thinking` field. Prefer removing it.
4. Re-baseline cost and `max_tokens` for workloads that previously ran without thinking.
5. Run a fresh effort sweep. Opus 4.8 guidance started at `xhigh` for coding; Opus 5 starts at `high` and steps down readily.
6. Run the amplifier pass: remove verification instructions, double-check instructions, separate verification stages, and delegation encouragement.
7. Add length calibration on each surface the product uses — conversation, narration, written files.
8. Add a delegation rule and, on Claude Code or the Agent SDK, deterministic caps. Update a pinned SDK to 2.1.217 or later first.
9. Re-validate prompt-side vision workarounds; many are now unnecessary.
10. Consider the newly available levers: task budgets, per-message effort, mid-conversation tool changes, the lower cache minimum, and fast mode if latency justifies the price.
11. Re-run your evals.

## Recommendation format

Return only the relevant rows:

| Setting | Recommendation | Evidence | Why | Test |
| --- | --- | --- | --- | --- |
| Model | [value] | [label] | [workload rationale] | [comparison] |
| Effort | [value] | [label] | [complexity rationale] | [sweep] |
| Effort variation | fixed or per-message | [label] | [where the hard steps are] | [A/B on those turns] |
| Thinking | enabled (default) | [label] | [why disabling is not justified] | [artifact check] |
| `max_tokens` | [value] | [label] | [thinking plus reply] | [truncation check] |
| `task_budget` | [value or none] | [label] | [measured p99 spend] | [early-stop check] |
| `speed` | standard or fast | [label] | [latency value vs 2x price] | [OTPS and cost comparison] |
| Delegation caps | [depth, concurrency, spend] | [label] | [fan-out risk] | [spawn count check] |
| Output enforcement | prompt, strict tool use, or structured outputs | [label] | [parsing need] | [schema validation] |
| Caching | [strategy] | [label] | [session shape] | [cache hit rate] |
