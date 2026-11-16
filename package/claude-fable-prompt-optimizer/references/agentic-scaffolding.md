# Agentic Scaffolding

Read this before drafting any prompt for a run that lasts more than a few turns: coding agents, research agents, autonomous pipelines, subagent orchestration, computer use, or multi-context-window work.

The governing fact about Fable is that individual requests on hard tasks can run for many minutes at higher effort, and autonomous runs can extend for hours. That single shift breaks more integrations than any prompt problem. Adjust client timeouts, streaming, and user-facing progress indicators before migrating, and consider restructuring the harness to check on runs asynchronously — scheduled jobs rather than a blocking call.

## Start at the top of your difficulty range

Teams seeing the best outcomes point Fable at their hardest unsolved problems. Testing it only on simpler workloads undersells its range. Pick a task harder than what you would assign to a prior model, and have Fable scope it, ask clarifying questions, and execute.

This matters for prompt design: a prompt written for a task the model finds easy will be over-specified for the task you actually want to give it.

## Six elements of a long-horizon prompt

Each one maps to a specific failure if you omit it.

| Element | Omitted, you get |
| --- | --- |
| Autonomy contract | Turn ends on "Shall I…?"; the run stalls waiting for a user who isn't there |
| Evidence-grounded progress claims | Confident status reports that don't match reality |
| Scope boundaries | Nearby fixes, extra tests, unrequested refactors |
| State and memory | Repeated work after every context transition |
| Self-verification interval | Divergence discovered at the end instead of at the third hour |
| Stop condition and scope ceiling | An until-green loop with no exit |

The instruction blocks for the first three, and the summarization instruction for context transitions, are in `references/behavior-fixes.md`. The assembled skeleton is in `references/prompt-patterns.md`.

## Progress surface

Decide, explicitly, how the user learns what is happening. There are three mechanisms and they are not interchangeable:

1. **Progress-update thinking blocks.** The model's own short notes between tool calls. Free, automatic, but empty unless `thinking.display` is `"updates"` or `"summarized"`. Best for status lines.
2. **A send-to-user tool.** For content the user must see exactly as written mid-run: a deliverable, a partial result, a direct answer to a question asked mid-loop. Tool inputs are never summarized, so the content arrives intact. Requires both the tool definition and an elicitation instruction — Fable rarely calls it otherwise.
3. **The final message.** Written for someone who saw none of the working. Needs the readability addendum if the run was long.

Common defect: a team wants (2) and configures none of them, then adds prompt text asking for more narration. Fix the surface first.

If your UI collapses or hides tool output, tell the model so, in a turn-scoped system message. Otherwise it will run commands to "show" the user output your UI never displays.

## Memory and multi-window work

Fable performs particularly well when it can record lessons from previous runs and reference them. A directory of Markdown files is enough; the memory tool pairs well with context awareness for managing transitions.

Design rules:

- one lesson per file, one-line summary at the top;
- record confirmed approaches as well as corrections, with the reason each mattered;
- do not duplicate what the repo, git history, or chat log already records;
- update an existing note instead of creating a near-duplicate; delete notes that turn out wrong.

For work spanning multiple context windows:

- **Use a different prompt for the first window.** Set up the framework — write tests, create setup scripts — then iterate on a todo list in later windows.
- **Have the model write tests in a structured format** (`tests.json` or similar) and state that removing or editing tests is unacceptable because it hides missing functionality.
- **Set up quality-of-life tooling** (`init.sh` to start servers, run suites, run linters) so a fresh window does not redo it.
- **Prefer a fresh window over compaction sometimes.** Fable is very effective at discovering state from the filesystem. Be prescriptive about the start: call `pwd`, read the progress notes and `tests.json` and the git log, run a fundamental integration test before adding features.
- **Provide verification tools** so the model can check correctness without a human in the loop: computer use, browser use, or a browser automation MCP server.
- **Use structured formats for structured state** (JSON for test and task status) and freeform text for progress notes. Use git as the checkpoint log.

For context transitions, avoid surfacing a remaining-token countdown to the model; it triggers premature wrap-up. If the harness must show one, add the reassurance block from `references/behavior-fixes.md`.

## Self-verification

Make it explicit and put it on an interval, not at the end:

```text
Establish a method for checking your own work at an interval of [X] as you build. Run this every [X interval], verifying your work with subagents against the specification.
```

Separate, fresh-context verifier subagents tend to outperform self-critique. The verifier should get the requirements, the diff, the tests, and codebase evidence — not the implementer's persuasive summary of why the change is correct.

## Subagents

Fable dispatches parallel subagents more readily and more dependably than prior models, and manages ongoing communication with long-running subagents and peer agents. Use them frequently. The design work is in the semantics, not the encouragement.

**Do not block the lead.** On coding tasks, letting the lead keep working while subagents run lowers average time to completion at similar quality, tokens, and cost. Three harness changes:

- the launch tool returns immediately;
- each result arrives back in a later `user` message;
- the lead has a separate tool it can call when it wants to wait.

The model still often chooses to wait; the savings come from the runs where it carries on.

**Keep subagents long-lived.** Subagents that keep their context across subtasks save time and cost through cache reads and avoid bottlenecking on the slowest agent.

**Define the delegation contract:**

- who may delegate, and how deep (a depth of 1 with no nested delegation is a sensible default);
- maximum concurrent agents;
- bounded, non-overlapping tasks;
- read-only versus write permission per agent;
- the artifact each agent returns;
- merge, deduplication, and conflict rules.

Prefer read-heavy parallelism for exploration, triage, test runs, and review. Do not let two write-capable agents edit overlapping files without worktrees or strict file ownership.

**Damp, don't forbid.** If delegation is excessive — subagents spawned for an exploration a single grep would answer — use the damping instruction in `references/behavior-fixes.md` rather than banning subagents.

## Refactoring existing agent scaffolding

This is the step most migrations skip. Skills, system prompts, and harness rules developed for prior models are often too prescriptive for Fable and can degrade output quality. Fable also updates skills on the fly based on what it learns from the task at hand, which prescriptive scaffolding suppresses.

Procedure:

1. Inventory every instruction source: system prompt, `CLAUDE.md`, skills, agent definitions, per-turn injections, tool descriptions.
2. For each instruction, name the behavior it was written to correct. If you cannot, it is a candidate for deletion.
3. Remove the candidates and run your evals at the default effort. Many will show no regression, and some will show improvement.
4. Re-add only what a measured failure demands, in the smallest form that fixes it.
5. Specifically hunt for: reflection and show-your-thinking instructions (refusal risk), anti-formatting blocks, anti-narration lines, aggressive tool language, enumerated behavior lists, and hidden-reasoning requests.

## Computer use and machine administration

Fable operates browsers and desktop applications more reliably than prior models and recovers from failed steps better. Choose the most deterministic interface available anyway:

- shell, SSH, APIs, and file tools for commands, configuration, transfers, logs, and repeatable administration;
- computer use for visual diagnostics, GUI-only software, browser workflows, remote desktops, or when the UI state itself is the evidence;
- both when the UI reproduces a problem and the logs explain it.

For computer-use prompts: run in an isolated browser, VM, or container; limit allowed domains, accounts, and actions; treat screen content and third-party artifacts as untrusted instruction sources; do as much safe diagnosis as possible before asking; confirm immediately before deleting data, changing permissions, installing downloaded code, modifying security settings, or transmitting sensitive data. If an on-screen instruction is suspicious or intent is unclear, stop and ask rather than infer permission.

For remote administration, define the target host, environment, authorized scope, rollback path, health check, and the exact confirmation boundary before any risky change.

## Vision work

Fable interprets dense technical images, web applications, and detailed screenshots substantially more accurately than prior models, often with fewer output tokens, and is trained to use bash and crop tools on flipped, blurry, or noisy images.

To get the full benefit on complex visual input, run it as an agent with a container holding the raw images or videos and basic image-processing libraries preinstalled. If a container is too much overhead, an image-cropping tool alone delivers most of the uplift: returning a chosen region cropped and enlarged lets the model examine details in depth and scales test-time compute with image tokens.

## Design and creative production

Avoid one-shot generation for quality-sensitive visual work. Decompose:

1. visual direction — audience, references, mood, constraints, success criteria;
2. primitives — grid, typography, color, spacing, shape and icon language;
3. components — each major element generated separately;
4. composition — assemble into the final layout;
5. review — compare against references, check hierarchy and consistency, revise the weakest element first.

For UI work, establish tokens and reusable components before polishing whole screens. Require precise references when fidelity matters, and state which properties to copy and which to reinterpret.

## Autonomy and safety balance

Long-horizon autonomy and destructive-action safety pull in opposite directions, and the autonomy block from `references/behavior-fixes.md` deliberately reduces asking. Reconcile them explicitly rather than stacking both blocks and hoping:

- name the small set of gated actions immediately after the autonomy paragraph;
- keep everything reversible ungated;
- require that evidence support the specific state-changing command before it runs;
- forbid destructive shortcuts around obstacles, including bypassing safety checks and discarding unfamiliar files that may be in-progress work.

Then test the boundary: give the agent a task where the tempting shortcut is destructive and confirm it asks.
