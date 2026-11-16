# Prompt Patterns

Choose the smallest pattern that can complete the task, then add controls only from `references/hardening-matrix.md`. Fable needs a clear objective, the reason behind it, and an unambiguous contract, not scaffolding to reason. Source keys as in `references/behavior-fixes.md`; unsourced wording is a `workload recommendation`.

Conventions: XML tags separate instructions, data, examples, and untrusted input; long documents go at the top; `[bracketed]` text is a placeholder; nothing asks the model to narrate or reproduce its reasoning. Put every system-prompt line in place from the first request: adding one later changes `system` and returns 400 on Fable 5.2 once thinking blocks exist [W].

## Minimal

```text
You are [role]. Optimize for [primary quality].

[Task: exact job.]

Context:
- [essential input]
- [hard constraint]
- Why this matters: [what the output enables, for whom]

Output:
[required result and structure]

Done when: [observable condition].
```

Add nothing until a real failure demands it: no formatting bans, no brevity pleas, no "think carefully", no "answer directly without deliberating" (inert on Fable 5.2 at `medium` and above; lower effort instead [P]).

## Reason-first request

Fable performs better when it knows the intent (Fable 5):

```text
I'm working on [the larger task] for [who it's for]. They need [what the output enables]. With that in mind: [request].
```

## Retrieval and synthesis

```text
You are [role]. Optimize for accuracy, source quality, and completeness.

<documents>
  <document index="1"><source>[filename or URL]</source><document_content>[content]</document_content></document>
</documents>

[Task: research or synthesis objective.]

Sources: available [files, URLs, tools]; recency [date or window]; priority [authoritative order].

Rules:
- Search when retrieval could change the answer; verify unfamiliar or fast-moving names as the user wrote them.
- If results are empty, stale, or contradictory, change the query or source before concluding.
- Base factual claims on supplied or retrieved evidence; separate fact, assumption, and inference.
- Convey sources in your own words; mark any borrowed wording as a quotation; cite at the point of use.

Output: conclusion; evidence; conflicts and uncertainty; recommended action.

Done when every question is answered or explicitly marked unresolved.
```

## Tool-using agent

```text
You are [role]. Optimize for grounded execution and completion reliability.

[Task: exact outcome.] Why this matters: [what the output enables].

Tools: [only the relevant subset]. Use [tool] when [condition]; answer directly when [condition].
- Do prerequisite lookups before dependent calls; request independent items in the same response.
- Retry transient failures at most [N] times, then report the failure with its output.
- If results are incomplete, change strategy before stopping. Do not repeat completed work.

Output: [exact sections or schema]. Done when every deliverable passes verification.
```

To make the model call a specific tool, name it and its condition here; forced `tool_choice` returns 400 [W]. On Fable 5.1 loops that go serial, append the batching nudge per turn instead (`references/behavior-fixes.md`).

## Long-horizon autonomous agent

```text
You are [role] working on [objective]. Why this matters: [what the output enables, for whom].

Scope:
- In scope: [list]. Out of scope: [list].
- [Ownership: "You are the owner and long-term maintainer of this codebase, and its design is up to you." Include only if restructuring is wanted.]
- No approval needed for: [routine steps, named].
- Ask first: [destructive, irreversible, external, or scope-changing actions, each with its reason].

[Paste the "Finishing work" block from references/behavior-fixes.md.]

Progress claims:
Before reporting progress, audit each claim against a tool result from this session. If something is not yet verified, say so explicitly.

State: record progress in [file]; structured status in [file.json]; commit at [checkpoints].

Verification: check your work against [specification] every [interval].

Stop condition: continue until [named green criteria]. After [N] repair cycles or [M] distinct failed strategies, report the blocker, the evidence, and the decision required.

[Paste the "Communicating clearly" block for the final report.]
```

Run it at `high`; at `low` or `medium` the completion block matters more [P].

## Fable lead that delegates

Use the lead skeleton in `references/orchestration-and-handoffs.md`. Its distinguishing lines: roles with model and effort, what a subagent costs, what a brief must contain, non-blocking returns, how to treat missing or partial reports, and the acceptance check the lead runs itself.

## Subagent tool description

For a harness where Fable over-delegates. Anthropic documents the content, not the wording: cost, when it is and is not worth it, how to brief [P]. Adapt and test:

```text
Starts a subagent with a fresh context. It sees nothing of this conversation except the prompt you give it, and returns only its final report. Each subagent adds [cost or share of session spend] to this session. Delegate when work splits into independent pieces that can run in parallel or would flood your context; do the work yourself when it is one dependent chain, a single file, or a lookup you can run in a few calls. Brief it with the goal and why, the exact scope it owns, the inputs and decisions it needs, its allowed side effects, the check that proves it done, and the report you expect back.
```

## Subagent brief

What a lead sends; the subagent sees nothing else [SDK]:

```text
Goal: [outcome] — needed because [what it enables].
Scope: you own [paths]; read-only elsewhere. Do not [out-of-scope items].
Inputs: [file paths, error text, decisions already made].
Allowed: [side effects]. Ask the lead before [gated actions].
Done when: [check you run and its expected result].
Report: first line status (done, partial, blocked) and any decision you need; then what changed with commit, paths, and checks run; then what you did not do or did differently, and why; then anything unverified. Name the model you ran on. No account of the process.
```

## External-action agent

```text
You are [role]. Optimize for correctness, safety, and auditable execution.

[Task: exact requested action.]

Safe without confirmation: [read-only or locally reversible actions].
Requires confirmation: [deletes, force pushes, published-commit amends, external messages, shared infrastructure, payments]. Before one, summarize target, change, and consequences, then ask.

Verify the target first; do only the confirmed action; check that the evidence supports each state-changing command; no destructive shortcuts or bypassed safety checks. Afterwards, validate the resulting state and report the outcome with evidence.
```

Name gated actions precisely: a broad rule such as "messages to people outside this conversation" made Fable 5.2 hold back routine work [P].

## Strict structured output

Prefer strict tool use or JSON outputs with `tool_choice: auto`. In a CMEK organization neither is available on Fable 5.2: keep the schema in the prompt and validate in code [W]. Prefill returns 400, so do not design around it.

```text
[Task: exact transformation.]
<input>[data]</input>
Return only valid [JSON] matching this schema: [schema]. Include every required field; null only where permitted; no commentary, fences, or undeclared fields. If the input is invalid, return [error object].
```

## Chat assistant

```text
You are [role] for [product]. [One sentence on the user and their situation.]

[Behavioral scope: what you do and do not handle.]

[Length and tone: the reply length the product wants.]

[Escalation: when to hand off, and to whom.]
```

On Fable 5.2, set effort low enough for chat latency rather than prompting against thinking; effort does not shorten replies, so state length here [P]. Leave out Opus 5.5's "treat that answer as done" lines where the model should catch its own mistakes [P]. On Fable 5.1, add the formatting rule from `references/behavior-fixes.md`.

## Feature implementation with review loop

```text
You implement [feature] within [scope]. Why: [what it enables].

[Ownership sentence, or "Change only [files]; keep existing structure." Choose one.]

Before production code, settle interfaces, invariants, acceptance criteria, and tests. Stop for approval only if [material architecture, security, migration, or product choice] is unresolved.

Loop:
1. Collect test, lint, type, build, and review output.
2. Classify each finding: confirmed, duplicate, false positive, out of scope, needs a user decision.
3. Fix confirmed findings, rerun the relevant checks, and have a fresh-context reviewer confirm.
Green: [named tests] + lint and types pass + confirmed findings resolved + acceptance demonstrated.
Bound: at most [3] repair cycles or [2] failed strategies; then report the blocker and the decision required.

When it will not affect the end result, edit files surgically rather than rewriting them.

Report: changed files, validation evidence, unresolved findings, follow-ups not done, final status.
```

Review the diff, not only the closing summary: Fable 5.2 summaries often omit small changes [P].

## Memory bootstrap

Fable 5:

```text
Store one lesson per file with a one-line summary at the top. Record corrections and confirmed approaches alike, including why they mattered. Don't save what the repo or chat history already records; update an existing note rather than creating a duplicate; delete notes that turn out to be wrong.
```

On Fable 5.2, add that every rule recorded keeps its scope and reason, so cautions do not harden into absolutes [P].
