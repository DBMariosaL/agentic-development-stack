---
name: claude-fable-prompt-optimizer
description: create, audit, migrate, and eval-tune production prompts and agent scaffolding for claude fable 5.1, claude mythos 5.1, claude fable 5, and claude mythos 5. use when the user provides a rough request, an existing system or user prompt, harness code, tool definitions, subagent wiring, eval datasets, model outputs, or asks about fable effort levels, adaptive thinking, thinking-block binding, turn-scoped system messages, progress updates, long-horizon autonomy, memory systems, subagent orchestration, refusal fallback, whole-file rewrites, writing density, or migration from claude opus or claude fable 5. verify volatile fable facts against official anthropic documentation before presenting them as current.
---

# Claude Fable Prompt Optimizer

Build the smallest prompt that reliably completes the real task on Claude Fable. Fable models are strong enough that most prompt failures are either a missing contract or a leftover instruction written for a weaker model. Subtract before you add.

## The Fable inversion

Prompt engineering habits from earlier model generations actively hurt on Fable. Check for these before writing anything new:

| Legacy habit | What it does on Fable | Do instead |
| --- | --- | --- |
| Long anti-formatting block ("no bullets, no bold, no headers") | Fable 5.1 already under-formats; suppresses structure the content needs | Say when formatting *is* appropriate |
| "Hold all findings for the final response" | Fable 5.1 already writes few updates; the agent goes silent for minutes | Ask for an opening line, periodic updates, a standalone recap |
| "Show your reasoning", "explain your thinking", reflection steps | Can trigger the `reasoning_extraction` refusal category and elevated fallbacks | Read structured `thinking` blocks; use a send-to-user tool |
| "CRITICAL: you MUST use this tool when..." | Overtriggering | "Use this tool when..." |
| Enumerating every unwanted behavior by name | Prompt bloat, no added compliance | One short instruction that defines the anti-pattern |
| `tool_choice` set to `any` or a named tool | 400 error on Fable 5.1 and Mythos 5.1 | `auto` plus an explicit prompt line, strict tool use, or structured outputs |
| `thinking.budget_tokens` to cap cost | 400 error | Lower `effort`; use `max_tokens` as the hard ceiling |
| Assistant prefill to force a format | 400 error | Structured outputs, XML output tags, or a direct no-preamble instruction |
| Injecting a per-turn reminder and deleting it next request | Invalidates thinking blocks, restarts the prompt cache | Turn-scoped system message (`clear_at: "next_user_message"`) |
| Prescriptive step-by-step skills tuned for older models | Measurably degrades Fable output | Delete, retest at default, re-add only what a failure demands |

Corollary: a large share of reported Fable problems are harness defects, not prompt defects. Before adding prompt text, check whether the fix belongs in `thinking.display`, message assembly, subagent return semantics, `max_tokens`, or the tool inventory. Say which layer owns each fix.

## Workflow

1. Identify the real objective, target user, surface (Claude API, Bedrock, Vertex, Foundry, Claude Code, Agent SDK), available inputs, expected output, tools, side effects, run length, and failure modes.
2. Classify the request:
   - create a prompt or agent scaffold from a rough request;
   - audit or repair an existing prompt, skill, or system prompt;
   - migrate from Claude Opus 5, Claude Opus 4.8, or Claude Fable 5 to Claude Fable 5.1;
   - diagnose an observed behavior (silent agent, early stop, unrequested work, dense prose, whole-file rewrites, refusals, one tool call per turn);
   - optimize from examples, outputs, graders, or eval datasets.
3. Inspect every supplied material before drafting: prompt assembly code, message roles, `system` and `tools` handling across turns, tool schemas, effort and thinking settings, sample outputs, eval data.
4. Map each observed symptom to its fix with `references/behavior-fixes.md`. That table is the fastest route from "what the user sees" to "what to change".
5. Verify volatile facts (model IDs, effort values, beta headers, parameter names, prices, refusal behavior) against official Anthropic sources. Follow `references/official-sources.md`.
6. Remove before you add. List the legacy instructions to delete, then choose the smallest pattern from `references/prompt-patterns.md` and add controls only for identified risks (`references/hardening-matrix.md`).
7. For agentic or long-horizon work, apply `references/agentic-scaffolding.md`: autonomy contract, progress surface, memory, subagent semantics, compaction, verification interval, stop condition.
8. Draft the prompt and recommend configuration with `references/fable-configuration.md`.
9. Validate coverage, contradictions, tool rules, permission boundaries, output format, done criteria, and scope ceiling.
10. Provide compact tests targeting the most likely failures, plus an effort sweep. When eval data exists, follow `references/evaluation-playbook.md`.

## Intake rules

Accept any combination of: a rough natural-language request; an existing system, developer, or user prompt; a Claude Code `CLAUDE.md`, skill, or agent definition; tool or MCP schemas; harness code that builds `messages`; policy or domain files; CSV, JSON, JSONL, or logs with test cases, outputs, labels, or grader results; latency, cost, quality, safety, or formatting requirements.

Do not ask for optional context when a useful result can be produced under explicit assumptions or placeholders. Ask first only when the missing answer changes architecture, scope, security, side effects, acceptance criteria, or an expensive implementation path.

## Source and freshness rules

When current Fable behavior matters:

- search only official Anthropic properties listed in `references/official-sources.md`;
- prefer the model-specific prompting page over the cross-model best-practices page, and both over release posts;
- verify model IDs, parameter names, accepted values, defaults, beta header strings, prices, and enforcement dates instead of relying on memory;
- cite the source beside each configuration claim;
- label each claim `verified current`, `workload recommendation`, or `requires verification`;
- if official pages conflict, report the conflict and prefer the most specific, most recently updated page;
- if no official source confirms a parameter, say so and do not invent syntax.

Anthropic's published instruction blocks were measured on specific models. Treat a block from the Fable 5 page as a Fable 5 measurement and re-check it on Fable 5.1. Treat third-party field reports as experiment ideas, not documentation.

Do not browse for stable prompt-writing work that does not depend on current model behavior.

## File, code, and dataset handling

### Prompts and skills

Read the whole thing before rewriting. Separate three groups: hard product requirements, domain knowledge worth keeping, and legacy scaffolding written for weaker models. Report the third group as deletions with a reason each.

### Harness code

Inspect and report on:

- model ID and surface;
- the `effort` setting, and whether it is ever changed mid-conversation;
- `thinking` config, especially `display` and any `budget_tokens` or `disabled` leftovers;
- `tool_choice`, `strict`, and structured-output usage;
- whether assistant turns are appended back byte-for-byte with thinking blocks intact;
- whether anything rewrites `system`, `tools`, or earlier messages between requests;
- how per-turn reminders are delivered;
- `max_tokens` relative to expected deliverable length;
- subagent launch and return semantics (blocking or asynchronous);
- compaction strategy, client-side or server-side;
- refusal handling and fallback configuration;
- timeouts, streaming, retries, and progress rendering.

Return prompt changes and harness changes separately. Do not claim a prompt-only fix repairs a message-assembly or timeout defect. Run `scripts/fable_api_check.py` over code that builds requests, and treat its output as warnings.

### Eval datasets

Infer the schema first and identify input, output, expected result, label, feedback, grader, effort, latency, token, and cost fields. Profile large CSV, JSON, or JSONL files with `scripts/profile_eval_dataset.py` before sampling failures. Derive narrow prompt changes from real failures only, and test for regressions on passing cases.

## Prompt construction rules

- State the goal, the reason behind it, hard constraints, the output contract, and done criteria. Fable performs better when it knows what the output enables.
- State each instruction once. Delete duplicate, overlapping, and decorative rules.
- Prefer one instruction that defines the anti-pattern over an enumeration of unwanted behaviors.
- Tell the model what to do rather than what to avoid, and use XML tags to separate instructions, context, examples, and untrusted input.
- Put long documents at the top, above the query, instructions, and examples.
- Never ask the model to echo, transcribe, or explain its internal reasoning as response text.
- Keep examples only when they encode a product requirement or repair a measured failure. Three to five, wrapped in `<example>` tags. For quotation discipline, one complete example with a `<rationale>` is the documented fix.
- Define behavior for missing, contradictory, stale, or malformed input.
- For machine-readable output, give an exact schema and prohibit extra text; prefer structured outputs or strict tool use over format pleading.
- For tools, define when each applies, prerequisites, batching of independent calls, retries, recovery from empty or partial results, synthesis, and post-action validation. Expose only the relevant subset.
- For long-running work, define both the completion condition and the scope ceiling. "Keep going until it works" is not a contract.
- Distinguish safe reversible actions from destructive, external, or costly ones, and gate only the latter.
- Place per-turn nudges as turn-scoped system messages rather than editing history.

## Fable configuration

Recommend only settings that affect this workload:

- model choice (Fable 5.1 versus Opus 5 versus a smaller model);
- `effort` baseline and whether to vary it mid-conversation;
- `thinking.display` and how updates reach the user;
- `max_tokens` sized for thinking plus reply;
- `tool_choice`, strict tool use, or structured outputs;
- prompt caching and compaction strategy;
- refusal handling and fallback targets.

Workload defaults for this skill, labeled as recommendations rather than Anthropic rules: start at `high` (the documented default), sweep `low`, `medium`, `xhigh`, and `max` against real evals, and prefer `high` for long deliverables. Do not treat `max` as automatically better. Load `references/fable-configuration.md` for the decision rules and verify volatile details online.

## Optimization modes

### Create

Turn the request into a copy-paste-ready prompt. Use the minimal pattern unless tools, strict schemas, side effects, long-horizon autonomy, or high stakes justify hardening.

### Audit or repair

1. Diagnose the highest-impact failure modes, mapping each symptom through `references/behavior-fixes.md`.
2. List legacy instructions to delete and say what each was compensating for.
3. Preserve genuine domain rules and product requirements.
4. Repair missing output contracts, tool rules, recovery behavior, autonomy boundaries, and done criteria.
5. Return the complete revised prompt, not a patch alone.

Run `scripts/prompt_lint.py` on long prompts for deterministic checks on Fable-hostile patterns, duplication, weak contracts, and unbounded loops. Warnings, not truth.

### Migrate

Preserve the baseline first, then change one variable at a time with representative tests. Separate required API changes (forced tool use, prefill, `budget_tokens`, sampling parameters, append-only history) from optional prompt simplifications and workload preferences. Effort level names do not map across models, so re-run the sweep even if you ran one on the previous model.

### Diagnose an observed behavior

Start from the symptom, not the prompt. Name the layer that owns the fix (prompt, message assembly, API parameter, tool inventory, UI), give the smallest change, and give the test that proves it.

### Eval-driven optimization

Establish a baseline, group failures by cause, apply the smallest targeted change, rerun the same cases, inspect regressions, and compare quality against latency, tokens, and cost. Follow `references/evaluation-playbook.md`.

## Default output contract

Return these sections unless the user asks for another format:

### Final prompt

One copy-paste-ready prompt in a fenced block, with all essential instructions inside it. When system versus user placement matters, label which part goes where.

### Fable configuration

A compact table of only the relevant settings with a one-line rationale each. Label every volatile claim `verified current`, `workload recommendation`, or `requires verification`.

### Harness changes

Only when the diagnosis assigns a fix outside the prompt: message assembly, `thinking.display`, `max_tokens`, tool definitions, subagent return semantics, compaction, timeouts, refusal fallback. Say what breaks if it is skipped.

### Diagnostic

Three to six concise points: main design choices, instructions removed and why, repaired risks, assumptions, limitations. For an audit, separate critical defects from optional improvements.

### Quick tests

Three to six representative tests: at least one normal case, one ambiguity or failure case, one format or completeness check, and one effort comparison when configuration is in play.

### Sources

Only when research was used. Cite official Anthropic pages beside the claims they support.

Keep the response compact without dropping a requested deliverable.

## Verification checklist

Before finalizing, confirm silently that:

- the prompt serves the user's actual objective, and the reason behind the request is stated;
- every requested input and deliverable is represented;
- legacy instructions written for weaker models were identified and removed;
- no instruction asks the model to reproduce its internal reasoning;
- no anti-formatting or anti-narration block is left in place unexamined;
- instructions do not materially contradict each other;
- volatile Fable claims were verified, and facts are separated from preferences;
- the fix for each symptom is assigned to the correct layer;
- API-level blockers are flagged: forced tool use, prefill, `budget_tokens`, non-default sampling, history edits;
- tool rules cover batching, recovery, stopping, and validation;
- long-running prompts define autonomy, evidence-grounded progress claims, a verification interval, a scope ceiling, and a stop condition;
- subagent prompts define when to delegate and whether the lead keeps working;
- external or irreversible actions have approval boundaries;
- strict formats are machine-checkable;
- `max_tokens` leaves room for thinking plus the reply;
- tests target the most likely failure modes;
- the result is ready to copy, run, or evaluate.

## Scripts

Deterministic helpers. All three are standard-library Python 3 and produce warnings, not verdicts.

- `scripts/prompt_lint.py [file|-] [--format json]` — flags Fable-hostile patterns (anti-formatting rules, anti-narration lines, reasoning-display requests, emphatic tool language, prefill and budget_tokens references, context countdowns, inert directives) plus contract gaps and duplication. Fable-class findings usually mean delete text, not add it.
- `scripts/fable_api_check.py <paths...> [--severity error|break|degrade|info] [--format json]` — scans harness code for documented 400s (forced tool use, `budget_tokens`, non-default sampling, prefill), silent breakage (history mutation, `system`/`tools` rebuilds, stripped thinking blocks, missing beta headers), and known-bad behavior (`display: "omitted"` in an agent loop, undersized `max_tokens`, blocking subagents, short timeouts). Exits 1 when anything error- or break-class is found.
- `scripts/profile_eval_dataset.py <file>` — profiles CSV, JSON, or JSONL eval data: infers the schema, identifies input, output, expected, label, grader, effort, model, latency, token, and cost fields, and reports coverage and label distributions before you sample failures.

## References

- `references/behavior-fixes.md` — symptom-to-fix table with the documented instruction blocks. Read this first for any audit or diagnosis.
- `references/fable-configuration.md` — model IDs, effort, thinking, betas, pricing, breaking changes, refusal handling.
- `references/prompt-patterns.md` — compact prompt skeletons for Fable.
- `references/agentic-scaffolding.md` — long-horizon autonomy, memory, subagents, compaction, verification loops, vision tooling.
- `references/hardening-matrix.md` — add only risk-justified controls.
- `references/evaluation-playbook.md` — effort sweeps, failure taxonomy, regression discipline.
- `references/official-sources.md` — where to verify current behavior.
