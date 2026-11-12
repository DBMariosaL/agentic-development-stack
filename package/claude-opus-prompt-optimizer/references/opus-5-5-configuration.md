# Claude Opus 5.5 Configuration Guide

Decision rules for the current Opus model. Anything with a number, an identifier, or a date must be re-verified in official Anthropic documentation before you present it as current. Details below were verified on 2026-09-25 against the Opus 5.5 what's-new, migration, prompting, effort, fast-mode, task-budget, and models-overview pages.

For workloads still pinned to Claude Opus 5, use `references/opus-5-configuration.md` instead. The two models differ on defaults and on four request shapes that Opus 5.5 rejects.

## Contents

- Evidence labels
- Model
- Effort
- Thinking
- max_tokens
- Progress updates and `thinking.display`
- Thinking-block binding
- Tools and output enforcement
- Computer use
- Refusals and safeguards
- Task budgets, fast mode, caching
- Time signals for multiagent harnesses
- Pricing
- Migration checklist from Opus 5
- Migration notes from Opus 4.8 and earlier
- Recommendation format

## Evidence labels

- `verified current` — confirmed in current official Anthropic documentation;
- `workload recommendation` — this skill's operating preference, to test on the user's own evals;
- `requires verification` — plausible but not confirmed for the target surface or date.

## Model

| Field | Value |
| --- | --- |
| Claude API ID | `claude-opus-5-5` (fixed ID, no date suffix) |
| Amazon Bedrock | `anthropic.claude-opus-5-5` |
| Claude Platform on AWS | `claude-opus-5-5` |
| Google Cloud | `claude-opus-5-5` |
| Microsoft Foundry | `claude-opus-5-5` |
| Context window | 1M tokens by default, no beta header |
| Max output | 128k tokens |
| Thinking | adaptive, always on — cannot be disabled |
| Default effort | `medium` (Opus 5 defaults to `high`) |
| Training data cutoff | June 2026 |
| Retirement commitment | not sooner than 2027-09-22 |
| Priority Tier | not supported |

Anthropic's routing advice: start most workloads on Opus 5.5. Move to Fable 5.1 for demanding reasoning and long-horizon agentic work, or when Opus 5.5 evals at higher effort still fall short.

Where it is strongest (documented): multistep work in a real repository carried until tests pass; multi-hour audits and migrations with parallel subagents and little oversight; code review with more bugs caught and fewer false alarms than Opus 5; knowledge work with fewer wrong figures or citations; catching easy-to-miss details in large inputs; reading dense charts, diagrams, and screenshots without tools; computer use. It generates output tokens more than 30% faster than Opus 5 and tends to finish the same task in fewer tokens.

## Effort

Accepted values: `low`, `medium`, `high`, `xhigh`, `max`. Default: `medium`. Setting `effort` to `"medium"` is exactly equivalent to omitting it on Opus 5.5 — a request that omitted effort on Opus 5 ran at `high` and now runs one level lower. Set it on `output_config.effort`.

Effort is the only request parameter that controls thinking depth on Opus 5.5, and the first setting to adjust when trading intelligence against latency and cost.

Level names do not map to the same amount of thinking across models. In Anthropic's testing:

- Opus 5.5 at `medium` matches or exceeds Opus 5 at `high` on coding and knowledge-work evals, in fewer steps and tokens;
- on several coding evals, `low` comes close to that at much lower cost;
- at a *given* level, Opus 5.5 thinks more per turn than Opus 5, most of all at `xhigh` and `max` — carrying over an Opus 5 setting means longer turns and more output tokens.

| Workload | Baseline | Evidence |
| --- | --- | --- |
| Default starting point | `medium`, set explicitly | verified current |
| Former thinking-disabled or latency-critical integration | `low`, then measure; move to `medium` if quality drops | verified current |
| Subagents, simple tasks | `low` | verified current (effort table) |
| `xhigh` and `max` | only where you have measured a quality gain | verified current |
| Chat with slow time to first token | lower effort first; prompt lines second | verified current |

Run a fresh sweep instead of translating an Opus 5 setting. To get less thinking, lower the effort level first: it reduces thinking more reliably than prompt instructions do.

Per-message effort (beta, `mid-conversation-output-config-2026-07-01`) is supported and preserves the cache. Changing top-level effort between requests invalidates it.

## Thinking

Always on. A request with `thinking: {"type": "disabled"}` **or** a manual budget `thinking: {"type": "enabled", "budget_tokens": N}` returns a 400 `invalid_request_error` at every effort level. Omit the field, or send `thinking: {"type": "adaptive"}`, which is equivalent.

Consequences:

- Every response can begin with `thinking` blocks, empty at the default `display: "omitted"`. Select content blocks by `type`.
- Thinking tokens bill as output and count toward `max_tokens`, even when the text is not returned.
- Prompts tuned for thinking disabled on Opus 5 need four changes — see `references/behavior-fixes.md`, "Prompts written for thinking disabled".
- If time to first token still matters after dropping to `low`, a system line such as `Answer directly without deliberating.` can reduce thinking further. Measure quality when you add it.

## max_tokens

A hard limit on total output, thinking plus text. Because Opus 5.5 thinks more per turn at a given level, a limit sized for Opus 5 with thinking off can cut replies off. For the long turns of agentic coding, 128,000 — the model's maximum — has worked well in Anthropic's testing. At `xhigh` or `max`, start at 64k at the very least and tune.

## Progress updates and `thinking.display`

A response-shape change that fails no request. On Opus 5.5 (as on Fable 5.1), the short notes the model writes between tool calls arrive as progress-update `thinking` blocks rather than `text` blocks, at most one before each tool call. At the default `display: "omitted"` their text is empty, so a client that renders only `text` blocks goes silent during long agentic turns.

| `thinking.display` | Returns |
| --- | --- |
| `"omitted"` (default) | empty thinking fields |
| `"updates"` (beta, `thinking-display-updates-2026-08-18`) | progress-update text; reasoning stays hidden |
| `"summarized"` | reasoning summaries and progress updates mixed together |

Render each non-empty `thinking` block ahead of the `tool_use` block it precedes, and pass the blocks back unchanged.

Levers for update frequency, in order: (1) set `display: "updates"`; (2) give the model a simple send-message tool for verbatim mid-turn content, declared from the first request; (3) ask for a statement of intent before the first tool call and a short recap at the end in the system prompt; (4) have the harness append a turn-scoped system reminder after several silent tool steps (`clear_at: "next_user_message"`, beta `mid-conversation-system-clear-at-2026-08-21`), capped at two or three reminders. The documented reminder text is in `references/behavior-fixes.md`.

## Thinking-block binding

Every thinking block records the model that produced it and the prefix before it.

- **Across models.** Opus 5.5 reads thinking blocks from Opus 5 and earlier Opus, Sonnet, and Haiku models, not from Fable or Mythos. On the Claude API only Fable 5.1 and Mythos 5.1 read Opus 5.5's blocks. A router or fallback that moves a conversation off Opus 5.5 to any other model runs the following turns without its reasoning. Unreadable blocks are dropped silently and unbilled; the `thinking-binding-controls-2026-08-01` beta reports drops in `input_transformations`.
- **Within a conversation.** If the `system` prompt, `tools`, or an earlier message changed since a block was produced, replaying that block returns a 400 by default for accounts created on or after 2026-08-31 00:00 UTC. To drop instead, send the binding beta header and set `thinking.block_binding.prefix_mismatch_behavior: "drop_block"`.

Prevention: keep the conversation append-only. Change instructions or tools with mid-conversation system messages, `tool_addition` blocks, or inline tool definitions (beta `inline-tools-2026-09-15`), not by editing the prefix. Claude Code, claude.ai, Managed Agents, and the Agent SDK are already append-only. This also means system-prompt additions such as the unattended-run instruction belong in the first request of the session, not added midway.

For long sessions, compaction on demand (beta `compact-2026-09-04`) returns a signed summary block and can keep thinking in retained turns valid.

## Tools and output enforcement

`verified current`: forced tool use is not supported. `tool_choice` of `{"type": "any"}` or `{"type": "tool", ...}` returns a 400, including on token counting. `auto` (default) and `none` work. For schema-valid JSON use `auto` plus `strict: true`, or structured outputs. To make the model call a tool, say in the prompt when it applies.

`verified current`: non-default `temperature`, `top_p`, or `top_k` return a 400 on Opus 4.7 and later, Opus 5.5 included. Prefill on the last assistant turn returns a 400 from the 4.6 generation onward.

Expose only the tools the task needs and use plain trigger phrasing ("Use this tool when…").

## Computer use

On the Claude API and Google Cloud, only the `computer_toolset_20260801` toolset is accepted; a `computer_20251124` tool returns a 400. Drop the `computer-use-2025-11-24` beta header, send `{"type": "computer_toolset_20260801"}` without name or display dimensions, and update the loop for member `tool_use` blocks (action in the block's `name`), several per turn, with `toolset_name` echoed on every result. On Bedrock the earlier tool still works.

## Refusals and safeguards

Opus 5.5 is the first Opus model with Fable-level bio and cyber safeguards. Classifier categories include `cyber`, `bio`, and `reasoning_extraction`. A decline is HTTP 200 with `stop_reason: "refusal"` and a `stop_details` object naming the category.

- Finding vulnerabilities in source code is allowed; high-risk dual-use cyber activity is not.
- Everyday health and educational questions are unaffected. Life-sciences organizations blocked by the bio classifier can apply to the Life Sciences Verification Program.
- `reasoning_extraction`: prompts that push the model to reproduce its internal reasoning in the response text can be declined. Server-side fallback does **not** retry these; they come back to you. Remove such instructions and read `display: "summarized"` thinking instead.

Configure fallback: `fallbacks: "default"` (beta `server-side-fallback-2026-07-01`), SDK middleware, or your own retry. Remember that a fallback to a non-Fable model loses Opus 5.5's thinking blocks. Refusals count against rate limits; whether a pre-output refusal is billed depends on category.

In Claude apps and Claude Code, flagged messages move the conversation to an older model — see `references/claude-code-and-apps.md`.

## Task budgets, fast mode, caching

- **Task budgets** — beta, `task-budgets-2026-03-13`, supported on Opus 5.5. Same semantics as Opus 5: advisory, 20,000-token minimum, not on Claude Code or Cowork. See `references/cost-and-latency.md`.
- **Fast mode** — research preview, `speed: "fast"` with `fast-mode-2026-02-01`, Claude API (including Managed Agents) only. Up to 2.5x output tokens per second. Priced at $8 / $40 per MTok on Opus 5.5 (versus $10 / $50 on Opus 5 and 4.8). Gated access; switching speeds invalidates the cache. In Claude Code: `/fast`, requires extra usage turned on.
- **Caching** — 512-token minimum cacheable prompt. Cache reads cost 0.05x base input ($0.20 / MTok); 5-minute writes $5, 1-hour writes $8. Top-level effort, task-budget values, and `speed` break cache matching when changed.

## Time signals for multiagent harnesses

Opus 5.5 pays close attention to elapsed-time information. In a lead-agent-plus-subagents setup, have the harness append a line such as `elapsed 340s / 1200s` to each message it sends back. The model paces to finish inside the budget, usually well before; set the budget somewhat above the time you want spent. Without a sensible budget, show elapsed time alone and add one system sentence (documented text in `references/behavior-fixes.md`).

A time budget differs from lower effort: lower effort reduces the work; a budget mostly increases parallelism. It is advisory, so keep your own timeout, and check quality — under time pressure the model may search and verify a little less.

## Pricing

$4 / MTok input, $20 / MTok output — below Opus 5's $5 / $25. Batch: $2 / $10. Cache reads $0.20 / MTok. Fast mode $8 / $40.

Cost caveat: cheaper per token, but at the same effort level Opus 5.5 thinks more per turn, and a workload that ran with thinking disabled on Opus 5 now pays for thinking. Re-baseline on real traffic rather than assuming a 20% saving.

## Migration checklist from Opus 5

Existing Opus 5 prompts should perform well without changes. Handle the breaking changes first, then change one variable at a time.

1. Model ID `claude-opus-5` → `claude-opus-5-5`.
2. Remove every `thinking: {"type": "disabled"}` and `{"type": "enabled", "budget_tokens": ...}`. Lower effort where you previously disabled thinking.
3. Replace `tool_choice` `any` or `tool` with `auto` plus strict tool use, and say in the prompt when the tool applies.
4. Keep the conversation append-only; replace prefix edits with mid-conversation system messages or inline tool definitions. Check routers and fallbacks for model switches that drop thinking.
5. On the Claude API or Google Cloud, move `computer_20251124` to `computer_toolset_20260801`.
6. If the UI shows text between tool calls, read progress updates from `thinking` blocks and set `display: "updates"`.
7. Add refusal handling for `bio` and `reasoning_extraction`; remove prompt instructions that ask for reasoning in the reply.
8. Set `effort` explicitly and re-sweep. The default dropped to `medium`, and each level thinks more per turn than on Opus 5.
9. Revisit `max_tokens` — up to 128k for agentic coding.
10. Run the Opus 5.5 amplifier pass: delete "think carefully" lines, reasoning-in-reply requests, progress-summary scaffolding, and vision workarounds. Re-test Opus 5 dampers (length, correction narration, delegation, thinking-disabled mitigation) rather than assuming they are still load-bearing.
11. For unattended agents, treat a text-only `end_turn` as a report, not completion — see `references/behavior-fixes.md`.
12. Re-baseline cost and re-run evals.

## Migration notes from Opus 4.8 and earlier

Apply the Opus 5 checklist above, then: thinking now runs on requests that never set it (re-size `max_tokens`, re-baseline cost); the cache minimum dropped from 1,024 to 512 tokens; Priority Tier is unavailable. From 4.7 and earlier also: effort levels recalibrated (default `medium` versus `high`), 1M context without a beta header, mid-conversation system messages, fast mode. From 4.6 and earlier: `budget_tokens` thinking and non-default sampling parameters return 400; the tokenizer uses roughly 1x–1.35x as many tokens; drop "after every N tool calls, summarize progress" scaffolding.

## Recommendation format

Return only the relevant rows:

| Setting | Recommendation | Evidence | Why | Test |
| --- | --- | --- | --- | --- |
| Model | [value] | [label] | [workload rationale] | [comparison] |
| Effort | [value, set explicitly] | [label] | [complexity rationale] | [sweep] |
| Effort variation | fixed or per-message | [label] | [where the hard steps are] | [A/B on those turns] |
| `thinking.display` | omitted, updates, or summarized | [label] | [does a human watch the run?] | [silent-stretch check] |
| `max_tokens` | [value] | [label] | [thinking plus reply] | [truncation check] |
| `tool_choice` | auto (+ strict) | verified current | forced tool use returns 400 | [schema validation] |
| `task_budget` | [value or none] | [label] | [measured p99 spend] | [early-stop check] |
| Time signal | [budget or elapsed only] | [label] | [multiagent wall-clock] | [finish time vs quality] |
| `speed` | standard or fast | [label] | [latency value vs premium] | [OTPS and cost comparison] |
| Delegation caps | [depth, concurrency, spend] | [label] | [fan-out risk] | [spawn count check] |
| Refusal handling | [fallback mode] | [label] | [bio, cyber, reasoning_extraction] | [refusal-path test] |
| Caching | [strategy, append-only] | [label] | [session shape] | [cache hit rate, no binding 400s] |
