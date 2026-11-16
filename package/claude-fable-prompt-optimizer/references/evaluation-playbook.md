# Evaluation Playbook

Use evidence to improve prompts without bloating them. Fable adds three obligations to ordinary prompt evaluation: an effort sweep, because effort is the main quality, latency, and cost control and its levels do not transfer between models [P]; a deletion experiment, because carried-over instructions are followed closely; and, for orchestrators, a delegation-cost comparison.

## 1. Establish the baseline

Record: model ID and surface; `effort` (explicit or default, which is `high` on the API and `medium` in Claude Code); `thinking.display`; `max_tokens`; beta headers; every instruction source (system prompt, skills, `CLAUDE.md`, memory and notes, per-turn injections, tool and subagent descriptions); representative inputs; rubric; outputs; task success and format compliance; latency, tokens, cache reads, turns, cost; for orchestrators, subagent count, subagent models, and their share of cost.

Do not change the prompt and the effort level in the same experiment.

## 2. Run the effort sweep first

Anthropic's starting order for Fable 5.2: set `high` explicitly, then run `medium` and `xhigh` [P]. Add `low` for subagents and high-volume work.

| Observation | Reading |
| --- | --- |
| `medium` holds quality | Step down; the `medium`-to-`high` step raised scores on most of Anthropic's tracked evals, so confirm on yours [P] |
| `low` holds on routine turns | Use it there, or per message; at `low` on coding, Fable 5.2 scored close to Fable 5.1 at higher effort [P] |
| Early stops appear at `low`/`medium` | Add the "Finishing work" block before concluding the level fails |
| Gain only at `xhigh` | Keep it for that phase; expect many more tokens [P] |
| Easy turns slow at `high` | Lower effort for those turns; prompt lines will not stop thinking [P] |

Per-message effort lets one session mix levels without losing the cache [P].

## 3. Run the deletion experiment

Remove every instruction you cannot tie to a behavior it corrects, then rerun at the default. Report improvements, regressions with the instruction that was load-bearing, and the net token and latency change. On Fable 5.2, include memory files and notes in the inventory, and test removing any visible token budget: Anthropic found removing a large one lowered cost at equal performance [P].

## 4. Measure delegation, if the lead orchestrates

Compare on the same cases: the lead alone; the lead with cheaper subagents; Opus 5.5 leading the same subagents. Anthropic's defect-search benchmark found Fable 5.2 leading Sonnet 5.5 subagents cost 19% more than Opus 5.5 leading them, at about the same score; and for single dependent chains the lead alone at lower effort did better on earlier models [OPT]. Report cost per accepted result, not per run.

## 5. Build a representative set

Normal cases; hard cases above your ceiling; bad or ambiguous inputs; tool failures; strict formats; long runs (short evals hide early stops, approvals, silence, and fabricated progress); refusal-adjacent cases in security, life sciences, or machine learning; known regressions.

## 6. Classify failures by cause and layer

| Cause | Usual layer |
| --- | --- |
| Misunderstood objective, missing context | Prompt |
| Early stop, offer to continue | Prompt ("Finishing work"), or effort |
| Unneeded approval, held routine work | Prompt and memory (deletion) |
| Duplicated code, or unwanted restructuring | Ownership sentence |
| Fabricated progress claim | Prompt (evidence rule) |
| Format or schema failure | Strict tools or JSON outputs |
| Unsupported claim | Prompt (grounding, citations) |
| Wrong tool or call order | Tool descriptions and trigger conditions |
| Silent run | `thinking.display`, then reminder, then prompt |
| Truncated output, text missing after thinking | `max_tokens`, effort |
| 400 on a later turn | Message assembly (prefix check) |
| Cold cache every turn | Message assembly, top-level effort changes |
| `stop_reason: "refusal"` | Prompt deletion, fallback config, program access |
| Too many subagents | Delegate lines, tool description |
| Subagent work lost or misread | Brief contents, report contract, missing-report handling |
| Timeout mid-run | Client configuration |

## 7. Make the smallest targeted change

State the failure and its layer; prefer a deletion; apply one change; keep unrelated cleanup out. Where Anthropic documents a block, start from it, and check which model it was measured on.

## 8. Rerun and compare

Compare task success, completeness, evidence quality, tool correctness, regressions, tokens, cache reads, latency, cost, and interventions. Lower resource use counts only if quality holds. Two documented costs to expect: the "Finishing work" block raised output tokens about 30%, and the ownership sentence 70 to 80% [P].

## 9. Graders and review

Prefer narrow graders (required fields, citations support claims, no unauthorized action, report leads with status) plus human review of a sample. For long runs, a fresh-context verifier beats self-critique [F5]. Version prompt, instruction inventory, and configuration together.

## Compact report format

```text
Baseline: [model, surface, effort, prompt version, score]
Effort sweep: [high / medium / xhigh (/ low) -> score, latency, cost]
Deletion pass: [instructions removed, net effect]
Delegation: [alone vs with subagents vs Opus 5.5 lead -> cost per accepted result]
Main failure clusters: [top 3, each with its layer]
Change tested: [one targeted change]
Result: [quality delta, regressions, tokens, latency, cost]
Decision: keep / revise / reject
Next test: [single highest-value experiment]
```

Source keys as in `references/behavior-fixes.md`; [OPT] is `https://platform.claude.com/docs/en/about-claude/models/optimizing-for-cost-and-intelligence`.
