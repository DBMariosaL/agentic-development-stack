# Evaluation Playbook

Use evidence to improve prompts without bloating them. On Fable there is one extra obligation over ordinary prompt evaluation: run an effort sweep, because effort is the primary quality/latency/cost control and its levels do not transfer between models.

## 1. Establish the baseline

Record:

- model ID and surface;
- `effort`, `thinking.display`, `max_tokens`, `tool_choice`, and any beta headers;
- the prompt and every other instruction source in play (system prompt, skills, `CLAUDE.md`, per-turn injections, tool descriptions);
- representative inputs;
- expected behavior or rubric;
- actual outputs;
- task success and format compliance;
- factual and tool-use errors;
- latency, input/output tokens, cache reads, turn count, and cost.

Do not optimize against a single convenient example. Do not change the prompt and the effort level in the same experiment.

## 2. Run the effort sweep first

Before touching the prompt, sweep `low`, `medium`, `high`, `xhigh`, and `max` on the same cases. This often resolves what looks like a prompt problem, and it tells you which level the prompt should be tuned for.

What to look for:

| Observation | Reading |
| --- | --- |
| `medium` or `low` holds quality | Step down; on Fable 5.1, `medium` roughly matches Fable 5 at lower cost |
| `low` beats a smaller model on cost per task | Replace the smaller model rather than tuning it |
| Quality only appears at `xhigh` or `max` | Keep it, but check whether long deliverables are being drafted twice |
| Retrieval stops happening at `low` | Effort-specific behavior, not a prompt defect — raise effort for those turns |
| Long deliverables slow or truncated at `xhigh`/`max` | Run at `high`, or size `max_tokens` for thinking plus reply and add the single-limit note |

Consider per-message effort rather than one level for the whole session: raise it for the hard step, lower it for routine turns. On Fable 5.1 this does not invalidate the prompt cache.

## 3. Run the deletion experiment

Fable-specific and frequently the highest-value change. Take the instruction inventory from step 1, remove everything you cannot tie to a behavior it was written to correct, and rerun the same cases at the default effort. Report:

- cases that improved after deletion;
- cases that regressed, and which specific instruction was load-bearing;
- net token and latency change.

Skills and system prompts written for prior models are often too prescriptive and degrade output. Measuring this is cheaper than arguing about it.

## 4. Build a representative set

Include:

- normal high-frequency cases;
- hard but valid cases, including one harder than your current production ceiling;
- missing, ambiguous, malformed, and contradictory inputs;
- tool failure and empty retrieval cases;
- strict-format cases;
- long-run cases if the product has them — short evals hide autonomy, progress-claim, and stop-condition failures entirely;
- refusal-adjacent cases if the domain touches security or life sciences, to measure false-positive rate and exercise the fallback path;
- known historical regressions.

## 5. Classify failures

Assign each failure to a cause and a layer. The layer matters as much as the cause, because a prompt change cannot fix a harness defect.

| Cause | Usual layer |
| --- | --- |
| Misunderstood objective | Prompt |
| Missing context or constraint | Prompt |
| Incomplete deliverable, early stop | Prompt (autonomy contract) |
| Fabricated progress claim | Prompt (evidence rule) |
| Scope creep, extra tests | Prompt (scope rule) |
| Format or schema failure | Prompt, or move to structured outputs |
| Unsupported factual claim | Prompt (grounding, citations) |
| Unmarked quotation | Prompt (one worked example) |
| Stale answer, no retrieval | Effort level, or prompt nudge |
| Wrong tool or call order | Tool descriptions and trigger conditions |
| One tool call per turn | Turn-scoped nudge |
| Silent run | `thinking.display`, then prompt |
| Deliverable lost in a summary | Send-to-user tool |
| Truncated long output | `max_tokens`, effort |
| 400 on a later turn | Message assembly (history edits) |
| Cold cache every turn | Message assembly |
| `stop_reason: "refusal"` | Prompt phrasing, tool output, fallback config |
| Lead agent idle | Subagent return semantics |
| Timeout mid-run | Client configuration |

## 6. Make the smallest targeted change

For each failure cluster:

1. State the observed failure and the layer.
2. Identify the missing or conflicting instruction, or the misconfigured parameter.
3. Prefer a deletion over an addition when both would work.
4. Apply the smallest change that addresses it.
5. Avoid unrelated cleanup in the same experiment.
6. Keep an example only when it repairs a measured gap.

Where Anthropic documents an instruction block for the failure, start from that text rather than writing your own — it was measured. Then check whether the block was measured on the model you are running.

## 7. Rerun and compare

Compare baseline and candidate on the same cases:

- task success and severity-weighted failures;
- completeness and format compliance;
- evidence and citation quality;
- tool-call correctness and turn count;
- regressions on previously passing cases;
- tokens, cache reads, latency, cost, and human interventions.

Lower resource use is an improvement only if the output still clears the quality bar. Optimize successful task completion per unit of constrained resource, not tokens in isolation: fewer tokens is not a win if it produces retries or manual repair.

On Fable 5.1, cache reads cost a quarter of the Fable 5 rate, so recompute the cost side of any decision inherited from a Fable 5 evaluation — especially compaction timing.

## 8. Use graders carefully

Prefer narrow graders for distinct properties: required fields present; citations support claims; no unauthorized action; quotations marked; answer matches reference facts; length or tone constraint met; no unrequested file changes committed.

A grader mixing many subjective properties is hard to interpret and hard to optimize against. Combine automated graders with human review of a sample. For long-run agentic work, a fresh-context verifier agent is a better grader than self-critique.

## 9. Review before production

Manually inspect the optimized prompt and a sample of outputs. Aggregate improvement can hide specific inputs getting worse. Keep a regression set, and version the prompt, the instruction inventory, and the configuration together — on Fable, a prompt is only meaningful alongside its effort level and its harness behavior.

## Compact report format

```text
Baseline: [model, effort, prompt version, score]
Effort sweep: [low / medium / high / xhigh / max -> score, latency, cost]
Deletion pass: [instructions removed, net effect]
Main failure clusters: [top 3, each with its layer]
Change tested: [one targeted change]
Result: [quality delta, regressions, tokens, latency, cost]
Decision: keep / revise / reject
Next test: [single highest-value experiment]
```
