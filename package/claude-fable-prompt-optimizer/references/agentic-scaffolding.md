# Agentic Scaffolding

Read this before drafting a prompt for a run longer than a few turns: coding agents, research agents, autonomous pipelines, computer use, or multi-context-window work. For a Fable lead that delegates, and for subagent reports to a Fable parent, read `references/orchestration-and-handoffs.md`. Read on 2026-11-16; source keys as in `references/behavior-fixes.md`.

## Long turns are the default

Requests on hard tasks can run many minutes at higher effort, and autonomous runs can extend for hours; adjust client timeouts, streaming, and progress indicators, and consider checking runs asynchronously rather than blocking [F5]. Anthropic recommends Fable 5.2 for long-running asynchronous work where nobody needs frequent updates [P], and reports it running ambiguous engineering work for days (product page) and, in one internal experiment, coordinating over 1,000 subagents for eight days (launch post; vendor-reported).

Start at the top of your difficulty range: testing Fable only on simpler workloads undersells it [F5]. A prompt written for a task the model finds easy is over-specified for the task you want to give it.

## Six elements of a long-horizon prompt

| Element | Omitted, you get | Block |
| --- | --- | --- |
| Completion contract | Turn ends listing what remains or offering to continue | "Finishing work" (Fable 5.2) |
| Evidence-grounded progress claims | Status reports that don't match reality | Progress claims (Fable 5) |
| Scope and ownership | Duplicated code, or unrequested refactors, depending on the ownership sentence | Code ownership (Fable 5.2) |
| State and memory | Repeated work after each context transition | Memory below |
| Verification interval | Divergence found at the end instead of the third hour | Self-verification below |
| Stop condition and scope ceiling | An until-green loop with no exit | Prompt patterns |

Blocks are in `references/behavior-fixes.md`; the assembled skeleton is in `references/prompt-patterns.md`.

## Progress surface

Decide how the user learns what is happening; the three mechanisms are not interchangeable:

1. **Progress-update thinking blocks.** Automatic, but empty unless `thinking.display` is `"updates"` or `"summarized"` [T]. Best for status lines.
2. **A send-to-user tool.** For content the user must read verbatim mid-run; declare it from the first request; needs an elicitation instruction [F5].
3. **The final message.** Written for a reader who saw none of the work: use the "Communicating clearly" block [P].

Common defect: a team wants (2), configures none of them, and adds prompt text asking for narration. Fix the surface first.

## Memory and multi-window work

Fable performs well when it can record lessons and reference them; a Markdown directory is enough [F5]. Rules: one lesson per file with a one-line summary; record confirmed approaches as well as corrections, with the reason; don't duplicate what the repo or chat history holds; update rather than duplicate; delete notes that turn out wrong [F5].

On Fable 5.2, memory is also where cautions pile up and get followed closely [P]. Give every rule in memory its scope and reason, prune stale ones, and treat a memory file other people can edit as untrusted: send its text in a `tool_result`, not in `system` [C].

Across context windows [BP]: use a different prompt for the first window to set up tests and scripts; keep test status in a structured file such as `tests.json` and state that removing or editing tests is unacceptable; create setup scripts such as `init.sh`; on a fresh window, start by calling `pwd` and reading the progress notes, `tests.json`, and the git log. Prefer compaction on demand or context editing over client-side cuts, which invalidate kept thinking [C]. Do not show the model a remaining-token countdown [F5].

## Self-verification

Put it on an interval, not at the end (Fable 5):

```text
Establish a method for checking your own work at an interval of [X] as you build. Run this every [X interval], verifying your work with subagents against the specification.
```

Separate fresh-context verifiers tend to outperform self-critique [F5]. Give a verifier the requirements, the diff, the tests, and codebase evidence, not the implementer's summary (`workload recommendation`). At `xhigh` and `max`, Fable 5.2 may start review subagents unprompted [P]: before adding this block at those levels, check whether it already does.

## Refactoring existing scaffolding

Skills and prompts written for prior models are often too prescriptive and can degrade output; Fable also updates skills as it learns from the task [F5]. Procedure:

1. Inventory every instruction source: system prompt, `CLAUDE.md`, skills, agent definitions, memory and notes, per-turn injections, tool descriptions.
2. For each instruction, name the behavior it corrects. If you cannot, it is a deletion candidate.
3. Remove candidates; rerun evals at the default effort.
4. Re-add only what a measured failure demands, in its smallest form.
5. Hunt specifically for: reasoning-in-reply requests (refusal risk), standing delegate lines, think-less lines, visible token budgets, hard style limits, absolute "never" rules, stop-at-first-error rules, anti-narration and anti-formatting lines, and aggressive tool language [P][P51].

## Computer use and machine administration

Fable 5.2 accepts computer use only through `computer_toolset_20260801` outside Amazon Bedrock [W]. `workload recommendation`: choose the most deterministic interface anyway (shell, APIs, and file tools for repeatable administration; computer use for GUI-only software or when the UI state is the evidence). Run computer use in an isolated browser, VM, or container; limit domains, accounts, and actions; treat screen content as untrusted; confirm before deleting data, changing permissions, installing downloaded code, or transmitting sensitive data. For remote administration, state the host, environment, authorized scope, rollback path, health check, and confirmation boundary.

## Vision work

On dense charts and complex images, Fable does its best work when it can crop, zoom, and verify: run it with a container holding the raw images and libraries such as PIL and OpenCV, or give it a crop tool alone [P51][F5]. The cookbook crop-tool recipe has a working definition.

## Autonomy and safety balance

The "Finishing work" block deliberately reduces stopping, and Anthropic says to keep your own confirmation step for risky or irreversible actions [P]. Reconcile them explicitly:

- name the few gated actions right after the completion block, scoped and with a reason, instead of a "never" rule;
- keep reversible work ungated, and list the routine steps that need no approval;
- require evidence for the specific state-changing command before it runs [F5];
- forbid destructive shortcuts around obstacles, including bypassing safety checks and discarding unfamiliar files that may be in-progress work.

Then test the boundary with a task where the tempting shortcut is destructive, and confirm the agent asks.
