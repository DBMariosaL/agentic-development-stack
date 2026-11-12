# Cost and Latency Control

Opus 5.5 and Opus 5 have more independent cost levers than earlier models, and they are frequently confused with each other. Work them in order. Reaching for the wrong one is the single most common misconfiguration on both.

Opus 5.5 changes the starting point: it is 20% cheaper per token ($4 / $20 versus $5 / $25), generates output more than 30% faster, and tends to finish tasks in fewer tokens — but its default effort is `medium`, it thinks more per turn than Opus 5 at the same level, and thinking cannot be switched off. Re-baseline on real traffic instead of assuming the list-price saving.

## What each lever actually controls

| Lever | Scope | Controls | Hard or soft |
| --- | --- | --- | --- |
| `effort` | Per request | How deeply the model reasons at each step, and how many/how terse its tool calls are | Behavioral signal |
| `task_budget` | Per agentic loop, across requests | How much total work the model does before finishing | Advisory |
| `max_tokens` | Per request | Total generated tokens, thinking plus text | Hard cap |
| Prompt caching | Per request prefix | Input cost on repeated prefixes | Deterministic |
| Delegation caps | Per session | Subagent fan-out and spend | Hard, where the harness supports them |
| `speed: "fast"` | Per request | Output tokens per second, at 2x the model's standard price | Throughput only |
| Time signal (harness) | Per multiagent task | Wall-clock pacing and parallelism (Opus 5.5) | Advisory |
| Prompt length instructions | Per response | Visible output length | Behavioral |

The distinction that matters most: **effort tunes depth, task budgets tune breadth, `max_tokens` is the ceiling, and prompt instructions tune visible length.** Effort does not shorten replies. `max_tokens` does not pace an agentic loop. A task budget does not stop runaway generation within a single request.

## The ladder

Work top to bottom. Each step is cheaper to try and less likely to cost quality than the one below it.

### 1. Step down effort

The highest-leverage move on Opus 5, and the cheapest to test. `low` and `medium` produce strong quality at a fraction of the tokens and latency of higher settings, and review accuracy in particular holds at lower effort. Use them liberally wherever your evals show quality holds.

Sweep before assuming. If you carried effort settings from Opus 4.8 or 4.7, they are almost certainly too high — that guidance started at `xhigh` for coding and agentic work.

On Opus 5.5 this step is even stronger. `medium` (the default) matches or beats Opus 5 at `high` on coding and knowledge work, `low` often comes close at much lower cost, and a carried-over Opus 5 level buys *more* thinking per turn than it did. Lowering effort reduces thinking more reliably than any prompt instruction, so reach for it before prompt text. Reserve `xhigh` and `max` for measured gains.

### 2. Vary effort per message instead of holding one level

Rather than picking a single level for a whole session, run the hard steps high and the routine ones low. On Opus 5 a per-message effort change preserves the prompt cache, so this is close to free. Beta header `mid-conversation-output-config-2026-07-01`.

Changing the top-level value between requests does not preserve the cache, so do not do it that way in a cached session.

### 3. Fix prompt-side length

If the complaint is "responses are too long" or "the reports are bloated," no parameter fixes it. Calibrate each surface — conversation, agentic narration, written files — with its own instruction. See `references/behavior-fixes.md`.

This is frequently mistaken for a cost problem when it is a product problem, and vice versa: a team lowering effort to shorten replies gets lower quality at the same length.

### 4. Remove the amplifiers

Over-verification, double-check instructions, verification subagents, and delegation encouragement all spend tokens for no quality gain on Opus 5. Deleting them is a pure cost win. Do this before adding any budget.

### 5. Cap delegation

Subagent sprawl multiplies both cost and wall-clock (documented for Opus 5; Opus 5.5 fan-outs are recommended for large audits and migrations, so cap rather than forbid). Use a prompt rule and, on Claude Code or the Agent SDK, the deterministic caps: `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH`, `CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS`, and the SDK's `max_budget_usd`. Requires Claude Code 2.1.217 or later.

Run subagents themselves at `low` effort where the subtask allows — that is the documented use case for `low`.

### 6. Give multiagent runs a time signal (Opus 5.5)

If wall-clock is the constraint on a lead-agent-plus-subagents run, have the harness append elapsed time against a budget (`elapsed 340s / 1200s`) to each message it sends back, or elapsed time alone plus the documented "Time matters here" sentence. The model mostly responds by parallelizing more, not by doing less, and usually finishes well inside the budget. Set the budget a little above the time you want spent, keep a hard timeout, and check quality — it may search and verify slightly less under pressure.

### 7. Set a task budget

Once the loop is lean, give it a ceiling to pace against. Use a budget when you want the model to self-regulate on long-horizon work, have a predictable per-task cost or latency ceiling, or want graceful finishing — summarize findings, report progress — rather than a mid-action cutoff.

Size it from measurement:

1. Run a representative sample of tasks **without** `task_budget`.
2. For each task, sum `usage.output_tokens` across every request in the loop, plus the tokens of tool results you append between requests.
3. Record the distribution and start at the p99.
4. Test up or down from there.

Do not guess a round number. A budget too small for the task causes refusal-like behavior — declining, aggressive scope reduction, or early stops. Minimum accepted `total` is 20,000 tokens.

### 8. Exploit caching

The minimum cacheable prompt is 512 tokens on Opus 5.5 and Opus 5, down from 1,024 on Opus 4.8. Cache reads cost 10% of base input on Opus 5 and 5% on Opus 5.5 ($0.20 / MTok).

On Opus 5.5, keep the conversation append-only: editing the `system` prompt, `tools`, or earlier messages both misses the cache and, on accounts created from 2026-08-31, turns thinking-block replay into a 400. Add tools with mid-conversation `tool_addition` or inline definitions (beta `inline-tools-2026-09-15`), and use turn-scoped system messages for reminders.

Protect cache hits by not mutating values that participate in the rendered prompt: top-level `effort`, `task_budget` fields including `remaining`, and `speed`. Mid-conversation tool changes (beta `mid-conversation-tool-changes-2026-07-01`) let you add or remove tools between turns while preserving the cache, instead of resending a fixed list all session.

### 9. Set max_tokens deliberately

Not a tuning knob — a safety ceiling. Size it for thinking plus reply. At `xhigh` or `max`, start at 64k. On Opus 5.5, which thinks more per turn, 128k (the model maximum) worked well for long agentic-coding turns in Anthropic's testing. Too low and you truncate with `stop_reason: "max_tokens"`; too high costs nothing by itself.

### 10. Consider fast mode, last

Fast mode buys up to 2.5x output tokens per second at double the model's token price: $8 / $40 per MTok on Opus 5.5 (versus $4 / $20), $10 / $50 on Opus 5 (versus $5 / $25). In Claude Code it is `/fast` and needs extra usage turned on; it suits back-and-forth work where someone reads each reply. It changes nothing about intelligence or output length, so it converts money into wall-clock and nothing else.

Only worth it when latency has clear business value, the workload streams, and the gain is in output tokens per second rather than time to first token. Note the constraints: Claude API only, gated access, no Batch API, no Priority Tier, dedicated rate limits, and switching speeds invalidates the cache.

## What not to do

**Do not disable thinking as a cost measure.** On Opus 5.5 it returns a 400 at every level. On Opus 5 it is capped at `high` effort, returns a 400 above that, and produces leaked tool calls and internal XML tags. Thinking enabled at `low` effort performs better than thinking disabled at similar cost.

**Do not reach for "think less" prompt text first on Opus 5.5.** Effort reduces thinking more reliably. Deleting "think carefully" lines is the prompt-side win; adding "Answer directly without deliberating." is a measured last step.

**Do not mirror the task budget client-side.** If you resend full history every request *and* decrement `remaining`, the model sees an under-reported budget and finishes early. Set a generous budget and let the server track the countdown.

**Do not conflate payload size with budget spend.** The countdown counts what the model sees — generated tokens plus new content — not what your client transmits. Resent history is counted once, not once per request.

**Do not change several levers at once during evaluation.** Effort, budget, and prompt length instructions all move token counts; changing them together makes the result uninterpretable.

## Measuring

Record per task: model, effort, `max_tokens`, budget if set, `speed`, request count, `usage.output_tokens` summed across the loop, tool-result tokens appended, cache reads and writes, wall-clock, subagent count, and task success.

Optimize successful task completion per unit of constrained resource. Fewer tokens is not a win if it produces retries, partial results, or manual repair. On a workload migrated from Opus 4.8 that ran without thinking, expect more output tokens per request at the same rates and re-baseline before drawing conclusions.
