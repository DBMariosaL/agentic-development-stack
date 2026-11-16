# Fable Configuration Guide

Decision rules, not timeless facts. Everything with a number, identifier, or date must be re-verified before you present it as current. Read on 2026-11-16. Short source keys used below:

- [W] What's new in Fable 5.2 — `https://platform.claude.com/docs/en/models/fable-5-2/whats-new-fable-5-2`
- [M] Fable 5.2 migration guide — `https://platform.claude.com/docs/en/models/fable-5-2/migration-guide`
- [P] Prompting Fable 5.2 — `https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-fable-5-2`
- [E] Effort — `https://platform.claude.com/docs/en/build-with-claude/effort`
- [T] Thinking — `https://platform.claude.com/docs/en/build-with-claude/thinking`
- [X] Prefix checks — `https://platform.claude.com/docs/en/build-with-claude/preserved-thinking/prefix-checks`
- [C] Change tools or instructions — `https://platform.claude.com/docs/en/build-with-claude/preserved-thinking/change-tools-or-instructions`
- [R] Refusals and fallback — `https://platform.claude.com/docs/en/build-with-claude/refusals-and-fallback`
- [O] Models overview — `https://platform.claude.com/docs/en/models/overview`
- [CC] Claude Code model config — `https://code.claude.com/docs/en/model-config`

## Evidence labels

- `verified current` — confirmed in official Anthropic documentation on the date above;
- `workload recommendation` — this skill's operating preference, to test on the user's evals;
- `requires verification` — plausible but not confirmed for the target surface or date.

## Models

| Model | Claude API ID | Price in / out per MTok | Access |
| --- | --- | --- | --- |
| Claude Fable 5.2 | `claude-fable-5-2` | $8 / $40 | All Claude API customers [W] |
| Claude Mythos 5.2 | `claude-mythos-5-2` | $8 / $40 | Organizations verified through Anthropic's verification programs [W] |
| Claude Fable 5.1 | `claude-fable-5-1` | $10 / $50 | [O] |
| Claude Fable 5 | `claude-fable-5` | $10 / $50 | [O] |

Mythos 5.2 has the same capabilities as Fable 5.2 [W]. On Amazon Bedrock, Fable 5.2 is `global.anthropic.claude-fable-5-2` or `us.anthropic.claude-fable-5-2`, served only on the `bedrock-runtime` endpoint; Claude Platform on AWS, both Google Cloud offerings, and Microsoft Foundry use `claude-fable-5-2` [W].

Shared 5.2 specs [W][M]: 1M-token context (default and maximum); 128k max output (no 300k batch beta [T]); adaptive thinking always on; the tokenizer introduced with Opus 4.7; 30-day data retention required, so a Claude API request from an organization or workspace without it returns 400 `invalid_request_error`; not on Priority Tier; its own rate limit, separate from the one Fable 5.1 and Fable 5 share.

Routing: Anthropic recommends starting most workloads on Opus 5.5 and moving to Fable 5.2 for demanding reasoning and long-horizon agentic work, or when Opus 5.5 evals at higher effort still fall short [O][W]. In Claude Code no account type defaults to a Fable model, though a saved or managed setting can select one; `/model fable` selects Fable 5.2 [CC].

## Effort

Accepted values: `low`, `medium`, `high`, `xhigh`, `max`. Set with `output_config.effort` [E].

| Surface | Fable 5.2 default | Source |
| --- | --- | --- |
| Claude API | `high` | [E][W] |
| Claude Code, Claude apps | `medium` | [CC], launch post |
| Opus 5.5 on the Claude API, for contrast | `medium` | [E] |

A request moved from Opus 5.5 that omits `effort` runs one level higher on Fable 5.2 and succeeds silently [M]. Set it explicitly.

Documented guidance [P][E]: start at `high`, where most of the capability gain already sits; `low` suits quick back-and-forth and fast subagents, and on coding evals Fable 5.2 at `low` scored close to Fable 5.1 at higher effort; `medium` suits interactive coding and chat; `xhigh` only for the hardest long-running work with a measured gain; `max` for ceiling measurement. At `high` and above the model thinks before almost every reply, including a greeting. Effort barely changes reply length: use the prompt for length and tone. Lower effort is more likely to stop early on agentic work. Rerun the sweep rather than carrying a Fable 5.1 or Opus 5.5 setting over: levels rank the same across models but think different amounts [P].

Per-message effort (beta `mid-conversation-output-config-2026-07-01`) changes the level mid-conversation and keeps the cache; a new top-level value can invalidate cached messages [P][E]. Changing effort is not a prefix-check edit [X].

`workload recommendation`: for an orchestrating Fable, keep the lead at `high` and run routine subagents at `low` or `medium` on a cheaper model, then measure; see `references/orchestration-and-handoffs.md`.

## Thinking

On Fable 5.2, `thinking` omitted or `{"type": "adaptive"}` gives adaptive thinking; `"enabled"` with `budget_tokens`, `"disabled"`, and `"between_tools"` all return 400 [T]. Use effort for depth and `max_tokens` as the hard ceiling on thinking plus reply.

`thinking.display` [T]:

| Value | Reasoning blocks | Progress-update blocks |
| --- | --- | --- |
| `"omitted"` (default) | empty | empty |
| `"updates"` (beta `thinking-display-updates-2026-08-18`) | empty | summary text |
| `"summarized"` | summary text | summary text, not distinguishable from reasoning |

No setting returns the raw chain of thought [T]. Progress updates arrive as their own `thinking` block immediately before the `tool_use` they introduce, at most one per call, and the model can skip any of them; they count toward `output_tokens` at full length [T]. Render non-empty blocks; pass every block back unchanged.

Small `max_tokens`: thinking counts toward it, so a request can stop with `stop_reason: "max_tokens"` after a `thinking` block and before any text. A prompt line that kept Fable 5.1 from thinking does not keep Fable 5.2 from thinking at `medium` and above [M]. Raise `max_tokens` or lower effort.

## Preserved thinking and the prefix check

Each thinking block is bound to its prefix: `system`, `tools`, and every earlier message. Changing any of them, or leaving out a block between others, fails the prefix check [X].

| Model, `prefix_mismatch_behavior` unset | On failure |
| --- | --- |
| Fable 5.2, Mythos 5.2, Mythos 5.1 | 400 `... The block is bound to a different conversation` |
| Fable 5.1, Opus 5.5, Sonnet 5.5, Haiku 5.5 | possible 400, or no error and stale blocks reach the model |

Message Batches items that leave the setting unset get no error, and the API can drop the failing blocks [X]. Retrying the same body does not clear the 400 [M]. With beta `thinking-binding-controls-2026-08-01`, set `thinking.block_binding.prefix_mismatch_behavior` to `"error"` or `"drop_block"`; `input_transformations` reports each drop with `reason: "prefix_binding_mismatch"` [X]. Treat `"drop_block"` as a stopgap: the model re-thinks and spends more output tokens [P][W].

Nothing to change if Claude Code, claude.ai, Managed Agents, or the Agent SDK (with a constant system prompt) owns history [X]. Otherwise keep three habits: send assistant turns back exactly, empty thinking blocks included; build `system` and `tools` once per conversation; append every update at the end and leave it there [X].

What does not count as a change: `model`, `effort`, `max_tokens`, `tool_choice`, `thinking.display`, JSON key order, `cache_control` markers, an unreferenced `defer_loading` tool [X]. What does: one reworded word in a tool description; an MCP connector tool list that changes between requests, unless pinned (an edit for Fable 5.2 blocks, not for 5.1 or Opus 5.5 blocks) [M]; changing the advisor's `model` [W].

Change patterns [C]:

| Need | Append-only method |
| --- | --- |
| New standing instruction | `role: "system"` message after the newest user message; leave it in place |
| Per-turn reminder | Turn-scoped system message: `clear_at: "next_user_message"`, beta `mid-conversation-system-clear-at-2026-08-21`; it clears at the next user message and costs no input tokens |
| New date or environment value | Its own text block in the next user message, after tool results |
| Add or remove a tool | `tool_addition` / `tool_removal` block in a system message; beta `inline-tools-2026-09-15`, or `mid-conversation-tool-changes-2026-07-01` for named, pre-declared tools |
| Turn tools off for one request | `tool_choice: {"type": "none"}` |
| Shorten history | Compaction on demand (beta `compact-2026-09-04`) or context editing; a client-side cut needs the kept thinking removed or `"drop_block"` |
| File other people can edit (`AGENTS.md`, `CLAUDE.md`, memory) | Send its text only in a `tool_result` block, never in `system` or a system message |

Model switching: Fable 5.2 reads blocks from Fable 5.1, Opus 5.5, and the other listed models on the Claude API and Google-managed Google Cloud; only Fable 5.2 and Mythos 5.2 read Fable 5.2 blocks [W]. Moving off Fable 5.2 (to Opus 5.5, Fable 5.1, or a fallback model) drops its reasoning for the turns that run elsewhere: the request succeeds, dropped blocks are unbilled, the first turn after the switch costs more [M]. Fable 5.2 blocks also work only in the producing account or a linked one [W].

## Tool configuration

`tool_choice` `{"type": "auto"}` (default) and `{"type": "none"}` work; `{"type": "any"}` and `{"type": "tool", ...}` return 400, on Messages and token counting [M]. For schema-valid JSON use `auto` plus `strict: true` or JSON outputs [W]. In a customer-managed-encryption-key organization, structured outputs (strict tools and JSON outputs) are unavailable on Fable 5.2: leave out `strict` and validate in code [W][M].

To make the model call a tool, name the tool and its condition in the prompt; say when to use it rather than forcing it, so it thinks first [T].

Computer use: declare `computer_toolset_20260801`; `computer_20251124` returns 400 everywhere except Amazon Bedrock [W].

Advisor tool (beta): a Fable 5.2 or Mythos 5.2 executor accepts only a Fable 5.2 or Mythos 5.2 advisor, else 400; a Fable 5.2 advisor returns encrypted advice [W].

## Sampling and prefill

Non-default `temperature`, `top_p`, or `top_k` return 400; the `top_p` default is `0.99`, so `top_p: 1`, or both `temperature` and `top_p` together, also fail. From API version `2026-10-21`, any value of these parameters returns 400 on every model [T]. A prefilled final assistant turn returns 400 [M][T].

## Refusals, fallback, and billing

A decline is HTTP 200 with `stop_reason: "refusal"` and `stop_details.category` [R][P]:

| Category | Billed before any output | Default fallback |
| --- | --- | --- |
| `cyber` | no | `requires verification` per category |
| `bio` | yes | `requires verification` per category |
| `frontier_llm` | yes | `requires verification` per category |
| `reasoning_extraction` | yes | none: the refusal stands; change the prompt [W][R] |
| `general_harms` | no | `requires verification` per category |
| `null` | no | `requires verification` |

Refusals count against rate limits either way; a mid-stream refusal bills what streamed; discard partial output [R]. Server-side fallback: `fallbacks: "default"` with beta `server-side-fallback-2026-07-01`, Claude API and Anthropic-managed Google Cloud only; permitted targets for Fable 5.2 are `claude-opus-4-8` and `claude-opus-5`; later requests in a fallen-back conversation go straight to the fallback model only when they also send `fallbacks`, for about an hour and best-effort, so keep `fallbacks` on every call and handle the requested model being tried again; batches cannot use it; the fallback model does not receive Fable 5.2 thinking [R][M]. `fallbacks` does not carry over to model calls made inside tool execution, so subagent calls need their own [R]. In Claude Code, flagged requests re-run on Opus 5 (bio) or Opus 4.8 (cyber); a subagent never pauses to ask at a flagged request: it switches model or, with the "Ask each time" setting, fails [CC].

`frontier_llm` is a named category in the current table; benign machine-learning work can trigger it [R]. The launch post reports fewer unnecessary cyber and bio blocks than Fable 5.1. Organizations blocked on legitimate work can apply to the Cyber or Life Sciences Verification Programs [P].

## Pricing (USD per MTok) [W]

| Base input | 5m cache write | 1h cache write | Cache read | Output | Batch in / out | Fast mode in / out |
| --- | --- | --- | --- | --- | --- | --- |
| $8 | $10 | $16 | $0.20 | $40 | $4 / $20 | $16 / $80 |

Cache reads are 0.025x base input, the same multiplier as Fable 5.1 [W]. Fast mode is `speed: "fast"` on the Claude API and both Google Cloud offerings; Foundry uses a `claude-fable-5-2-fast` deployment; remove `speed: "fast"` in Managed Agents [W][M]. Fast mode is also available in Claude Code (product page).

## Migration to Fable 5.2

From Fable 5.1 (mostly drop-in; four breaking changes) [W][M]:

1. Update the model ID; check the separate rate limit.
2. If your code builds `messages`, run a session with `thinking-binding-controls-2026-08-01` and `"drop_block"`, log `input_transformations`, fix every `prefix_binding_mismatch`; then choose `"error"` or `"drop_block"` for production.
3. Expect Fable 5.1 to run without Fable 5.2 blocks if a router can move conversations back.
4. Move `computer_20251124` to the toolset; update any advisor to Fable 5.2 or Mythos 5.2.
5. Remove think-less prompt lines and lower effort instead; recheck small `max_tokens`.
6. Rerun the sweep from `high`, also at `medium` and `xhigh` [P], and review carried-over instructions with `references/behavior-fixes.md`.

From Opus 5.5 [M]: enable 30-day retention first if under ZDR; set effort explicitly (default rises to `high`); run the prefix-check test; handle every refusal category and name only Fable 5.2's fallback targets; remove structured outputs in CMEK organizations; recheck fast-mode platforms; update the advisor.

From Fable 5 [M]: forced `tool_choice` now returns 400; the prefix check applies; move per-request effort changes to per-message effort.

## Recommendation format

One row per relevant setting, columns `Setting | Recommendation | Evidence label | Why | Test`. Usual rows: model (compared with Opus 5.5), effort (explicit; sweep `high`/`medium`/`xhigh`), effort variation, `thinking.display`, `max_tokens`, output enforcement (CMEK), history and `prefix_mismatch_behavior`, subagent model, effort, and caps (cost with and without), refusal handling.
