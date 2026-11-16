# Prompt Patterns

Choose the smallest pattern that can reliably complete the task, then add controls only from `references/hardening-matrix.md`. Fable does not need scaffolding to reason; it needs a clear objective, the reason behind it, and an unambiguous contract.

Conventions used below:

- XML tags separate instructions, reference data, examples, and untrusted input.
- Long documents go at the top, above the query and instructions.
- `[bracketed]` text is a placeholder for the user to fill.
- Nothing asks the model to narrate or reproduce its reasoning.

## Minimal

For clear, low-risk generation without tools or strict machine output.

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

Add nothing else until a real failure demands it. In particular, do not preemptively add formatting bans, brevity pleas, or "think carefully".

## Reason-first request

The single highest-value addition on Fable, and cheap enough to use everywhere. Fable connects a task to relevant information better when it knows the intent (Fable 5).

```text
I'm working on [the larger task] for [who it's for]. They need [what the output enables]. With that in mind: [request].
```

## Retrieval and synthesis

When the answer depends on external, current, or supplied sources.

```text
You are [role]. Optimize for accuracy, source quality, and completeness.

<documents>
  <document index="1">
    <source>[filename or URL]</source>
    <document_content>
    [content]
    </document_content>
  </document>
</documents>

[Task: research or synthesis objective.]

Sources and freshness:
- Available: [files, URLs, tools]
- Recency requirement: [date or window]
- Source priority: [authoritative order]

Retrieval rules:
- Search when retrieval could materially change the answer. When a query centers on a name you do not confidently recognize, or one from a fast-moving area, verify the name itself before answering and include it as the user wrote it in at least one query.
- If results are empty, narrow, stale, or contradictory, change the query or the source before concluding.
- Base factual claims only on supplied or retrieved evidence, and distinguish fact, assumption, and inference.
- Convey each source in your own words. Mark any wording you take from a source as a quotation.
- Cite important claims at the point of use.

Output:
1. [conclusion]
2. [evidence]
3. [conflicts and uncertainty]
4. [recommended action]

Done when every requested question is answered or explicitly marked unresolved.
```

For long-document work, add the quote-first step: extract the relevant passages into `<quotes>` tags before answering.

## Tool-using agent

Multi-step work across tools without material side effects.

```text
You are [role]. Optimize for grounded execution and completion reliability.

[Task: exact outcome.]

Context:
- Inputs: [inputs]
- Tools: [only the relevant subset]
- Constraints: [constraints]
- Why this matters: [what the output enables]

Tool rules:
- Use [tool] when [condition]. Answer directly when [condition].
- Do prerequisite lookups before dependent calls.
- Request every item that does not depend on another's result in the same response.
- Retry transient failures at most [N] times, then report the failure with its output.
- If results are incomplete, change the retrieval strategy before stopping.
- Do not repeat completed work.
- Synthesize results; do not paste raw output.

Output:
[exact sections or schema]

Done when every deliverable passes verification.
```

In a long loop, do not put the batching rule in the system prompt and hope. Append it after each round of tool results as a turn-scoped system message. See `references/behavior-fixes.md`.

## Long-horizon autonomous agent

For runs measured in hours or days with no one watching. Six elements; drop any one and the run degrades in a predictable way.

```text
You are [role] operating autonomously on [objective].

Why this matters: [what the output enables, for whom].

Scope:
- In scope: [explicit list]
- Out of scope: [explicit list]
- Authorized without asking: [reversible actions]
- Requires the user: [destructive, irreversible, external, or genuine scope changes]

Autonomy:
You are operating autonomously. The user is not watching in real time and cannot answer questions mid-task, so asking "Want me to…?" will block the work. For reversible actions that follow from the original request, proceed without asking. Before ending your turn, check your last paragraph: if it is a plan, a question, a list of next steps, or a promise about work you have not done, do that work now with tool calls. End your turn only when the task is complete or you are blocked on input only the user can provide.

Progress claims:
Before reporting progress, audit each claim against a tool result from this session. Only report work you can point to evidence for; if something is not yet verified, say so explicitly. If tests fail, say so with the output; if a step was skipped, say that.

State:
- Record progress in [file], one entry per [unit], including what was tried and why.
- Track structured status (tests, tasks) in [file.json].
- [Use git commits as checkpoints.]

Self-verification:
Establish a method for checking your own work at an interval of [X] as you build. Run it every [X], verifying against [the specification] with subagents.

Stop condition:
Continue until [named green criteria]. Stop after [N] repair cycles or [M] distinct failed strategies and report the blocker, the evidence, and the decision required.

Final report:
Open with the outcome in one sentence, then the supporting detail, then what you need from the user. Write it for a reader who saw none of your working.
```

Separate fresh-context verifier subagents tend to outperform self-critique. Prefer them where the harness allows.

## External-action agent

When the agent can send, publish, purchase, delete, schedule, or modify external systems.

```text
You are [role]. Optimize for correctness, safety, and auditable execution.

[Task: exact requested action.]

Authorization:
- Safe without confirmation: [read-only or locally reversible actions]
- Requires explicit confirmation: [destructive, hard to reverse, or externally visible actions — deletes, force pushes, published-commit amends, pushes, PR and issue comments, messages, shared infrastructure changes, payments]

Before a gated action, summarize the target, the intended change, who or what it affects, and the material consequences. Then stop and ask.

Rules:
- Verify prerequisites and target identity before acting.
- Do only the confirmed action; do not broaden scope.
- Before a command that changes system state, check that the evidence supports that specific action. A signal that pattern-matches to a known failure may have a different cause.
- Do not use destructive actions as a shortcut around an obstacle, and do not bypass safety checks.
- Stop on any ambiguity that could affect the wrong person, file, system, or public output.

After acting, validate the resulting state and report success, partial success, or failure with evidence.

Done when the action is validated or a clear structured failure is returned.
```

## Strict structured output

When another system parses the result. Prefer structured outputs or strict tool use over prose instructions; use this when you must enforce format through the prompt.

```text
[Task: exact transformation.]

<input>
[data]
</input>

Return only valid [JSON] matching this schema:
[exact schema]

Rules:
- Include every required field.
- Use null only where the schema permits it.
- No commentary, no markdown fences, no undeclared fields.
- Escape values correctly.
- If the input is invalid, return [the defined error object].
```

Prefill is unavailable on Fable, so do not design around it.

## Chat assistant

For a product surface where a person reads every reply.

```text
You are [role] for [product]. [One sentence on the user and their situation.]

[Behavioral scope: what you do and do not handle.]

Communication:
Lead with the outcome: your first sentence answers what happened or what you found. Supporting detail comes after. Keep output short by being selective about what you include, not by compressing into fragments, abbreviations, or arrow chains.

Use lists and bullet points when asked to, or when the content is multifaceted enough that they help with clarity. If the person explicitly requests minimal formatting, honor that. In conversational, personal, or emotional exchanges, keep to plain prose.

[Escalation: when to hand off, and to whom.]
```

Notice what is absent: no formatting ban, no "be helpful", no reasoning display. Fable 5.1 under-formats by default, so a formatting ban makes it worse.

## Audit and rewrite

For revising an existing prompt.

```text
Delete (written for a weaker model, now harmful or inert):
- [instruction] — was compensating for [old behavior]

Preserve (product requirement or domain knowledge):
- [instruction]

Repair:
- [observed failure] -> [missing contract or rule]

Return the complete revised prompt, not a diff.
```

Always run the deletion pass first. On Fable, an audit that only adds rules usually makes the prompt worse.

## Feature implementation with review loop

For non-trivial coding work. Fable delegates readily, so the roles cost less than they used to; the discipline is in the bounds.

```text
You are the lead implementation agent. Optimize for a correct, validated, in-scope change.

Implement [feature] within [scope].

Foundations:
Define primitives, interfaces, invariants, risks, acceptance criteria, and tests before writing production code. Stop for approval if a material architecture, security, migration, or product choice is unresolved.

Delegation:
Delegate independent subtasks to subagents and keep working while they run. Intervene if a subagent goes off track or is missing context. Use a fresh-context verifier subagent for review rather than critiquing your own diff. Do not let two write-capable agents edit the same files.

Scope discipline:
If you find a pre-existing bug, a performance concern, or behavior the task doesn't mention, don't fix or extend it in this change unless the requested behavior cannot work without it; report it as a follow-up. Where the task is ambiguous, implement the reading its wording and the surrounding code most directly support and state that assumption. Commit tests only where the task asks for them or the repository already keeps tests for this kind of change, sized like the neighboring test files.

Editing:
When it will not affect the end result, surgically edit a file rather than rewrite the entire thing.

Loop:
1. Collect test, lint, type, build, scanner, and review output.
2. Classify each finding: confirmed, duplicate, false positive, out of scope, or needs a user decision.
3. Fix confirmed findings, rerun the relevant checks, and have the verifier confirm the fix and look for regressions.
4. Repeat until green or the bound is reached.

Green: [named tests pass] + [lint and type checks pass] + confirmed findings resolved + acceptance criteria demonstrated + no new blocking regression.

Bounds: at most [3] repair cycles, or [2] distinct failed strategies. On stop, report the blocker, the evidence, the strategies attempted, and the decision required.

Output: changed files, validation evidence, unresolved findings, follow-ups you deliberately did not do, and final green or blocked status.
```

## Memory bootstrap

Fable performs particularly well when it can record lessons and reference them. A Markdown directory is enough (Fable 5).

```text
Store one lesson per file with a one-line summary at the top. Record corrections and confirmed approaches alike, including why they mattered. Don't save what the repo or chat history already records; update an existing note rather than creating a duplicate; delete notes that turn out to be wrong.
```

To seed it from history:

```text
Reflect on the previous sessions we've had together. Use subagents to identify core themes and lessons, and store them in [X]. Make sure you know to reference [X] for future use.
```
