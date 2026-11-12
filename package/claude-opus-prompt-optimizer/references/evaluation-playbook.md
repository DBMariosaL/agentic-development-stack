# Evaluation Playbook

Use evidence to improve prompts without bloating them. On Opus 5.5 and Opus 5 there are two obligations beyond ordinary prompt evaluation: run an effort sweep, and run an amplifier-removal experiment. Both usually pay for themselves before any prompt rewriting starts.

## 1. Establish the baseline

Record:

- model ID and surface;
- `effort`, `thinking` config, `max_tokens`, `task_budget`, `speed`, and any beta headers;
- the prompt and every other instruction source in play (system prompt, skills, `CLAUDE.md`, tool descriptions, harness-injected text);
- subagent caps in effect;
- representative inputs;
- expected behavior or rubric;
- actual outputs;
- task success and format compliance;
- response length and written-deliverable length, separately;
- factual and tool-use errors;
- latency, output tokens summed across the loop, cache reads, request count, subagent count, and cost.

Do not optimize against a single convenient example. Do not change the prompt and a cost lever in the same experiment.

## 2. Run the effort sweep first

Sweep `low`, `medium`, `high`, `xhigh`, and `max` on the same cases before touching the prompt. On Opus 5 this frequently resolves what looks like a prompt problem, and it tells you which level the prompt should be tuned for.

What to look for:

| Observation | Reading |
| --- | --- |
| `low` or `medium` holds quality | Step down; they produce strong quality at a fraction of tokens and latency |
| Review accuracy holds at lower effort | Split into a fast pass at review time and a thorough pass later |
| Quality keeps climbing to `xhigh` or `max` | Demanding coding or agentic work; keep it and size `max_tokens` at 64k or above |
| Response length barely changes across levels | Expected. Effort controls thinking, not visible length — fix length in the prompt |
| Settings inherited from Opus 4.8 look high | They are. That guidance started at `xhigh` for coding; Opus 5 starts at `high` |
| Opus 5.5 at an Opus 5 level runs long and costly | Expected: Opus 5.5 thinks more per turn at a given level. Its `medium` default often matches Opus 5 `high` |
| Opus 5.5 `low` close to `medium` | Common on coding evals; take the saving if your quality bar holds |
| Response length barely changes on Opus 5.5 either | Same rule: effort controls thinking; length goes in the prompt |

On Opus 5.5 always sweep with `effort` set explicitly — an omitted value silently means `medium` — and with `max_tokens` large enough (up to 128k) that truncation does not masquerade as a quality drop.

Where a session relies on prompt caching, test per-message effort too: it lets you run hard steps high and routine ones low without a cache miss.

## 3. Run the amplifier-removal experiment

Opus 5-specific, and often the largest single win. Take the instruction inventory from step 1 and remove every amplifier:

- verification instructions ("include a final verification step", "use a subagent to verify");
- double-check and re-verify instructions;
- separate verification stages in the harness;
- delegation encouragement;
- narration requests, if narration is already heavy;
- prompt-side vision workarounds tuned for older models;
- do-not-think or do-not-reason rules;
- on Opus 5.5: "think carefully" / "think step by step" lines, reasoning-in-reply requests, progress-summary scaffolding, and Opus 5 dampers that may no longer be load-bearing (length, correction narration, thinking-disabled mitigation).

Rerun the same cases at the default effort and report:

- cases that improved after removal;
- cases that regressed, and which specific instruction was load-bearing;
- net token, latency, and subagent-count change.

The documented expectation is that removing verification instructions reduces wasted tokens with no loss in quality. Measuring it is cheaper than arguing about it.

## 4. Build a representative set

Include:

- normal high-frequency cases;
- hard cases, including one harder than your current production ceiling — Opus 5 is strongest on difficult multi-file and end-to-end work, and easy-only evals undersell it;
- easy single-turn cases, where the delta from prior models is smaller;
- missing, ambiguous, malformed, and contradictory inputs;
- tool failure and empty retrieval cases;
- strict-format cases;
- length-sensitive cases for each surface the product uses: conversational reply, agentic narration, written file;
- long-run cases if the product has them — short evals hide budget, scope, delegation, and (on Opus 5.5) early-stop failures entirely;
- for chat products on Opus 5.5, multi-turn cases with short follow-ups, measuring time to first token as well as quality;
- for Opus 5.5 migrations, a case that switches models mid-conversation if a router or fallback can do that;
- known historical regressions.

## 5. Classify failures

Assign each failure a cause **and** a layer. The layer matters as much as the cause, because a prompt change cannot fix a parsing or parameter defect.

| Cause | Usual layer |
| --- | --- |
| Misunderstood objective | Prompt |
| Missing context or constraint | Prompt |
| Reply too long | Prompt (conciseness), never effort |
| Written file too long | Prompt (deliverable calibration) |
| Too much narration | Prompt (cadence) |
| Wasted verification passes | Prompt or harness (deletion) |
| Correction chatter | Prompt (correction limiter) |
| Too few findings in a review | Prompt (remove the limiter) |
| Scope expansion | Prompt (scope block) |
| Subagent sprawl | Prompt rule plus deterministic caps |
| Partial work, stubs | Spec delivery, usually the harness or workflow |
| Format or schema failure | Prompt, or move to structured outputs |
| Unsupported factual claim | Prompt (grounding, citations) |
| Wrong tool or call order | Tool descriptions and trigger conditions |
| Tool call appears as text | `thinking` disabled — a parameter, not a prompt, problem |
| Internal XML tags in output | Same |
| 400 disabling thinking | Parameter (effort above `high`) |
| `content[0].text` undefined | Parsing |
| Truncated output | `max_tokens` |
| Early stop or refusal after adding a budget | Budget size, or client-side `remaining` decrementing |
| Unexpected cost rise post-migration | Billing model: thinking now bills as output |
| Cold cache | Mutated effort, budget, or speed values |
| 429 on a fast-mode request | Fast-mode rate limits; needs a fallback path |
| Agent stops after a progress report (Opus 5.5) | Harness end-of-turn handling, then the unattended instruction |
| UI silent during tool calls (Opus 5.5) | `thinking.display` and rendering |
| 400 replaying thinking blocks (Opus 5.5) | Harness: prefix edited mid-conversation |
| `reasoning_extraction` refusal (Opus 5.5) | Prompt: reasoning-in-reply instruction |
| `bio` / `cyber` refusal (Opus 5.5) | Fallback configuration or program access |
| Slow first token in chat (Opus 5.5) | "Think carefully" line, effort, or re-examined earlier answers |
| Multi-app task missed a source (Opus 5.5) | Prompt: explore-broadly instruction |

## 6. Make the smallest targeted change

For each failure cluster:

1. State the observed failure and the layer.
2. Identify the missing instruction, the amplifier, or the misconfigured parameter.
3. Prefer a deletion over an addition when both would work.
4. Apply the smallest change that addresses it.
5. Avoid unrelated cleanup in the same experiment.
6. Keep an example only when it repairs a measured gap — and prefer a positive example of the style you want over an instruction about what not to do.

Where Anthropic documents an instruction block for the failure, start from that text rather than writing your own; it was measured. Check which model it was measured on before assuming it transfers.

## 7. Rerun and compare

Compare baseline and candidate on the same cases:

- task success and severity-weighted failures;
- completeness and format compliance;
- response and deliverable length against target;
- tool-call correctness and request count;
- subagent count and depth;
- regressions on previously passing cases;
- output tokens, cache reads, latency, and cost.

Lower resource use is an improvement only if the output still clears the quality bar. Optimize successful task completion per unit of constrained resource, not tokens in isolation.

Watch for a specific confound: an amplifier removal and an effort step-down both reduce token counts. Run them as separate experiments or you will not know which one bought the saving, or which one cost the quality.

## 8. Use graders carefully

Prefer narrow graders for distinct properties: required fields present; citations support claims; no unauthorized action; response under the target length; written file under the target length; no unrequested scope additions; subagent count within cap; findings count against a known-bug set.

A grader mixing many subjective properties is hard to interpret and hard to optimize against. Combine automated graders with human review of a sample.

For review-quality evaluation specifically, grade recall against a seeded bug set rather than asking a judge whether the review "looks thorough" — Opus 5's reported precision and recall make recall the measurable property.

## 9. Review before production

Manually inspect the optimized prompt and a sample of outputs. Aggregate improvement can hide specific inputs getting worse. Keep a regression set, and version the prompt, the instruction inventory, and the configuration together — a prompt is only meaningful alongside its effort level, its budget, and its caps.

## Compact report format

```text
Baseline: [model, effort, prompt version, score, tokens/task]
Effort sweep: [low / medium / high / xhigh / max -> score, latency, tokens]
Amplifier removal: [instructions removed, delta on score and tokens]
Main failure clusters: [top 3, each with its layer]
Change tested: [one targeted change]
Result: [quality delta, regressions, tokens, latency, cost]
Decision: keep / revise / reject
Next test: [single highest-value experiment]
```
