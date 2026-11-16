# Fable Configuration Guide

Decision rules, not timeless facts. Everything with a number, an identifier, or a date in it must be re-verified in official Anthropic documentation before you present it as current. Details below were verified on 2026-09-03.

## Evidence labels

Label a recommendation whenever the distinction matters:

- `verified current` — confirmed in current official Anthropic documentation;
- `workload recommendation` — this skill's operating preference, to test on the user's own evals;
- `requires verification` — plausible but not confirmed for the target surface or date.

## Models

| Model | Claude API ID | Notes |
| --- | --- | --- |
| Claude Fable 5.1 | `claude-fable-5-1` | Successor to Fable 5; long-running agentic coding, knowledge work, research |
| Claude Mythos 5.1 | `claude-mythos-5-1` | Same capabilities; Project Glasswing participants only |
| Claude Fable 5 | `claude-fable-5` | Prior generation |
| Claude Mythos 5 | `claude-mythos-5` | Project Glasswing only |

Other surfaces: Amazon Bedrock uses `anthropic.claude-fable-5-1`; Claude Platform on AWS, Google Cloud, and Microsoft Foundry use `claude-fable-5-1`.

Anthropic's own routing advice is to start most workloads on Claude Opus 5 and reach for Fable 5.1 for demanding reasoning and long-horizon agentic work, or when Opus 5 evals at higher effort still fall short. Do not choose by prestige. Pick the model that clears the quality bar, then test cheaper or faster alternatives on representative cases.

Shared specs for Fable 5.1 and Mythos 5.1:

- 1M token context window, default and maximum, at standard per-token pricing across the whole window;
- 128k max output tokens;
- adaptive thinking always on, depth controlled by `effort`;
- tokenizer introduced with Opus 4.7 — the same text produces roughly 30% more tokens than on models older than Opus 4.7, so re-baseline token budgets when migrating from those;
- 30-day data retention, not available under zero data retention unless expressly authorized; Covered Models.

## Effort

Accepted values on Fable: `low`, `medium`, `high`, `xhigh`, `max`. Default and recommended starting point: `high`.

Effort is the primary control for the intelligence, latency, and cost tradeoff. Level names do not correspond to the same amount of thinking across models, so a sweep is model-specific.

| Workload | Baseline | Evidence level |
| --- | --- | --- |
| Most tasks, and any long single-reply deliverable | `high` | verified current (documented default) plus workload recommendation |
| Routine work where a sweep shows quality holds | `medium`, then `low` | workload recommendation |
| Capability-sensitive work with a measured gain | `xhigh`, then `max` | workload recommendation, gated on measurement |
| Turns that need fresh retrieval while the session runs low | raise mid-conversation | verified current |

On Fable 5.1, `medium` roughly matches Fable 5 at lower cost, and `low` is often competitive with Opus and Sonnet models on cost per task while scoring higher. Include `low` in the comparison anywhere you would otherwise run a smaller model at a higher effort level.

Two effort-specific behaviors have their own fixes: reduced search triggering at `low`, and long pre-writing thinking at `xhigh` and `max`. Both are in `references/behavior-fixes.md`.

### Per-message effort (beta)

On Fable 5.1 you can change effort mid-conversation without invalidating the prompt cache: send `output_config` at the top level for the session default, and a `role: "system"` message carrying its own `output_config.effort` to change it from the next user turn. Beta header: `mid-conversation-output-config-2026-07-01`. Supported on Fable 5.1, Mythos 5.1, and Opus 5 on the Claude API.

Raise it for a hard step, lower it for routine ones. Changing `effort` between requests does not count as a history edit.

## Thinking

Adaptive thinking is always on and is the only mode. Both `thinking: {"type": "enabled"}` with `budget_tokens` and `thinking: {"type": "disabled"}` return 400. Omit `thinking` or send `{"type": "adaptive"}`.

There is no thinking-token cap. Use `effort` to shape depth and `max_tokens` as the hard ceiling.

`thinking.display` values:

| Value | Behavior | When to use |
| --- | --- | --- |
| `"omitted"` (default) | `thinking` blocks come back empty | No UI surface for reasoning or progress |
| `"summarized"` | Summarized reasoning plus progress updates | You want both |
| `"updates"` (beta `thinking-display-updates-2026-08-18`) | Progress updates as text, reasoning stays hidden | Agentic UIs that need status lines without exposing reasoning |

The raw chain of thought is never returned. Reasoning between tool calls appears in thinking blocks rather than text, and interleaved thinking is automatic with no beta header.

Never instruct the model to reproduce its reasoning as response text: on Fable 5 that can trigger the `reasoning_extraction` refusal category and elevated fallbacks. Read the structured blocks instead.

### Thinking-block binding

Every thinking block records which model produced it and is preserved in one direction: Fable 5.1 reads earlier models' blocks; no earlier model reads Fable 5.1's. Moving a conversation onto Fable 5.1 keeps its reasoning; moving off loses it for the turns that run elsewhere. Blocks a target model cannot read are dropped before the model sees them, unbilled, reported in `input_transformations` only with the `thinking-binding-controls-2026-08-01` beta header and silent without it.

Blocks are also bound to the exact conversation that produced them. Editing anything before a block — `system`, `tools`, or an earlier message — invalidates every later block. Enforced for accounts created on or after 2026-08-31; for older accounts the API records the mismatch and acts on it only when the request sets `thinking.block_binding.prefix_mismatch_behavior`. Mythos 5.1 does not run the check. Where enforced, replaying an invalidated block returns 400 with a message saying the block is bound to a different conversation; `prefix_mismatch_behavior: "drop_block"` drops and continues, reporting `reason: "prefix_binding_mismatch"`.

Claude Code, claude.ai, Claude Managed Agents, and the Claude Agent SDK preserve the prefix for you. Code that builds `messages` itself needs the check. See `references/behavior-fixes.md` for the safe and unsafe edit patterns.

## Turn-scoped system messages (beta)

A `role: "system"` message with `clear_at: "next_user_message"` carries system-prompt authority for the current turn and stops rendering once a later `user` message exists. It stays in `messages` and you keep sending it back verbatim, so nothing earlier changes: the prompt cache keeps matching, later thinking blocks stay valid, and a cleared message costs no input tokens. Beta header: `mid-conversation-system-clear-at-2026-08-21`.

```json
{
  "role": "system",
  "clear_at": "next_user_message",
  "content": "Results have landed in your inbox. Check it before running more code."
}
```

This is the correct mechanism for per-turn reminders in a tool loop. It replaces the inject-and-delete pattern entirely. For durable instruction or tool changes mid-session, use a plain mid-conversation system message or a mid-conversation tool change rather than rewriting `system` or `tools`.

## Tool configuration

Forced tool use is unsupported on Fable 5.1 and Mythos 5.1. `tool_choice` set to `{"type": "any"}` or `{"type": "tool", "name": "..."}` returns 400 `invalid_request_error`, on the Messages endpoint and on token counting. `{"type": "auto"}` (default) and `{"type": "none"}` are unchanged. The rationale is that thinking is always on and a forced call would skip it, pushing the working-out into the tool arguments and lowering argument quality.

Replacements:

| Old goal | Fable approach |
| --- | --- |
| Guarantee schema-valid JSON | `tool_choice: auto` with `strict: true` strict tool use, or structured outputs |
| Force a specific tool | Name the tool and its condition in the prompt; Fable follows explicit tool instructions reliably |
| Classification into fixed labels | A tool with an enum field, or structured outputs |

Expose only the tools the task needs. Aggressive tool language ("CRITICAL: you MUST...") now overtriggers; plain phrasing is enough.

Batch independent calls. Fable 5.1 parallelizes when a request names several things to fetch but can go serial in implied-read agent loops; the fix is a turn-scoped nudge, not a system prompt rule.

## Sampling and prefill

Non-default `temperature`, `top_p`, or `top_k` return 400. Prefilling the assistant response returns 400.

Prefill replacements: structured outputs or XML output tags for format control; a direct no-preamble instruction for skipping introductions; a user-message continuation quoting the interrupted text for continuations; tool-based or compaction-time context hydration for injected reminders.

## Caching and compaction

Minimum cacheable prompt length: 512 tokens. Cache writes are unchanged from Fable 5; cache reads on Fable 5.1 and Mythos 5.1 cost 0.025x base input against 0.1x on other Claude models, so long agentic sessions re-reading a cached prefix pay a quarter of the Fable 5 rate.

Consequence for prompt design: compacting early to save cost may no longer be the right tradeoff on Fable 5.1. Test later compaction points. Prefer server-side compaction or context editing, which do not count as history edits. Moving `cache_control` markers is safe.

If you must compact on the client, replace the whole history with one summary message plus the new user turn and replay no thinking blocks, and use the documented summarization instruction in `references/behavior-fixes.md`.

## Refusals, fallback, and billing

A declined request returns HTTP 200 with `stop_reason: "refusal"` and a `stop_details` object naming the policy area. Classifier domains include offensive cybersecurity, biology and life sciences, and extraction of the model's summarized thinking; benign work in those areas can also trigger them. Finding vulnerabilities in source code is permitted on Fable 5.1.

Fallback options: server-side fallback, SDK middleware, or your own retry. `fallbacks: "default"` (beta) retries on the model Anthropic recommends for that category. Permitted fallback targets for Fable 5.1 are Claude Opus 4.8 and Claude Opus 5.

Billing: no charge for a refusal that arrives before any output, and on Fable 5.1 fallback credit refunds the prompt-cache cost of switching models.

Design consequence: any production Fable integration needs a refusal branch. A prompt that cannot tolerate a fallback model's output is an architecture problem, not a prompt problem.

## Pricing (USD)

| Base input | 5m cache writes | 1h cache writes | Cache reads | Output |
| --- | --- | --- | --- | --- |
| $10 / MTok | $12.50 / MTok | $20 / MTok | $0.25 / MTok | $50 / MTok |

Batch processing: $5 / MTok input, $25 / MTok output.

Fable 5.1 is priced identically to Fable 5 except for the lower cache read price.

## max_tokens

Size it for thinking plus reply, not the reply alone. At `xhigh` and `max`, long-deliverable requests can spend a large share of the budget thinking; running them at `high` is usually the better answer. When you keep high effort, append the single-limit note from `references/behavior-fixes.md` and set `max_tokens` accordingly. Ceiling is 128k output tokens.

## Migration checklist to Fable 5.1

1. Update the model ID.
2. Remove `tool_choice` of type `any` or `tool`; move schema enforcement to strict tool use or structured outputs.
3. Pass thinking blocks back unchanged and make the history append-only. Move injected per-turn reminders to turn-scoped system messages; move `system` and `tools` changes to mid-conversation system messages; trim server-side or strip thinking blocks from turns carried across a client summary; pick a production `prefix_mismatch_behavior` and monitor `input_transformations`.
4. Remove `budget_tokens`, `thinking: disabled`, prefills, and non-default sampling parameters.
5. Audit prompts and skills for reflection or show-your-thinking instructions, anti-formatting blocks, and anti-narration lines.
6. Re-run the effort sweep from `high`, and consider changing effort mid-conversation instead of holding one level.
7. Set `thinking.display` to `"updates"` if your UI shows progress.
8. Watch for one tool call per turn in agent loops and add the turn-scoped batching note.
9. Adjust client timeouts, streaming, and progress indicators for longer turns; consider asynchronous run checks rather than blocking.
10. Re-run your evals. Refusal handling, fallback, and token counts carry over from Fable 5; cache reads cost less; default behaviors differ as listed in `references/behavior-fixes.md`.

## Recommendation format

Return only the relevant rows:

| Setting | Recommendation | Evidence | Why | Test |
| --- | --- | --- | --- | --- |
| Model | [value] | [label] | [workload rationale] | [comparison] |
| Effort | [value] | [label] | [complexity rationale] | [sweep] |
| Effort variation | fixed or per-message | [label] | [where the hard steps are] | [A/B on those turns] |
| `thinking.display` | omitted, summarized, or updates | [label] | [UI need] | [render check] |
| `max_tokens` | [value] | [label] | [thinking plus reply] | [truncation check] |
| Output enforcement | prompt, strict tool use, or structured outputs | [label] | [parsing need] | [schema validation] |
| Caching and compaction | [strategy] | [label] | [session length and cost] | [cost per task] |
| Refusal handling | [fallback strategy] | [label] | [domain risk] | [refusal injection test] |
