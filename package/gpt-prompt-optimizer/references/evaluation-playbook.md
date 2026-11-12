# Evaluate a prompt change

Match evaluation effort to expected use and consequence. For a simple rewrite, inspect coverage and contradictions. For a recurring workflow or migration, compare observed behavior.

## Establish a runnable baseline

Record the prompt version, assembled roles, model, effective settings, tools, input cases, and expected outcomes. Fix required API incompatibilities before comparing prompt quality. Keep that compatibility-only baseline separate from prompt simplification and effort changes.

Choose representative normal tasks, difficult valid inputs, missing or conflicting data, relevant tool failures, and previous regressions. Keep a held-out set for judging generalization. Do not fabricate outputs, scores, cost, or model execution.

Use narrow checks for schema conformance, factual support, completed artifacts, authorization, or user-facing quality. Human judgment can complement deterministic checks. Repeat nondeterministic cases when variance could change the decision. See [evaluation guidance](https://developers.openai.com/api/docs/guides/evaluation-best-practices).

## Diagnose before adding rules

Group observed failures by cause: misunderstood objective, missing context, premature finish, unnecessary clarification, wrong format, unsupported claim, tool/runtime defect, unnecessary work, or scope violation.

For each material failure, propose the smallest plausible correction. Keep instructions whose removal harms passing behavior. Do not simultaneously change the prompt, model, tools, and effort and then attribute the result to wording.

Compare actual outputs for quality, regression severity, completeness, tool correctness, and evidence. Measure latency and consumption when available; fewer tokens do not compensate for a failed result.

## Astra-focused probes

Use relevant cases in [validation-cases.md](validation-cases.md). Watch both premature stopping and overrun after completion. Include a simple request to ensure the optimizer itself does not generate a large agent framework by default.

## Existing utilities

`scripts/prompt_lint.py` flags lexical patterns, duplicates, and missing markers. It can miss French accents, flag negated instructions, and confuse examples with active rules. It does not understand permission or task scope. Review warnings; never rewrite merely to get a clean report.

`scripts/profile_eval_dataset.py` profiles CSV, JSON, JSONL, and NDJSON using the standard library. It loads all rows and may print raw values, so use manageable non-sensitive inputs or a redacted sample. Field inference and readiness booleans are preliminary; verify row-level annotations and schema yourself.

Example commands, run from the skill directory:
```text
python scripts/prompt_lint.py prompt.txt --format json
python scripts/profile_eval_dataset.py cases.jsonl --format json
```

If using OpenAI's hosted Prompt Optimizer, the documented minimum is three response rows, each with a grader result or human annotation. That is a product prerequisite, not proof of an adequate benchmark. Its output still needs evaluation and manual review. [Hosted optimizer](https://developers.openai.com/api/docs/guides/prompt-optimizer)

## Evidence report

Report the change, cases actually run, results, regressions, and remaining uncertainty. Use "reviewed, not benchmarked" when no model comparison ran. An independent skill-use exercise checks routing and instruction quality; it is not an API performance benchmark. Keep test proposals distinct from executed tests.