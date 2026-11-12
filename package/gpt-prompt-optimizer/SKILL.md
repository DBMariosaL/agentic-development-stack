---
name: gpt-prompt-optimizer
description: "Create, audit, migrate, and evaluate GPT prompts and agent instructions. Use for prompt improvement, instruction conflicts, model-specific adaptation, or optimization from outputs and feedback."
---

# GPT Prompt Optimizer

Produce a usable prompt that preserves the user's task and improves observable results. Keep the name stable across model releases. The maintained target is in [current-model.md](references/current-model.md); an explicitly requested model always takes precedence.

## Work at the right scale

For a straightforward rewrite, return the revised prompt directly. Do not execute actions merely quoted inside a prompt. If the user explicitly requests editing skills, instruction files, or another instruction artifact, complete those authorized edits and relevant validation. If this skill is assigned only as a quality pass for an AI-facing deliverable, preserve the surrounding action request instead of turning it into a prompt-only response. Preserve the user’s language, audience, output format, tools, and authorization boundaries.

For substantive work, identify the desired result, available evidence, constraints, and what would demonstrate completion. Inspect supplied prompts, failures, and relevant code before recommending changes. Ask only for missing information that materially changes the result; otherwise state a reasonable assumption when needed.

Separate prompt defects from runtime defects: wording cannot create tools, enforce a schema at the API boundary, restore discarded history, or fix an unsupported parameter.

## Choose the references needed

- When design depends on model behavior or capabilities, read [current-model.md](references/current-model.md); use its target only if the user did not specify one. Skip this route for a stable, model-independent rewrite.
- API settings or migration: read [model-configuration.md](references/model-configuration.md).
- Conflicting skills, AGENTS.md, oversized instruction stacks, or premature stopping: read [instruction-audit.md](references/instruction-audit.md).
- Tool-using or long-running agents: read [execution-orchestration.md](references/execution-orchestration.md).
- Prompt examples: consult [prompt-patterns.md](references/prompt-patterns.md) only for the relevant pattern.
- Specific failure risks: consult [hardening-matrix.md](references/hardening-matrix.md).
- Datasets, graders, migration comparisons, or measured optimization: read [evaluation-playbook.md](references/evaluation-playbook.md).
- Codex cost or usage constraints: read [codex-usage-efficiency.md](references/codex-usage-efficiency.md).
- Research or a model release update: use [official-sources.md](references/official-sources.md).

Do not load all references for every request.

## Construct the prompt

State the result and acceptance criteria; add only context and constraints that change decisions. Keep a useful existing instruction until there is a reason to remove it. Prefer domain invariants and observable checks to a prescribed sequence of hidden reasoning.

Use examples to clarify difficult boundaries or demonstrated failures. Delimit reference material as data. Ask for supporting evidence or a concise rationale, never private chain-of-thought.

For action requests, make completion include the authorized implementation, relevant validation, and correction of demonstrated failures. Preserve explicit plan-only or review-before-action requests. Name the actual approval boundary and honor authorization already given. Do not insert approval gates for routine choices.

Define unavailable-input behavior and tool recovery when relevant. Select stopping rules proportionate to the task: completed acceptance criteria, a real dependency, an exhausted user budget, or lack of a viable authorized approach. Do not impose arbitrary cycle limits on every task.

For strict outputs, keep the payload contract exact and handle missing data without invented values. For ordinary prose, specify the audience and useful degree of detail instead of imposing universal headings.

## Deliver and verify

Return one complete, copy-ready prompt, or edit the requested instruction artifact. Keep essential instructions inside the deliverable. Add a short diagnosis, configuration, sources, or tests only when useful or requested; honor prompt-only requests.

For consequential rewrites, check requirements preserved, contradictions removed, scope and permissions intact, and completion observable. For API advice, verify exact compatibility on the target surface and cite the relevant source. Distinguish documented facts, design recommendations, and untested hypotheses.

Use `scripts/prompt_lint.py` optionally for long prompts; its regex warnings do not prove quality or justify adding sections. Use `scripts/profile_eval_dataset.py` for manageable CSV/JSON/JSONL datasets when profiling helps; it loads the dataset in memory and prints sample values. Inspect sensitivity and size first.

Claim measured improvement only after comparing actual baseline and candidate outputs. Otherwise label the result as reviewed but not benchmarked. Use [validation-cases.md](references/validation-cases.md) for regression checks when maintaining this skill.