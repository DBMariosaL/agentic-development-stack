# Orchestration and Handoffs

Two jobs this file covers: (A) writing the prompt or mandate for a Fable 5.2 lead that plans, delegates, and judges; (B) writing the report a subagent hands back to a Fable parent. Facts carry a source key; everything else is a `workload recommendation`. Read on 2026-11-16.

Sources: [P] `https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-fable-5-2` · [OPT] `https://platform.claude.com/docs/en/about-claude/models/optimizing-for-cost-and-intelligence` · [SDK] `https://code.claude.com/docs/en/agent-sdk/subagents` · [SUB] `https://code.claude.com/docs/en/sub-agents` · [CC] `https://code.claude.com/docs/en/model-config` · [R] `https://platform.claude.com/docs/en/build-with-claude/refusals-and-fallback` · [F5] `https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-fable-5`

## What is documented about Fable 5.2 as a lead

- How much it delegates depends on the harness: with a minimal subagent tool on short tasks it rarely delegated; in a coding product whose prompts invite delegation it delegated readily [P].
- At `xhigh` and `max` it started subagents to review its own work, which Fable 5.1 did not do on the same tasks [P].
- Early testers had good results with it as planner and orchestrator for other models; subagents can be a large share of session cost, so check which model they use by default [P].
- On a defect-search benchmark, Fable 5.2 as orchestrator in place of Opus 5.5 (both with Sonnet 5.5 subagents) cost 19% more and scored about the same; Fable 5.2 alone scored higher than Opus 5.5 alone at 1.5 to 2.4 times the cost [OPT]. For one dependent chain, or work that fits one context, the orchestrator's model alone at lower effort came out ahead in every case measured on earlier models [OPT].
- Cautions pile up from memory, notes, and instruction files, mostly when several agents work together; the model follows them closely and asks for approvals it does not need. A rule listing "sending messages to people outside this conversation" as needing approval made it hold back about half of routine requests to colleagues [P].
- The model treats "never" as absolute; "continue" is a weak approval; say exactly what is approved [P].
- A closing PR summary from Fable 5.2 often left out small changes: review the diff as well as the summary [P].

Consequence for a pilot that mostly decides and delegates (`workload recommendation`): Fable earns its price on judgment, decomposition, and acceptance, not on volume. Put bulk authoring on cheaper subagents, keep the lead's own tool use for checks that drive decisions, and measure cost per accepted result against Opus 5.5 leading the same team.

## Subagent mechanics the lead must know (Claude Code and Agent SDK)

| Fact | Source |
| --- | --- |
| A non-fork subagent receives only its own system prompt, the Agent tool's prompt string, project `CLAUDE.md` (unless `omitClaudeMd`), and its tools; not the parent's history or system prompt | [SDK] |
| Only the subagent's final message returns; the parent may summarize it | [SDK] |
| Spawned subagents run in the background by default (`status: "async_launched"`); the report arrives in a later turn; the lead blocks only when its next action needs the report | [SDK] |
| At `maxTurns` the output is marked partial | [SDK] |
| An API error that ends a subagent early is never delivered as its result | [SDK] |
| The final message is scanned: harness-only control tags and `Human:`/`Assistant:` turn markers are neutralized, and a `[harness: ...]` line is prepended for some matches; text is never removed | [SDK] |
| Default caps: nesting depth 3 (`CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH`), 20 concurrent (`CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS`), no spend cap unless `maxBudgetUsd` / `max_budget_usd` is set | [SDK] |
| Subagent model order: per-call `model`, then the definition's `model`, then `CLAUDE_CODE_SUBAGENT_MODEL`, then the parent's model; aliases include `fable`, `opus`, `sonnet`, `haiku`, `inherit` | [SUB][SDK] |
| With a Fable parent, the built-in Explore agent runs on Opus with a subscription, Console account, or gateway, and stays on Fable on Bedrock, Google Cloud, and Foundry | [SUB] |
| A subagent never pauses to ask at a classifier-flagged request: in Claude Code it switches model (bio to Opus 5, cyber to Opus 4.8) or, with the "Ask each time" setting, fails | [CC] |
| API `fallbacks` does not carry over to model calls made inside tool execution | [R] |
| For dozens to hundreds of agents, the `Workflow` tool moves orchestration into a script outside the conversation | [SDK] |
| Descriptions route delegation; custom descriptions past 15,000 tokens in total raise a startup warning, so keep them short and put detail in the subagent's own prompt | [SUB] |

## A. Writing for a Fable lead

### Delete first

From the lead's system prompt, skills, and agent files, remove standing "delegate" or "use subagents where possible" lines unless tests show the lead under-delegates [P]; old cautions whose reason is gone; absolute "never" rules without scope; stop-at-first-error rules you do not need; a visible token budget [P].

### The delegation contract (`workload recommendation`)

State each item once:

1. **What is worth delegating.** Independent, bounded units, especially work larger than one context window; not a single dependent chain [OPT]. Say what a subagent costs in this harness; that sentence is what cut delegation in Anthropic's test [P].
2. **Roles and models.** Name the model and effort per role, because the default is the parent's model [SUB]. Example: authors on Opus at `medium`, reviewers on another model family, the lead at `high`.
3. **Brief contents.** The prompt string is all a non-fork subagent gets from the lead [SDK], so every brief carries: the goal and why it matters, the exact scope (files or paths owned), inputs and decisions already made, constraints and allowed side effects, the check that proves it done, and the return format in part B.
4. **Ownership.** One writer per file set; reviewers read-only; worktree isolation for parallel writers.
5. **Non-blocking.** Keep working while subagents run; wait only when the next step needs the report.
6. **Caps.** Depth (1 is a sensible default when the lead alone coordinates), concurrency, and a spend cap set in the harness; a prompt only steers [SDK].
7. **Approvals.** Name the routine steps that need no approval, including messaging and re-tasking its own subagents, and name the few actions that do [P].

### Reading returns (`workload recommendation`)

Tell the lead how to treat what comes back:

- A report is a claim. Accept a result when the evidence it cites (diff, commit, command output) supports it; open the diff for anything that will be merged or decided on [P].
- No report, or a partial marker, means not done [SDK]. Re-task or resume; do not infer success from silence.
- A report whose model line differs from the one assigned may come from a fallback or a different alias resolution [SUB][CC]; weigh it accordingly.
- Disagreement between author and reviewer is the lead's decision: rule on it with evidence, or send a narrow follow-up question.
- Give cross-family reviewers the requirements, the diff, and the tests, not the author's argument for the change. Fresh-context verifiers tend to outperform self-critique [F5].

### Continue or stop (`workload recommendation`, built on [P])

Continue on everything that does not depend on an open answer; diagnose ordinary obstacles (timeouts, empty results, failing tools) before reporting them. Stop only for a decision only the user can make, a deliberate blocker, or a risky or irreversible action that needs confirmation. Pair this with the "Finishing work" block in `references/behavior-fixes.md` when the lead runs at `low` or `medium`.

### What the lead verifies itself

The acceptance check named in its own mandate; anything a subagent reports as verified that changes the final decision; the combined state after merging work from several subagents. Isolated passing checks do not prove the integrated result.

### Lead prompt skeleton

```text
You lead [objective] for [who it's for]. Why it matters: [what the result enables].

You decide, decompose, and accept. Subagents do the bulk work:
- [role]: [model], effort [level], [read-only | owns paths]
- [role]: [model], effort [level], read-only reviewer
A subagent costs [what it adds in this harness]. Delegate independent, bounded pieces; do work that is one dependent chain yourself.

Each brief contains: goal and reason, owned scope, inputs and decisions already made, constraints and allowed effects, the check that proves it done, and the report format below. A subagent sees none of this conversation.

Keep working while subagents run. A missing or partial report is not done. Accept a result when its cited evidence supports it; open the diff before merging. You may brief, re-task, and message your own subagents without asking. Ask the user before [gated actions].

Done when [observable acceptance condition], checked by you.
```

## B. Writing the handoff a Fable parent reads

Documented constraints: only the final message reaches the parent, which may summarize it [SDK]; Fable 5.2 readers handle self-contained, plain reports best, and Anthropic's "Communicating clearly" block exists for exactly this low-context reader [P]; progress claims should be audited against tool results [F5]; asking a Fable model or Opus 5.5 to write out its internal reasoning risks a `reasoning_extraction` refusal [R][P].

Report contract (`workload recommendation`):

1. **First line:** status (`done`, `partial`, `blocked`) and, if any, the one decision needed from the parent.
2. **Result:** what changed or what was found, with pointers the parent can check (commit SHA, paths, command and result).
3. **Not done or deviating from the brief:** each item with its reason.
4. **Unverified:** claims not checked against a tool result, labelled as such.
5. **Run facts:** model and effort used, checks run.

Leave out the narrative of the work, reasoning transcripts, praise for the result, and vocabulary invented during the run. Keep it short enough that the parent need not summarize it.

Subagent-side line to put in a brief:

```text
End with a report for a parent that has not seen your work: first line status (done, partial, blocked) and any decision you need; then what changed with commit, paths, and checks run; then what you did not do or did differently, and why; then anything unverified. Name the model you ran on. No account of the process.
```

## Field ideas (third-party, not documentation)

Test these; they are not Anthropic guidance.

- Ask each subagent to state the model it used and what it checked, and request a fixed handoff (root cause, files changed, tests run, remaining uncertainty, decision needed). Source: João Queirós, "How to Prompt Claude Fable 5.2: Five Changes That Matter", 2026-11-11, `https://www.ai.joaoqueiros.com/blog/rob-shocks-claude-fable-5-2-prompting-model-effort-guide`.
- Do not predefine subagent archetypes; let the lead invent roles per task. Source: `https://github.com/per-simmons/fable-orchestration/blob/master/SKILL.md` (written for Fable 5, undated). It conflicts with stacks that fix roles by model family; test before adopting.

Rejected: the same repository's claim that asking for reasoning in the reply "silently reroutes to Opus 4.8". The refusals page documents `reasoning_extraction` as returned to the caller with no fallback [R].
