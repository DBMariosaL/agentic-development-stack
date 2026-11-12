---
name: claude-opus-prompt-optimizer
description: create, audit, migrate, and eval-tune production prompts, CLAUDE.md files, and agent scaffolding for claude opus 5.5 and claude opus 5. use when the user provides a rough request, a system prompt, CLAUDE.md, harness code, tool definitions, subagent wiring, eval data, or model outputs, or asks about opus 5.5 or opus 5 effort levels (medium default on 5.5), always-on thinking, "think carefully" lines, done criteria, unattended agents that stop early, silent progress updates and thinking.display, thinking-block binding, forced tool use errors, reasoning_extraction or bio/cyber refusals, flagged messages switching models in claude apps or claude code, pasted-content injection, multi-app automation, subagent fan-out and time signals, frontend design defaults, response length and narration, over-verification, task budgets, fast mode, cost control, or migration from claude opus 5, 4.8, or 4.7 to opus 5.5. verify volatile opus facts against official anthropic documentation before presenting them as current.
---

# Claude Opus 5.5 / Opus 5 Prompt Optimizer

Build the smallest prompt that reliably completes the real task on Claude Opus 5.5 — the current default Opus — or on Claude Opus 5 for workloads that stay there. Both models already do, unprompted, most of what older prompts asked for: they verify their work, catch their mistakes, report progress, and finish tasks end to end. Opus 5.5 adds three things on top: it works longer on its own, reports plainly what it did and what it needs from you, and thinks before every reply. The dominant failure mode is no longer under-instruction. It is **doubling** — an instruction that compounds with a behavior the model already has.

Optimizing for these models is three moves: remove the amplifiers, add dampers where a default runs hot, and — new with Opus 5.5 — give long runs a finish line and name which stops you want.

For Claude Fable 5.1, Fable 5, or Mythos, use the `claude-fable-prompt-optimizer` skill instead — different model, different failure modes, different API constraints.

## Which model the user is on

Default to Opus 5.5 when the user says "Opus" without a version or is starting fresh. Anthropic now routes most workloads to Opus 5.5 first ($4 / $20 per MTok versus $5 / $25, more than 30% faster output, fewer tokens per task), and to Fable 5.1 when Opus 5.5 at higher effort still falls short. Stay on Opus 5 guidance when the user is pinned there. The differences that change your advice:

| | Opus 5.5 | Opus 5 |
| --- | --- | --- |
| Default effort | `medium`; each level thinks more per turn than on Opus 5 | `high` |
| Thinking | always on; `disabled` or `budget_tokens` → 400 at any effort | on by default; `disabled` allowed at `high` or below |
| Forced `tool_choice` (`any`, `tool`) | 400 | accepted |
| Text between tool calls | progress-update `thinking` blocks, empty unless `display` returns them | `text` blocks |
| Thinking blocks | bound to model and prefix; prefix edits → 400 on newer accounts | — |
| Refusal categories | `cyber`, `bio`, `reasoning_extraction` | `cyber` |
| Main documented dampers | done criterion, stop rules, settled answers, pasted-content marking, explore-broadly, time signals, design exclusions | length, narration, deliverable length, correction narration, delegation caps, scope |

Opus 5 dampers are a reasonable starting point on Opus 5.5 — Anthropic says existing Opus 5 prompts should perform well — but re-test whether each is still load-bearing.

## Amplifiers to remove

Every row is a documented behavior that a legacy instruction makes worse. Check for these before writing anything new.

| Legacy instruction | What the model already does | Result of keeping it | Model |
| --- | --- | --- | --- |
| "Think carefully", "think step by step", "think hard" | Opus 5.5 always thinks and decides how much | Slower first token, no clear quality gain | 5.5 (inert-to-harmful on 5) |
| "Show your reasoning", "write out your chain of thought" in the reply | Reasons in thinking blocks | `reasoning_extraction` refusal; fallback won't retry | 5.5 |
| "After every N tool calls, summarize progress" | Writes progress updates between tool calls | Duplicate chatter, more tokens | both |
| "Include a final verification step", "use a subagent to verify" | Verifies its own work unprompted | Over-verification; wasted tokens | both |
| "Double-check your answer", "re-verify before responding" | Catches and fixes its own mistakes | Compounds; cost without benefit | both |
| Harness scaffolding that adds a separate verification stage | Same | Same | both |
| "Delegate aggressively", "use subagents where possible" | Delegates readily | Multiplied cost on small tasks | both (documented on 5) |
| "Explain what you're doing as you work" | Narrates readily | Per-message output grows | both (documented on 5) |
| "Avoid a generic look" | Falls back on its own default styles | Swaps one default for another | 5.5 |
| Lowering `effort` to shorten replies | Effort controls thinking, not visible length | Same length, lower quality | both |
| Disabling thinking to cut cost | — | 400 on 5.5; on 5, 400 above `high` plus leaked tool calls and XML tags | both |
| "Do not think", "do not reason" | — | Tag leakage when thinking is off; inert otherwise | both |
| Prompt-side vision workarounds for older models | Strong on charts, diagrams, screenshots; 5.5 at `low` reads dense charts better than 5 at its highest effort | Dead weight; re-validate | both |

Corollaries worth stating in any audit:

**Effort is the thinking lever; the prompt is the length lever.** On Opus 5.5, lowering effort reduces thinking more reliably than any prompt line, so reach for it first. Neither model shortens visible replies when effort drops — conversational verbosity, agentic narration, and files on disk each need their own instruction.

**Literal instruction following cuts both ways.** A limiting instruction is followed exactly. Where you want breadth, ask for everything and filter separately. Where the limit *is* the acceptance criterion — the claude.dev review prompt's "only problems you'd block the merge for" — keep it and say why.

**Continuation is a harness property, not only a prompt property.** On Opus 5.5 a text-only `end_turn` is often a progress report, not completion. Unattended loops need end-of-turn handling as well as the prompt instruction.

## Workflow

1. Identify the real objective, target user, model (Opus 5.5 or 5), surface (Claude API, Bedrock, Vertex, Foundry, Claude Code, Agent SDK, Managed Agents, claude.ai), inputs, expected output, tools, side effects, run length, whether a human watches the run, and failure modes.
2. Classify the request:
   - create a prompt, `CLAUDE.md`, or agent scaffold from a rough request;
   - audit or repair an existing prompt, skill, `CLAUDE.md`, or system prompt;
   - migrate from Opus 5, 4.8, or 4.7 to Opus 5.5 (or from 4.8/4.7 to Opus 5);
   - diagnose an observed behavior (early stops, silent UI, slow first tokens, refusals, 400s, long replies, heavy narration, bloated documents, over-verification, subagent sprawl, scope expansion, generic design);
   - control cost or latency;
   - optimize from examples, outputs, graders, or eval datasets;
   - coach a Claude Code or Claude app user on working with Opus 5.5.
3. Inspect every supplied material before drafting: prompt assembly code, message roles, tool schemas, `tool_choice`, effort and thinking settings, `thinking.display`, `max_tokens`, whether the conversation is append-only, end-of-turn handling, subagent wiring and caps, fallback routing, sample outputs, eval data.
4. Map each symptom to its fix with `references/behavior-fixes.md` (Opus 5.5 index first, then Opus 5).
5. Verify volatile facts (model IDs, effort defaults, beta headers, parameter names, prices, restrictions) against official Anthropic sources. Follow `references/official-sources.md`.
6. Remove amplifiers first. List them explicitly with the behavior each was compensating for. Then choose the smallest pattern from `references/prompt-patterns.md` and add dampers only for identified risks (`references/hardening-matrix.md`).
7. If cost or latency is a constraint, work the ladder in `references/cost-and-latency.md`.
8. Draft the prompt and recommend configuration with `references/opus-5-5-configuration.md` (or `references/opus-5-configuration.md`).
9. Validate coverage, contradictions, tool rules, permission boundaries, done criterion, stop rules, output format, and scope.
10. Provide compact tests targeting the most likely failures, plus an effort sweep with effort set explicitly. When eval data exists, follow `references/evaluation-playbook.md`.

## Intake rules

Accept any combination of: a rough natural-language request; an existing system, developer, or user prompt; a `CLAUDE.md`, project instructions, skill, or agent definition; tool or MCP schemas; harness code; policy or domain files; CSV, JSON, JSONL, or logs with test cases, outputs, labels, or grader results; latency, cost, quality, safety, or formatting requirements.

Do not ask for optional context when a useful result can be produced under explicit assumptions or placeholders. Ask first only when the missing answer changes architecture, scope, security, side effects, acceptance criteria, or an expensive implementation path. Whether a human is in the loop is often one of those — the unattended-run instruction is wrong for human-in-the-loop products — so infer it from context or ask.

## Source and freshness rules

When current model behavior matters:

- search only official Anthropic properties listed in `references/official-sources.md`;
- prefer the target model's prompting page over the cross-model best-practices page, and both over release posts and playbooks;
- use the claude.dev playbook for Claude apps and Claude Code usage, not for API parameters;
- verify model IDs, parameter names, accepted values, defaults, beta header strings, prices, and restrictions instead of relying on memory;
- cite the source beside each configuration claim;
- label each claim `verified current`, `workload recommendation`, or `requires verification`;
- if official pages conflict, report the conflict and prefer the most specific, most recently updated page;
- if no official source confirms a parameter, say so and do not invent syntax.

The cross-model best-practices page carries guidance measured on Opus 4.5 and 4.6. Treat each block as a measurement on that model and re-check before applying; several are amplifiers here.

## File, code, and dataset handling

### Prompts, skills, and CLAUDE.md

Read the whole thing before rewriting. Sort every instruction into three groups: hard product requirements, domain knowledge worth keeping, and amplifiers. Report the third group as deletions with the behavior each was compensating for. For `CLAUDE.md` files and project instructions, also check for a stop/continue rule, a destructive-action boundary, and a task-list-in-a-file rule on long runs (`references/claude-code-and-apps.md`).

### Harness code

Inspect and report on:

- model ID and surface;
- `effort` — set explicitly? varied mid-conversation, and how?
- `thinking` config — any `disabled` or `budget_tokens` (400 on Opus 5.5; on Opus 5, 400 above `high`);
- `thinking.display`, and whether the UI renders progress-update `thinking` blocks;
- whether response parsing selects content blocks by `type`;
- whether thinking blocks are passed back complete and unmodified, and whether the conversation stays append-only (no edits to `system`, `tools`, or earlier messages);
- `tool_choice` values (forced use is a 400 on Opus 5.5);
- computer-use tool type (`computer_20251124` is a 400 on Opus 5.5 via Claude API or Google Cloud);
- end-of-turn handling in unattended loops, and a cap on automatic continuations;
- `max_tokens` against effort and expected deliverable (up to 128k for Opus 5.5 agentic coding; at least 64k at `xhigh`/`max`);
- `task_budget`, time signals, subagent depth and concurrency caps;
- `speed` and fast-mode fallback;
- caching strategy and whether cache-participating values mutate per request;
- refusal handling by `stop_details.category`, `fallbacks` configuration, and model routing that drops thinking;
- non-default sampling parameters (400 on Opus 4.7 and later);
- separate verification stages left over from older models.

Return prompt changes and harness changes separately. Do not claim a prompt-only fix repairs a parsing, parameter, routing, or cap defect. Run `scripts/opus_api_check.py` over code that builds requests, and treat its output as warnings.

### Eval datasets

Infer the schema first and identify input, output, expected result, label, feedback, grader, effort, latency, token, and cost fields. Profile large CSV, JSON, or JSONL files with `scripts/profile_eval_dataset.py` before sampling failures. Derive narrow prompt changes from real failures only, and test for regressions on passing cases.

## Prompt construction rules

- State the goal, the reason behind it, hard constraints, the output contract, and the scope.
- Give the complete task specification up front, in one message. Both models do their best long-horizon work when handed the full spec and left to run.
- For any multi-step or agentic task, state what "done" looks like in observable terms and when to stop and ask. That finish line is how Opus 5.5 knows it has arrived.
- Name the stops you want and the ones you don't. For unattended agents, use the documented standing instruction; for human-in-the-loop work, ask for a plan and a recap instead. Keep destructive actions gated either way.
- State each instruction once. Delete duplicate, overlapping, and decorative rules.
- Do not instruct behavior the model already exhibits — including thinking. Damp it or leave it alone.
- Never ask for internal reasoning in the reply. If the product needs a rationale, ask for a bounded one ("in three sentences").
- Calibrate each length surface the product uses separately: conversation, narration, written files.
- Where you want breadth, ask for everything and filter downstream; where a filter is the real acceptance criterion, state it as such.
- Tell the model what to do rather than what to avoid, with one exception: for visual design, name the specific default patterns to exclude.
- Use XML tags to separate instructions, context, examples, and untrusted input; mark user-pasted text with ID-tagged `<pasted_content>` blocks.
- Put long documents at the top, above the query and instructions.
- Define behavior for missing, contradictory, stale, or malformed input. For research, ask the model to mark what it couldn't confirm and where it looked.
- For machine-readable output, use structured outputs or strict tool use with `tool_choice: auto` — not forced tool choice, not format pleading.
- For tools, define when each applies, prerequisites, recovery from empty or partial results, and post-action validation. Expose only the relevant subset. In multi-app automation, tell the model to explore relevant sources before acting.
- For delegation, name the scenarios that warrant subagents (large, independent units such as per-service audits), ask for an evidence check on each subagent report, and pair the rule with a deterministic cap.
- Distinguish safe reversible actions from destructive, external, or costly ones, and gate only the latter.
- Prompt explicitly for any style, template, or house format that office and document output must follow, and ask for the finished file rather than an outline.
- Put system-prompt additions in place from the first request of a session; on Opus 5.5 later edits invalidate earlier thinking blocks.

## Configuration

Recommend only settings that affect this workload:

- model choice (Opus 5.5 versus Opus 5 versus Fable 5.1 versus a smaller model);
- `effort`, set explicitly, and whether to vary it per message;
- `max_tokens`, sized for thinking plus reply;
- `thinking` (omit or adaptive on Opus 5.5) and `thinking.display` (`updates` when a human watches agentic turns);
- `tool_choice` and strict tools;
- `task_budget` for agentic loops with a cost ceiling, time signals for multiagent wall-clock;
- `speed` for latency-critical work, with its price stated;
- subagent depth, concurrency, and spend caps;
- caching and append-only history;
- refusal handling and fallback, including what the fallback does to thinking.

Workload defaults for this skill, labeled as recommendations rather than Anthropic rules. **Opus 5.5:** start at `medium` set explicitly; try `low` for subagents, simple tasks, latency-critical chat, and former thinking-disabled integrations; use `xhigh` or `max` only where a sweep shows a gain; `max_tokens` up to 128k for agentic coding. **Opus 5:** start at `high`, use `low` and `medium` liberally where evals hold, step up to `xhigh` for demanding coding and agentic work; keep thinking enabled. Load the matching configuration reference and verify volatile details online.

## Optimization modes

### Create

Turn the request into a copy-paste-ready prompt or `CLAUDE.md`. Use the minimal pattern unless tools, strict schemas, side effects, long-horizon autonomy, or high stakes justify hardening. Include a done criterion for any multi-step task, and length calibration whenever a human reads the output or a file lands on disk and evals show the default runs long.

### Audit or repair

1. Run the amplifier pass first and list every deletion with its reason.
2. Diagnose remaining failure modes through `references/behavior-fixes.md`.
3. Preserve genuine domain rules and product requirements.
4. Repair missing output contracts, done criteria, stop rules, length calibration, scope boundaries, tool rules, and delegation limits.
5. Return the complete revised prompt, not a patch alone.

Run `scripts/prompt_lint.py` on long prompts for deterministic checks. Warnings, not truth.

### Migrate to Opus 5.5

Existing Opus 5 prompts should perform well, so preserve the baseline and change one variable at a time. Handle the request-level breaks first: remove `thinking: disabled` and `budget_tokens`; replace forced `tool_choice` with `auto` plus strict tools; move `computer_20251124` to the toolset on Claude API or Google Cloud; make history append-only. Then the silent change — progress updates now arrive in `thinking` blocks, so set `display: "updates"` if a UI shows them. Then set effort explicitly and re-sweep (default dropped to `medium`, but each level thinks more), revisit `max_tokens`, add refusal handling for `bio` and `reasoning_extraction`, run the Opus 5.5 amplifier pass, and fix end-of-turn handling in unattended loops. Full checklist in `references/opus-5-5-configuration.md`. For migrations onto Opus 5 from 4.8, use `references/opus-5-configuration.md`.

### Diagnose an observed behavior

Start from the symptom, not the prompt. Name the layer that owns the fix (prompt, parameter, parsing, rendering, end-of-turn handling, routing, cap, user setting), give the smallest change, and give the test that proves it.

### Control cost or latency

Work the ladder in `references/cost-and-latency.md`: effort for depth, time signals for multiagent wall-clock, task budgets for breadth, `max_tokens` as the hard cap, delegation caps for fan-out, append-only caching for repeated prefixes, fast mode for speed at a premium. Do not try to disable thinking.

### Coach a Claude Code or Claude app user

Use `references/claude-code-and-apps.md`: whole task with a finish line, delete "think hard" lines, add to a running task instead of restarting, a `CLAUDE.md` stop/continue rule, subagent fan-out for big splittable work, a task list in a file, reading "blocked on me" first, a review pass before humans, attaching images instead of retyping, settled answers in long projects, and what to do when a message is flagged and the model switches.

### Eval-driven optimization

Establish a baseline, group failures by cause and layer, apply the smallest targeted change, rerun the same cases, inspect regressions, and compare quality against latency, tokens, and cost. Follow `references/evaluation-playbook.md`.

## Default output contract

Return these sections unless the user asks for another format:

### Final prompt

One copy-paste-ready prompt in a fenced block, with all essential instructions inside it. When system versus user placement or first-request placement matters, label it.

### Configuration

A compact table of only the relevant settings with a one-line rationale each. Label every volatile claim `verified current`, `workload recommendation`, or `requires verification`.

### Harness changes

Only when the diagnosis assigns a fix outside the prompt: content-block parsing, `thinking.display` and rendering, thinking-block replay and append-only history, end-of-turn continuation, `tool_choice`, `max_tokens`, task budgets, time signals, subagent caps, fast-mode fallback, caching, refusal handling and routing. Say what breaks if it is skipped.

### Diagnostic

Three to six concise points: amplifiers removed and why, main design choices, repaired risks, assumptions, limitations. For an audit, separate critical defects from optional improvements.

### Quick tests

Three to six representative tests: at least one normal case, one ambiguity or failure case, one length or format check, one long-run or early-stop case for agentic work, and one effort comparison when configuration is in play.

### Sources

Only when research was used. Cite official Anthropic pages beside the claims they support.

Keep the response compact without dropping a requested deliverable.

## Verification checklist

Before finalizing, confirm silently that:

- the prompt serves the user's actual objective, and the reason behind the request is stated;
- the target model is identified, and advice matches it;
- the full task specification is present, with an observable done criterion for multi-step work;
- stop and continue behavior matches whether a human is in the loop, and destructive actions stay gated;
- every amplifier was identified and removed, with its reason recorded;
- no verification, double-check, "think carefully", or reasoning-in-reply instruction remains;
- no instruction encourages delegation the model already performs; any fan-out names its scenario and has a cap;
- length is calibrated on each surface that needs it, and no one tried to shorten responses by lowering effort;
- review or analysis prompts either ask for everything and filter separately, or state their filter as the real acceptance criterion;
- on Opus 5.5: no `thinking: disabled`/`budget_tokens`, no forced `tool_choice`, effort set explicitly, history append-only, progress updates rendered if a UI needs them;
- on Opus 5: thinking enabled, or disabling it justified, capped at `high`, and paired with the artifact mitigation;
- parsing selects content blocks by `type`, and thinking blocks are replayed unmodified;
- `max_tokens` leaves room for thinking plus reply;
- any `task_budget` is sized against measured spend and above the 20,000-token minimum;
- refusals are handled by category, and fallback routing accounts for lost thinking;
- tool rules cover recovery and validation; strict formats are machine-checkable;
- tests target the most likely failure modes;
- the result is ready to copy, run, or evaluate.

## Scripts

Deterministic helpers. All three are standard-library Python 3 and produce warnings, not verdicts.

- `scripts/prompt_lint.py [file|-] [--format json]` — flags amplifiers (verification, double-check, "think carefully", delegation, narration, progress-summary scaffolding, do-not-think rules), reasoning-in-reply requests, self-limiting review language, vague design exclusions, effort-as-length confusion, missing done criteria and stop rules on agentic prompts, missing length calibration, and generic contract gaps.
- `scripts/opus_api_check.py <paths...> [--severity error|break|degrade|info] [--format json]` — scans harness code for documented 400s (thinking disabled or `budget_tokens`, forced `tool_choice` and `computer_20251124` on Opus 5.5, sampling parameters, undersized task budgets), silent breakage (`content[0].text`, stripped thinking blocks, text-only progress rendering, mutated cache values), and known-bad configuration (undersized `max_tokens`, omitted effort on Opus 5.5, uncapped delegation, missing fast-mode fallback, missing beta headers). Model-aware: it reads the model IDs in each file. Exits 1 on error- or break-class findings.
- `scripts/profile_eval_dataset.py <file>` — profiles CSV, JSON, or JSONL eval data: infers the schema, identifies input, output, expected, label, grader, effort, model, latency, token, and cost fields, and reports coverage and label distributions.

## References

- `references/behavior-fixes.md` — symptom-to-fix index with documented instruction blocks, Opus 5.5 first. Read this first for any audit or diagnosis.
- `references/opus-5-5-configuration.md` — Opus 5.5 IDs, effort, always-on thinking, `thinking.display`, block binding, tools, refusals, pricing, migration from Opus 5 and earlier.
- `references/opus-5-configuration.md` — the same for workloads staying on Opus 5.
- `references/claude-code-and-apps.md` — the claude.dev playbook for Opus 5.5 in Claude Code and Claude apps: `CLAUDE.md` rules, long runs, checking results, flagged messages, fast mode.
- `references/cost-and-latency.md` — the control ladder, and which knob to turn in which order.
- `references/prompt-patterns.md` — compact prompt skeletons, including Opus 5.5 unattended, chat, multi-app, fan-out, design, pasted-content, and `CLAUDE.md` patterns.
- `references/hardening-matrix.md` — add only risk-justified controls.
- `references/evaluation-playbook.md` — effort sweeps, amplifier-removal experiments, failure taxonomy.
- `references/official-sources.md` — where to verify current behavior.
