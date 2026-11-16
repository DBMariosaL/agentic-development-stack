---
name: claude-fable-prompt-optimizer
description: create, audit, migrate, and eval-tune prompts, mandates, and agent scaffolding for claude fable 5.2 and claude mythos 5.2 (default), and for workloads staying on fable 5.1 or fable 5. use when writing or auditing a prompt or delegation brief for a fable model, a fable lead that orchestrates subagents (delegation contract, subagent models and effort, reading reports, when to continue or stop), or a subagent's final report to a fable parent; or when the user asks about fable effort (high on the api, medium in claude code), think-less lines that no longer work, early stops, approvals and accumulated cautions, code ownership, silent progress updates and thinking.display, over-delegation and subagent cost, prefix-check 400s and append-only history, forced tool use, refusal categories and fallback, final-report readability, or migration from fable 5.1, fable 5, or opus 5.5. verify volatile fable facts against official anthropic documentation before presenting them as current.
---

# Claude Fable Prompt Optimizer

Build the smallest prompt that reliably completes the real task on Claude Fable 5.2 (the default target; Mythos 5.2 has the same capabilities for verified organizations), or on Fable 5.1 or Fable 5 for workloads pinned there. Fable 5.2 follows what it is told closely: instructions, style rules, ownership statements, and cautions left in memory. Most failures are now a leftover instruction obeyed past its purpose, a missing contract, or a harness that edits history. Subtract before you add.

For Claude Opus 5.5 or Opus 5, use `claude-opus-prompt-optimizer` instead.

## Which model the user is on

Default to Fable 5.2 when the user says "Fable" without a version. Facts below read on 2026-11-16; sources in `references/fable-configuration.md`.

| | Fable 5.2 | Fable 5.1 | Fable 5 | Opus 5.5, for contrast |
| --- | --- | --- | --- | --- |
| API ID | `claude-fable-5-2` | `claude-fable-5-1` | `claude-fable-5` | `claude-opus-5-5` |
| Price in / out per MTok | $8 / $40 | $10 / $50 | $10 / $50 | $4 / $20 |
| Default effort | `high` on the API; `medium` in Claude Code and apps | `high` | `high` | `medium` |
| "Answer directly without deliberating" | no effect at `medium`+ | usually followed | — | documented option at low effort |
| Forced `tool_choice` | 400 | 400 | accepted | 400 |
| Failed prefix check | always 400 | possible 400 | — | possible 400 |
| Who reads its thinking blocks | only Mythos 5.2 | — | — | — |
| `computer_20251124` | 400 outside Bedrock | accepted with beta | accepted with beta | — |
| Refusal categories | `cyber`, `bio`, `frontier_llm`, `reasoning_extraction`, `general_harms` | same | — | — |
| Main documented fixes | finishing work, approvals, ownership, silence, delegation cost, cautions, reports | batching, density, formatting, quoting, scope, search, rewrites | progress claims, boundaries, memory, send-to-user | unattended stops, time signals, settled answers, pasted content |

Anthropic routes most work to Opus 5.5 first and to Fable 5.2 for demanding reasoning and long-horizon agentic work, or when Opus 5.5 at higher effort still falls short. Claude Code never defaults to Fable; `/model fable` selects 5.2.

## Remove before you add

Each row is a documented Fable 5.2 behavior that a carried-over instruction or harness habit makes worse ([P] = Prompting Fable 5.2).

| Carried-over instruction or habit | Result on Fable 5.2 | Do instead |
| --- | --- | --- |
| "Answer directly", "don't deliberate" | Still thinks at `medium`+ [P] | Lower effort for those turns |
| "Delegate", "use subagents where possible" | Delegates readily; subagents dominate cost [P] | Remove; cost-focused subagent tool description if needed |
| A visible token budget | Its size drives spend [P] | Test without it |
| Hard style limits ("20 words or fewer") | Followed closely; choppy prose [P] | Remove; use the "Communicating clearly" block |
| Absolute "never" rules, stale cautions in memory | Read as absolute; unneeded approvals [P] | Scoped rule with a reason; list steps needing no approval |
| Broad approval categories | About half of routine requests held back [P] | Name the specific actions |
| Opus 5.5 "treat that answer as done" lines | Far less self-correction [P] | Leave out where mistakes matter |
| Reasoning in the reply, scratchpad sections, `reasoning` fields | `reasoning_extraction` refusal, no fallback | Read `display: "summarized"` thinking |
| Forced `tool_choice`, prefill, `budget_tokens`, `thinking: disabled`, sampling parameters | 400 | `auto` plus a prompt line or strict tools; effort; nothing |
| Editing `system`, `tools`, or earlier turns mid-conversation | 400 on every failing request | Append-only; system messages; tool additions |

Many reported Fable problems are harness defects: check `thinking.display`, message assembly, `max_tokens`, effort, subagent models and caps, and the tool inventory before adding prompt text, and say which layer owns each fix.

## The two jobs this skill serves most

**1. A prompt or mandate for a Fable model, especially a lead that decides and delegates.** Fable earns its price on decomposition, judgment, and acceptance. Anthropic documents that it delegates as much as the harness invites, reviews its own work with subagents at `xhigh`/`max`, and that as orchestrator in Opus 5.5's place it cost 19% more for about the same score on one benchmark. The mandate needs a delegation contract (what is worth delegating and what a subagent costs; model and effort per role; brief contents, because the subagent sees only its brief; ownership; non-blocking returns; caps set in the harness; steps that need no approval), return semantics (a missing or partial report is not done; evidence beats the summary; open the diff), a continue-or-stop rule, and the acceptance check the lead runs itself. Use `references/orchestration-and-handoffs.md`.

**2. The final report a subagent hands to a Fable parent.** Only the final message reaches the parent. Write status first (`done`, `partial`, `blocked`) with any decision needed, then what changed with checkable pointers, then deviations and what was not done, then unverified claims, then the model and checks used. No narrative of the work, no reasoning transcript, no invented labels. The contract and a brief line to request it are in `references/orchestration-and-handoffs.md`.

## Workflow

1. Identify the objective, target model and surface (Claude API, Bedrock, Google Cloud, Foundry, Claude Code, Agent SDK, Managed Agents), who reads the output (human, Fable parent, other model), inputs, tools, side effects, run length, whether a human watches, and failure modes.
2. Classify: create; audit or repair; migrate (Fable 5.1, Fable 5, or Opus 5.5 to Fable 5.2); orchestration mandate; subagent report; diagnose an observed behavior; eval-driven optimization.
3. Inspect every supplied material before drafting, including memory files, notes, agent definitions, and subagent tool descriptions.
4. Map each symptom with `references/behavior-fixes.md` (Fable 5.2 index first).
5. Verify volatile facts against `references/official-sources.md`.
6. Run the deletion pass; then choose the smallest pattern from `references/prompt-patterns.md` and add controls only for identified risks (`references/hardening-matrix.md`).
7. For long runs apply `references/agentic-scaffolding.md`; for delegation and reports, `references/orchestration-and-handoffs.md`.
8. Recommend configuration with `references/fable-configuration.md`.
9. Validate coverage, contradictions, tool rules, approval boundaries, output format, done criteria, and scope ceiling.
10. Provide compact tests and an effort sweep; with eval data, follow `references/evaluation-playbook.md`.

## Intake rules

Accept any mix of requests, prompts, `CLAUDE.md` files, skills, agent definitions, memory directories, tool or subagent schemas, harness code, eval data, and requirements. Do not ask for optional context when explicit assumptions suffice; ask first only when the answer changes architecture, scope, security, side effects, acceptance criteria, or an expensive path. Whether a human is in the loop, and who owns the code, often qualify.

## Source and freshness rules

Follow `references/official-sources.md`: official pages only, in its order; verify IDs, parameters, values, defaults, beta strings, and prices rather than recall; cite each claim and label it `verified current`, `workload recommendation`, or `requires verification`; state the surface (API and Claude Code defaults differ); report conflicts; never invent syntax. A Fable 5.1 or Fable 5 block is a measurement on that model. Third-party reports are labeled experiment ideas. Do not browse for stable prompt-writing work.

## File, code, and dataset handling

### Prompts, skills, memory

Read the whole thing first. Sort instructions into hard product requirements, domain knowledge, and carried-over scaffolding. Report the third group as deletions with what each was compensating for. Treat memory files and notes as instruction sources: on Fable 5.2 they are followed closely.

### Harness code

Report on: model and surface; `effort` (explicit, defaulted, varied); `thinking` and `display`; `max_tokens`; `tool_choice`, `strict`, CMEK; exact replay of assistant turns; anything that rewrites `system`, `tools`, or earlier messages (dates in the system prompt, unpinned MCP tool lists, removed reminders); `prefix_mismatch_behavior`; computer-use tool and advisor model; subagent models, effort, caps, and blocking; refusal handling, including on subagent calls; timeouts.

Return prompt changes and harness changes separately. Run `scripts/fable_api_check.py` over request-building code; treat its output as warnings.

### Eval datasets

Infer the schema and profile large files with `scripts/profile_eval_dataset.py` before sampling failures; derive narrow changes from real failures only.

## Prompt construction rules

- State the goal, the reason behind it, hard constraints, the output contract, and done criteria.
- State each instruction once, with its scope; give every prohibition its reason and exceptions.
- Name the routine steps that need no approval and the few that do.
- Decide the ownership sentence deliberately: include it when restructuring is wanted, omit it for narrow changes.
- For a reader who did not see the work, use the "Communicating clearly" block; do not add sentence-length limits.
- Never ask the model to reproduce its reasoning as response text or in a JSON field.
- Use XML tags for instructions, context, examples, and untrusted input; long documents at the top.
- For machine-readable output, prefer strict tools or JSON outputs; validate in code where CMEK rules them out.
- For tools, define when each applies, recovery from empty or partial results, and validation; expose only the relevant subset; name a tool and its condition to make the model call it.
- For long runs, define both the completion condition and the scope ceiling.
- Put system-prompt text in place from the first request; append later changes as system messages.

## Configuration

Recommend only settings that affect the workload: model (Fable 5.2 versus Opus 5.5 versus Fable 5.1); `effort`, set explicitly; per-message effort; `thinking.display`; `max_tokens` sized for thinking plus reply; output enforcement; append-only history and `prefix_mismatch_behavior`; subagent model, effort, and caps; caching; refusal handling and fallback.

Workload defaults, as recommendations: start Fable 5.2 at `high` explicitly, then test `medium` and `xhigh`, and `low` for subagents; keep an orchestrating lead at `high` with cheaper subagents at lower effort, and compare against Opus 5.5 leading; do not treat `max` as better. Details in `references/fable-configuration.md`.

## Optimization modes

### Create

Start from the minimal pattern; harden only for tools, strict schemas, side effects, autonomy, delegation, or high stakes.

### Audit or repair

1. Run the deletion pass, including memory and agent files, listing each deletion with its reason.
2. Diagnose remaining failures through `references/behavior-fixes.md`.
3. Preserve genuine domain rules and product requirements.
4. Repair missing contracts, approval boundaries, completion rules, delegation contracts, and done criteria.
5. Return the complete revised prompt.

Run `scripts/prompt_lint.py` on long prompts. Warnings, not truth.

### Migrate

Preserve the baseline; change one variable at a time. Required changes first (prefix-check test, computer-use toolset, advisor model, explicit effort when coming from Opus 5.5, ZDR and CMEK checks), then deletions (think-less lines, delegate lines, token budgets, style limits, stale cautions), then optional prompt additions measured one at a time. Rerun the sweep.

### Diagnose an observed behavior

Start from the symptom. Name the layer that owns the fix, give the smallest change, and the test that proves it.

### Eval-driven optimization

Follow `references/evaluation-playbook.md`: baseline, effort sweep, deletion experiment, delegation comparison, one targeted change at a time.

## Default output contract

Return these sections unless the user asks otherwise:

- **Final prompt**: one copy-paste-ready block with all essential instructions; label system versus user placement when it matters.
- **Configuration**: only relevant settings, one-line rationale each, every volatile claim labeled.
- **Harness changes**: only when a fix lies outside the prompt; say what breaks if skipped.
- **Diagnostic**: three to six points: deletions and why, design choices, repaired risks, assumptions, limits.
- **Quick tests**: three to six: a normal case, an ambiguity or failure case, a format check, a long-run or early-stop case for agentic work, and an effort comparison when configuration is in play.
- **Sources**: only when research was used, beside the claims they support.

When the deliverable is a subagent's report to a Fable parent, the report contract replaces these sections.

## Verification checklist

Before finalizing, confirm silently that:

- model, surface, and reader are identified, and advice matches them;
- the reason behind the request is stated, and every deliverable is represented;
- the deletion pass covered memory files and agent definitions;
- no instruction asks for reasoning in the reply;
- approvals are specific, and the ownership choice is deliberate;
- delegation covers cost, models, briefs, ownership, caps, returns, and the lead's own check;
- a report for a Fable parent leads with status and evidence;
- effort is explicit, `max_tokens` fits thinking plus reply, and history is append-only;
- refusals are handled by category, including on subagent calls;
- each fact carries its source; tests target the likeliest failures.

## Scripts

Standard-library Python 3 helpers that produce warnings, not verdicts.

- `scripts/prompt_lint.py [file|-] [--format json]`: carried-over lines Fable 5.2 obeys too well (think-less, delegate, visible token budget, style limits, unscoped "never", "treat as done", broad approvals, ownership plus scope limit), reasoning-in-reply requests, API-parameter references, contract gaps, duplication.
- `scripts/fable_api_check.py <paths...> [--severity error|break|degrade|info] [--format json]`: documented 400s (forced tool use, rejected thinking types, sampling parameters, prefill, `computer_20251124`, a pre-5.2 advisor), prefix-check breakage, bad configuration (`display: "omitted"`, small `max_tokens`, unset effort, blocking or uncapped subagents), missing beta headers. Exits 1 on error or break findings.
- `scripts/profile_eval_dataset.py <file>`: profiles CSV, JSON, or JSONL eval data, including effort, model, stop-reason, and subagent fields.

## References

- `references/behavior-fixes.md`: symptom-to-fix index with documented blocks, Fable 5.2 first. Read first for any audit or diagnosis.
- `references/orchestration-and-handoffs.md`: writing for a Fable lead, subagent mechanics in Claude Code and the Agent SDK, and the report contract for a Fable parent.
- `references/fable-configuration.md`: IDs, effort, thinking, prefix check, tools, refusals, pricing, migration.
- `references/prompt-patterns.md`: compact skeletons, including subagent tool description and brief.
- `references/agentic-scaffolding.md`: long-horizon runs, memory, verification, computer use, vision.
- `references/hardening-matrix.md`: risk-justified controls and anti-patterns.
- `references/evaluation-playbook.md`: effort sweeps, deletion experiments, delegation comparison.
- `references/official-sources.md`: where to verify current behavior.
