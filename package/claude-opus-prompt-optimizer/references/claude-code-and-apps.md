# Opus 5.5 in Claude Code and Claude Apps

User-side playbook for people who drive Opus 5.5 through Claude Code, claude.ai, or the desktop and mobile apps rather than the API. Most of this lands in a `CLAUDE.md`, a project's instructions, a saved style, or a single message — not in request parameters.

Source: "Getting the most out of Opus 5.5 in Claude and Claude Code", claude.dev blog, 2026-09-22 (`https://claude.dev/blog/getting-the-most-out-of-opus-5-5/`), cross-checked against the Opus 5.5 prompting page on 2026-09-25. Slash commands and settings labels change often; confirm them in the product before quoting.

## What behaves differently

Three things, per the source: Opus 5.5 works longer on its own, reports plainly what it did, and thinks before every reply. Nearly every recommendation below follows from one of those.

## Asking

### Hand over the whole task with a finish line

Give the whole task in one message, name what "done" looks like, and say when to stop and ask. Then let it run. Opus 5.5 carries multi-part work further than Opus 5, and a concrete finish line is how it knows it has arrived.

```text
Migrate the payment endpoints from the old client to the new one.
Done means: every endpoint uses the new client, the old client is
deleted, and the test suite passes.
Stop and ask me only if a test fails for a reason you can't explain.
```

Good finish lines are observable: "the tests pass", "every endpoint is migrated", "the table has one row per service".

### Delete "think hard" lines

Remove "think carefully", "think step by step", "think hard" and their cousins from prompts, `CLAUDE.md`, project instructions, and saved styles. Opus 5.5 always thinks and decides how much. In Anthropic's chat testing, deleting such a line made replies start sooner with no clear quality loss. For a quick answer, say "Answer directly." To change depth in Claude Code, change effort.

### Add to a running task instead of restarting

Runs are longer, so a restart costs more. In Claude Code, type a follow-up and press Enter while Claude works ("Also keep the old endpoint names as aliases.").

### Name the design patterns you don't want

Without direction, Opus 5.5 falls back on a few default styles, and "avoid a generic look" mostly swaps one default for another. List concrete patterns, look at what it chose instead, and extend the list.

```text
Build a personal website with placeholder content.
Don't use a cream or off-white background, italic accent words in
headings, numbered "01 / 02 / 03" section labels, monospace labels, or
pill-shaped buttons.
```

This is a legitimate exception to "say what to do rather than what to avoid": the model's positive default is the problem, so the exclusion list is the specification.

## Steering a long run in Claude Code

### Say which stops you want, in CLAUDE.md

On long tasks Opus 5.5 keeps you posted, and sometimes stops to report instead of continuing: a summary naming the next step without taking it, an offer to continue, or a list of choices that don't block the work. It follows instructions that name these stops — and the ones you do want.

```markdown
When a step doesn't need my input, keep going. Put status notes in the
same message as your next action.
Stop and ask only when you can't continue without me, or before anything
destructive: deleting data, force-pushing, or changing anything outside
this repository.
```

If a run still ends with "Want me to continue?", reply "continue"; if it happens often, the rule above is the fix. Fewer stops means fewer natural checkpoints, so keep the destructive-action line and leave permission prompts on for destructive commands.

For pair programming, ask for the opposite — a one-line plan before starting and a short recap at the end. Opus 5.5 follows either.

The API-side equivalent for fully unattended agents is the longer standing instruction in `references/behavior-fixes.md` ("Unattended early stops").

### Ask for a subagent fan-out on big, splittable work

For an audit, migration, or codebase-wide review, ask it to split the work across subagents and check each one's evidence. Early testers ran multi-hour audits and migrations this way with little oversight.

```text
Audit every service in services/ for the retry bug in the linked issue.
Give each service to its own subagent. When a subagent reports back,
check its evidence before you accept it.
Finish with one table: service, affected yes or no, and the evidence.
```

This does not contradict the delegation damper for small tasks. It names the qualifying scenario (large, independent, parallelizable units). "Check its evidence before you accept it" is review of another agent's claims, not self-verification, and stays.

### Keep the task list in a file

A long run fills the context window and Claude Code summarizes older turns; a file survives that and shows progress at a glance. "Keep a checklist in TASKS.md. Tick each item when it's done, and add anything new you find." Read the file, not the scrollback.

## Checking the result

### Read "what it needs from you" first

Opus 5.5's updates and final summary say what it did, what it found, and what it needs from you. Read the blocking items first. To fix the format, put it in `CLAUDE.md`: "End every run with three headings: Blocked on me, Changed, Found."

### Run a review pass before a human does

One early tester reported Opus 5.5 at its lowest effort caught more bugs than Opus 5 at high effort, with fewer false alarms, and its PR descriptions are easier to review.

```text
Review the diff on this branch against main.
List only problems you'd block the merge for. For each one, give the
file and line, why it's wrong, and how to show it fails.
```

Note the filter. "Only problems you'd block the merge for" is a real acceptance criterion for a human reviewer, and the model will apply it literally. When the goal is recall — a findings database, a second-stage filter, a seeded-bug eval — ask for every issue at every severity and filter afterwards (see `references/behavior-fixes.md`, "Review under-reporting").

### Ask it to mark what it couldn't confirm

For research and analysis: "Mark anything you couldn't confirm, and say where you looked." Works in a Claude research report and in Claude Code; it makes gaps easy to find instead of buried.

## In Claude apps

First, check the model picker says Opus 5.5.

- **Attach the chart, diagram, screenshot, or slide** instead of retyping numbers, and ask a specific question ("Which of these services call the billing API directly?"). Opus 5.5 reads visuals more accurately than Opus 5 with no extra steps, including position-dependent meaning: arrow endpoints, diagram diffs, calendar start and end times.
- **Ask it to check a long document** for contradictions: "Check this deck for anything that contradicts itself: numbers, dates and names. Quote each problem and say where it is." It catches wrong weekdays in long threads and charts that disagree with the numbers.
- **Ask for the finished file**, not an outline: "Make this a spreadsheet I can share: one row per vendor, with columns for cost, contract end date and owner." Its spreadsheets and documents need less editing than Opus 5's.
- **In a long project, mark earlier answers as settled** if follow-ups feel slow. Opus 5.5 sometimes re-examines earlier answers while thinking about a short follow-up. Project instruction:

  ```text
  Once you have answered something, treat that answer as done. Focus on
  what I'm asking now, and don't go back over an earlier answer unless I
  ask about it or point out a problem with it.
  ```

  Leave it out of long-analysis projects, where a later step can expose an earlier mistake — it can make the model less likely to flag its own earlier error.

## When a message is flagged

Opus 5.5 launched with Fable-level bio and cyber safeguards. In apps and Claude Code, most flagged messages move to an older model and work continues there. Finding vulnerabilities in source code is allowed; everyday health and education questions should work. Legitimate work is sometimes flagged, and the check covers the whole conversation — files and search results included — so a flag can come from earlier content.

| Surface | What you see | What to do |
| --- | --- | --- |
| Claude apps | A notice starting "Switched to" plus an older model's name; the chat stays on it | Pick Opus 5.5 in the model picker; start a new chat if the flagged content is still in context. To be asked first: Settings → Capabilities → turn off "Switch models when a message is flagged" (you get a "paused" card instead). |
| Claude Code | A notice naming the older model; the session continues on it | `/model` to switch back; Esc twice to edit the last message and retry; `/config` to change "Switch models when a message is flagged"; `/feedback` if the flag was wrong. |

**Don't ask it to show its reasoning in the reply.** Requests to reproduce internal reasoning are a flag category (`reasoning_extraction`). Ask for what you actually need: "Explain why you chose this approach in three sentences."

## Speed

In Claude Code, fast mode (`/fast`) suits back-and-forth work where you read each reply before sending the next. Same model, text arrives sooner. Research preview; needs extra usage turned on and costs more per token.

## Checklist

Asking
- The task says what "done" looks like.
- No "think hard" lines in prompts or saved instructions.
- Design requests list the styles to leave out.
- Charts and screenshots are attached, not retyped.

Long runs in Claude Code
- `CLAUDE.md` says when to stop, when to keep going, and to stop before anything destructive.
- Permission prompts are still on for destructive commands.
- Large audits and migrations are split across subagents.
- The task list lives in a file.

Checking
- The "needs from you" part of the report is read first.
- A review pass runs before a person reviews.
- Research answers mark what couldn't be confirmed.

Flags
- You know how to switch back: model picker or `/model`.
- "Switch models when a message is flagged" is set the way you want.
