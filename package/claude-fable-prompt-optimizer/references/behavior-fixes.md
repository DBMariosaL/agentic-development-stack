# Behavior Fixes

Symptom-driven index. Find the row that matches what the user observes, apply the smallest fix, and name the layer that owns it. Instruction blocks are Anthropic's documented text, each tagged with the model it was measured on. A Fable 5.1 or Fable 5 block was not re-measured on Fable 5.2: test it before carrying it over. Read on 2026-11-16.

Sources: [P] Prompting Fable 5.2 `https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-fable-5-2` · [P51] Prompting Fable 5.1 `https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-fable-5-1` · [F5] Prompting Fable 5 `https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-fable-5` · [BP] Prompting best practices `https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices` · [W] What's new in Fable 5.2 · [M] Fable 5.2 migration guide · [E] Effort · [T] Thinking · [X] Prefix checks · [C] Change tools or instructions · [R] Refusals and fallback · [SDK] Agent SDK subagents (full URLs in `references/official-sources.md`).

## Fable 5.2 index

| Symptom | Layer that owns the fix | Section |
| --- | --- | --- |
| Unsure which effort; easy requests slow or costly | API parameter | [Effort and think-less lines](#effort-and-think-less-lines) |
| "Answer directly" line no longer cuts thinking | Prompt (deletion) plus effort | [Effort and think-less lines](#effort-and-think-less-lines) |
| `stop_reason: "max_tokens"` after a thinking block, no text | API parameter | [Small max_tokens](#small-max_tokens) |
| Turn ends listing what's left, offering to continue, or at a timeout | Prompt | [Early stops](#early-stops) |
| Asks for approvals it doesn't need; holds routine work | Prompt and memory files (deletion) | [Caution that piles up](#caution-that-piles-up) |
| Copies existing code instead of consolidating; reports problems and leaves them | Prompt | [Code ownership](#code-ownership) |
| Long agentic turns look silent; first tool call unannounced | Harness, then prompt | [Silent agent](#silent-agent) |
| More subagents than the task needs; subagent cost dominates | Tool description, then prompt (deletion) | [Over-delegation](#over-delegation) |
| Prompt or harness carried over from Fable 5.1 or Opus 5.5 | Prompt and harness | [Carried-over instructions](#carried-over-instructions) |
| Final reports or handoffs hard to follow; prose choppy | Prompt | [Reports](#reports) |
| `stop_reason: "refusal"` | Prompt (deletion), fallback, program access | [Refusals](#refusals) |
| 400 `bound to a different conversation` | Message assembly | [History edits](#history-edits) |
| Reasoning lost or cost spike after a router or fallback switch | Harness | [Model switches](#model-switches) |
| 400 on `computer_20251124` or on the advisor's model | API parameter | [Tool 400s](#tool-400s) |

## Fable 5.1 and Fable 5 index

For users on those models, or for a Fable 5.2 symptom the 5.2 page does not cover.

| Symptom | Layer | Section | Measured on |
| --- | --- | --- | --- |
| One tool call per turn in an agent loop | Turn-scoped prompt | [Serial tool calls](#serial-tool-calls) | 5.1 |
| Dense prose, long sentences | Prompt | [Writing density](#writing-density) | 5.1 |
| Chat replies under-formatted | Prompt (deletion) | [Formatting](#formatting) | 5.1 |
| Summaries reproduce source wording unmarked | Prompt example | [Quoting sources](#quoting-sources) | 5.1 |
| Unrequested fixes, extra committed tests | Prompt | [Scope creep](#scope-creep) | 5.1 |
| Answers from memory at `low` | Effort or prompt | [Search triggering](#search-triggering) | 5.1 |
| Benign coding requests refused | Phrasing, tool output | [Safeguard false positives](#safeguard-false-positives) | 5.1 |
| Whole files rewritten for small edits | Prompt | [Whole-file rewrites](#whole-file-rewrites) | 5.1 |
| Long deliverables drafted twice at `xhigh`/`max` | Effort, `max_tokens`, prompt | [Long outputs](#long-outputs) | 5.1 |
| Runs commands to "show" output the UI hides | Turn-scoped prompt | [Hidden tool output](#hidden-tool-output) | 5.1 |
| Lead idles while subagents run | Tool semantics | [Subagent blocking](#subagent-blocking) | 5.1, 5 |
| Fabricated status reports | Prompt | [Progress claims](#progress-claims) | 5 |
| Suggests a new session over context limits | Harness, then prompt | [Context anxiety](#context-anxiety) | 5 |
| Unrequested emails, backups, state changes | Prompt | [Boundaries](#boundaries) | 5 |
| Overplanning; tidying at high effort | Prompt | [Overplanning and gold-plating](#overplanning-and-gold-plating) | 5 |
| Deliverable lost inside a summarized turn | Tool inventory | [Send-to-user](#send-to-user) | 5 |
| Speculates about code; hardcodes to tests; suggests instead of acting | Prompt | [Cross-model blocks](#cross-model-blocks) | cross-model |

# Fable 5.2 sections

## Effort and think-less lines

Start at `high` (API default), then evaluate `medium` and `xhigh` [P]. At `high` and above the model thinks before almost every reply, including a greeting. "Answer directly without deliberating" did not stop Fable 5.2 from thinking at `medium` and above, although Fable 5.1 usually followed it: delete such lines and lower effort for those turns [P][W]. Effort barely changes reply length; prompt for length [P]. Mix levels per phase with per-message effort (`references/fable-configuration.md`).

## Small max_tokens

Thinking counts toward `max_tokens`. A small limit that fit on Fable 5.1 because a prompt line suppressed thinking can now end with `stop_reason: "max_tokens"` after a `thinking` block and before any text [M]. Raise `max_tokens` or lower effort; at `high` and above set it large [E].

## Early stops

On long multistep tasks Fable 5.2 sometimes ends the turn listing what remains, offering to continue, or stopping at an ordinary obstacle; more often at `low` and `medium` [P]. System prompt (Fable 5.2):

```text
# Finishing work
Please avoid stopping while you still owe work the user asked for. Be persistent and do not stop unless needed.

While status notes are welcome, as is clarifying with the user on open decisions, carry on with work that does not depend on the user's answer without unnecessary stops.

If you notice yourself inviting the user to redirect you or offering to wait, instead proceed on the next part of the task. You may meet ordinary obstacles like errors, timeouts, locked files, empty results or failing tools. Diagnose them first, and when they are not real blockers, work through them with the access you have (wait and retry, fix the request, use another tool or source) rather than stopping unnecessarily.

If someone clearly decided something is a hard blocker, such as a file marked not to be touched, access that was intentionally withheld, or a safety guardrail, leave it alone, say plainly what you found, and look for another safe way to finish the task. Stopping before the task is complete is very rarely merited, as in when the task can't move forward without user input, or where the blocker is deliberate and should not be worked past. This does not override the need for confirmation on risky or destructive actions.
```

Measured at `medium` on replayed sessions: about half as many sessions ended with continuable unfinished work; it removed most permission-asking and offer-to-continue endings but not list-what-remains endings; output tokens rose about 30% [P]. Keep your own confirmation step for risky actions.

Approvals [P]: reply with the exact approval ("Yes, run the migration on the staging database"), not "continue". Make approval rules specific: a rule listing "sending messages to people outside this conversation" held back about half of routine requests to colleagues and other teams.

## Caution that piles up

Memory, notes, and instruction files accumulate cautions, some written by the model itself; Fable 5.2 follows them closely, mostly visible when several agents work together [P]. Remove notes whose reason is gone ("never retry"); name the routine steps that need no approval instead of "act more freely"; narrow stop conditions such as "stop and review at the first error"; write "ask for approval before deleting files" instead of "never delete files", because "never" is read as absolute [P]. If a system is already stuck, restart it with memory and notes trimmed [P].

## Code ownership

With nothing said about ownership, or with the code presented as someone else's, Fable 5.2 adds to the existing structure even when that duplicates code, and reports nearby problems instead of fixing them [P][W]. To have it improve structure (Fable 5.2):

```text
You are the owner and long-term maintainer of this codebase, and its design is up to you.
```

Effect: consolidation of duplicated code went from under 10% to about 75% of runs; output tokens rose 70 to 80%; unrequested changes appeared (tests, docs, sometimes changed feature behavior); the closing summary often omitted small changes [P]. Leave it out when the user owns the code and wants minimal change. A scope-limiting rule does not cancel it: with "No drive-by refactors, renames or cleanups" earlier in the same prompt, it still consolidated in more than half of runs [P]. In a delegation brief, decide this sentence per subagent: include it for an author who owns a module, omit it for a narrow patch.

## Silent agent

Check in this order [P]:

1. **The client receives updates.** Progress updates come back as `thinking` blocks, empty at the default `display: "omitted"`. Set `display: "updates"` (beta `thinking-display-updates-2026-08-18`) or `"summarized"` and render non-empty blocks.
2. **Harness reminder.** With `"updates"` or `"summarized"` set, count consecutive tool-calling steps with nothing for the user to read; after several, append as a turn-scoped system message (`clear_at: "next_user_message"`, beta `mid-conversation-system-clear-at-2026-08-21`) and leave it in `messages` (Fable 5.2):

```text
The user hasn't heard from you in a while: say in a few words what you're doing, then continue.
```

Roughly halved the longest silent stretch without a noticeable increase in tokens or time.

3. **Opening line and recap**, where a human is in the loop (Fable 5.2; about 20% more output tokens):

```text
Before you start, say in a line what you're about to do; brief updates while you work help the user follow along. Close with a short recap that stands on its own (what you found, what you did, and what's next), so a reader who only sees the last message has the full picture.
```

4. **No mid-conversation system messages available**: add `Every few tool calls, give the user a one-line update on where things stand.` [P]

Expect several tool calls between updates even with all of these. Anthropic recommends Fable 5.2 for work where nobody needs frequent updates [P]. Remove anti-narration lines ("hold all findings for the final response") before adding any of this [P51].

## Over-delegation

Delegation depends on the harness: rare with a minimal subagent tool, ready when prompts invite it; at `xhigh` and `max` it also starts subagents to review its own work [P]. Change the subagent tool description only if it starts more subagents than the task needs, mainly where subagents are a large share of token use. First review delegate lines in system prompts, skills, and agent files [P]. The new description should state what a subagent adds to session cost, when delegation is worth it and when not, and how to brief a subagent; a longer cost-focused description roughly halved subagent count at `high` [P]. Template in `references/prompt-patterns.md`; the full orchestration contract is in `references/orchestration-and-handoffs.md`.

## Carried-over instructions

Review before migrating [P]:

| Carried-over item | On Fable 5.2 | Action |
| --- | --- | --- |
| Standing "delegate" lines | Raise delegation and cost | Remove if testing shows over-delegation |
| Token budget shown to the model | Its size changes spend; removing a large one cut cost at equal performance (`high`, `xhigh`) | Test without it; the API task-budget beta was not covered |
| Harness edits to earlier turns | 400 on the prefix check | Append-only; see [History edits](#history-edits) |
| Opus 5.5 "treat that answer as done" lines | Less thinking on follow-ups, far less self-correction | Leave out where the model should re-examine earlier answers |
| "Answer directly without deliberating" | No effect at `medium` and above | Remove; lower effort |
| Hard style rules ("20 words or fewer") | Followed closely; choppy prose | Remove before adding the report block |
| Accumulated rules, notes, memories | Followed closely | Delete stale ones; rewrite absolutes with scope and reason |

## Reports

Testers rated Fable 5.2's writing above Fable 5.1's and similar in clarity to Opus 5.5's; final reports still need to stand alone for readers who saw none of the work [P]. For final reports or handoffs (Fable 5.2):

```text
# Communicating clearly
Write for an intelligent but low-context reader. The person reading has not seen your tool calls, your reasoning or the files you opened, and may be switching in from other work. Messages should generally be self-contained: the reader should understand what you mean without having to dig for other context. Put the key points in the first few sentences. Practice progressive disclosure in your sentence order, and do not use undefined references and ideas in line 1 that won't make sense until the reader reaches line 12.

Use plain words, and write in clear, understandable full sentences. Do not use a term or abbreviation that you made up during the work. Say what the thing is in a way any reader would understand. Write mostly in the style of ASD-STE100 Simplified Technical English: short sentences, one idea per sentence, active voice, and consistently using the same word for the same thing. Use a paragraph of flowing prose where ideas connect, and keep bullets for lists of separate items. Leave out unnecessary details unless the reader asks and practice concision, but do ensure that your messages have the key context. Aim to make your user-facing text as human-readable and clear as possible.
```

It made reports less dense with fewer semicolons, and shortened sentences on workflow tasks [P]. Add length or required-detail instructions per product. For a report a Fable parent reads, combine it with the contract in `references/orchestration-and-handoffs.md`.

## Refusals

Categories: `cyber`, `bio`, `frontier_llm`, `reasoning_extraction`, `general_harms`, `null` [P][R]. Remove prompt, skill, and tool-description text that asks for reasoning in the reply, including a `<thinking>` or scratchpad section, a `reasoning` field in JSON or tool input, or "private notes"; read `display: "summarized"` thinking blocks instead. A short explanation, the evidence behind a result, or a summary of actions is still fine [R]. `reasoning_extraction` has no fallback. For blocked legitimate cyber or life-sciences work, see the verification programs; Mythos 5.2 is the verified-access counterpart [P]. Fallback configuration is in `references/fable-configuration.md`.

## History edits

Fable 5.2 returns 400 whenever a request fails the prefix check, where Fable 5.1 might not [W][X]. Append assistant turns exactly; keep `system` and `tools` fixed; put every update in a new message. Change patterns are in `references/fable-configuration.md`. To find edits: run with `thinking-binding-controls-2026-08-01` and `"drop_block"` and log `input_transformations` [M]. If you use the MCP connector without pinning the tool list, test against `claude-fable-5-2` specifically [M].

## Model switches

Only Mythos 5.2 reads Fable 5.2 thinking blocks. A switch to Opus 5.5, Fable 5.1, or a fallback model drops the reasoning for those turns; the first turn after costs more [M]. Keep routers and fallbacks from bouncing conversations off Fable 5.2 casually.

## Tool 400s

`computer_20251124` returns 400 outside Amazon Bedrock: declare `computer_toolset_20260801`. A Fable 5.2 executor needs a Fable 5.2 or Mythos 5.2 advisor; change it in new conversations, since it edits `tools` [W].

# Fable 5.1 and Fable 5 sections

## Serial tool calls

Fable 5.1 may issue one call per turn in coding and computer-use loops where independent reads are implied [P51]. Append after each round of tool results as a new turn-scoped system message, leaving earlier copies in place (Fable 5.1):

```text
First privately list what you need next; then request every item that doesn't depend on another's result in this one response.
```

Without the beta, put it in a text block after the `tool_result` blocks. The system-prompt version is `<use_parallel_tool_calls>` on [BP].

## Writing density

Fable 5.1 prose can run denser than Fable 5's. In a user message (preferred) or the system prompt, the documented short version (Fable 5.1): `Please remove all mannered prose.` The full mannered-prose definition is on [P51] under "Writing density". On Fable 5.2, start with the Reports block instead.

## Formatting

Fable 5.1 uses bold, headers, and lists less than earlier models; delete anti-formatting rules and replace them with (Fable 5.1):

```text
Use lists and bullet points when asked to, or when the content is multifaceted enough that they help with clarity. If the person explicitly requests minimal formatting, always format your responses without bullet points, headers, lists, or bold emphasis, as requested. In conversational, personal, or emotional exchanges, keep to plain prose.
```

Do not carry `<avoid_excessive_markdown_and_bullet_points>` from [BP] onto Fable.

## Quoting sources

Fable 5.1 reproduces source passages unmarked more than Fable 5. Fix: one complete example (request, response, rationale) in the system prompt; the documented example is on [P51] under "Quoting retrieved sources". Replace its `[web_search: ...]` lines with your tool name.

## Scope creep

Measured on Fable 5.1: unrequested additions and committed test code dropped substantially with no change in task success (Fable 5.1):

```text
If, while working or testing, you find a pre-existing bug, a performance concern, or behavior the task doesn't mention, don't fix, optimize or extend it in this change unless the requested behavior cannot work without it; report it as a follow-up in your summary. Where the task is ambiguous, implement the reading its wording and the surrounding code most directly support, state that assumption in your summary, and don't build for the other readings as well. Verify your work however you like; scratch scripts and quick checks need not be kept. Commit tests only where the task asks for them or this repository already keeps tests for this kind of change, sized like the neighboring test files — roughly one focused test per stated behavior — and don't turn scratch checks into additional permanent test files. This is about extras only: implement every behavior the task asks for, completely.
```

On Fable 5.2 the larger lever is the ownership sentence: leave it out for narrow changes, because scope rules do not cancel it [P]. Fable 5.1 users also have the "Delivering work" block and the autonomous-operation block on [P51] under "Finish the whole task"; on Fable 5.2 use [Early stops](#early-stops).

## Search triggering

At `low`, Fable 5.1 searches less and answers from memory more. Raise effort for the affected turns, or add (Fable 5.1):

```text
When a query centers on a name you do not confidently recognize, or recognize from a fast-moving area like AI models and developer tools where the landscape shifts within months, the name itself is the thing to verify: search before answering, and include the name as the user wrote it in at least one query alongside any reformulations. This holds even when you have some background on it — partial background is exactly what makes an out-of-date answer sound authoritative, so familiarity is not a reason to skip the search.
```

## Safeguard false positives

Documented for Fable 5.1 [P51]: ask "Are there any bugs in this program?" rather than "Does this program compile without errors?"; give context or documentation for lesser-known languages; remove base64 from tool output. Not re-stated for Fable 5.2: `requires verification`, though the launch post reports fewer unnecessary cyber and bio blocks on 5.2.

## Whole-file rewrites

Append to the system prompt or first user message (Fable 5.1):

```text
The number of tokens used to edit files is best minimized, all else being equal. Therefore, when it will not affect the end result, try to surgically edit a file rather than rewrite the entire thing.
```

## Long outputs

At `xhigh` and `max`, Fable 5.1 can draft a long deliverable in thinking and again as the reply. Run such requests at `high`; otherwise size `max_tokens` for thinking plus reply and append the single-limit note from [P51] "Leave room for long outputs at xhigh and max effort".

## Hidden tool output

If your UI hides tool output, follow that output with a turn-scoped system message (Fable 5.1):

```text
Only you see that command's output — the user's terminal shows at most a few lines of it. If the user needs to read any of it, put it in your reply.
```

## Subagent blocking

Do not force the lead to wait on each subagent: on coding tasks, continuing while subagents run lowered time to completion at similar quality and cost (Fable 5.1). The launch tool returns immediately, results arrive in a later `user` message, a separate tool waits [P51]. Claude Code and the Agent SDK already start subagents in the background by default and deliver the report in a later turn [SDK]. Prompt counterpart (Fable 5): `Delegate independent subtasks to subagents and keep working while they run. Intervene if a subagent goes off track or is missing relevant context.` On Fable 5.2, do not add it to a harness that already invites delegation [P].

## Progress claims

Nearly eliminated fabricated status reports in Anthropic's testing (Fable 5):

```text
Before reporting progress, audit each claim against a tool result from this session. Only report work you can point to evidence for; if something is not yet verified, say so explicitly. Report outcomes faithfully: if tests fail, say so with the output; if a step was skipped, say that; when something is done and verified, state it plainly without hedging.
```

## Context anxiety

Most often triggered by a remaining-token countdown shown to the model; stop surfacing it. If the harness must (Fable 5): `You have ample context remaining. Do not stop, summarize, or suggest a new session on account of context limits. Continue the work.` On Fable 5.2, a visible token budget also changes spend [P].

## Boundaries

For unrequested actions such as drafting an email or creating git-branch backups (Fable 5):

```text
When the user is describing a problem, asking a question, or thinking out loud rather than requesting a change, the deliverable is your assessment. Report your findings and stop. Don't apply a fix until they ask for one. Before running a command that changes system state (restarts, deletes, config edits), check that the evidence actually supports that specific action. A signal that pattern-matches to a known failure may have a different cause.
```

## Overplanning and gold-plating

Overplanning on ambiguous tasks (Fable 5):

```text
When you have enough information to act, act. Do not re-derive facts already established in the conversation, re-litigate a decision the user has already made, or narrate options you will not pursue in user-facing messages. If you are weighing a choice, give a recommendation, not an exhaustive survey. This does not apply to thinking blocks.
```

Unrequested tidying at higher effort: the "Don't add features, refactor, or introduce abstractions beyond what the task requires" block on [F5] under "Consider all effort levels". Brevity: the "Lead with the outcome" block on [F5] under "Strong instruction following".

## Send-to-user

For content the user must see verbatim mid-run, define a `send_to_user` tool (input `message`; render it; return an acknowledgement) from the first request, since adding a tool later edits `tools` [F5][C]. Without an instruction Fable rarely calls it (Fable 5):

```text
Between tool calls, when you have content the user must read verbatim (a partial deliverable, a direct answer to their question), call the send_to_user tool with that content. Use send_to_user only for user-facing content, not for narration or reasoning.
```

## Cross-model blocks

On [BP]: `<investigate_before_answering>` against speculating about unopened code; the "Please write a high-quality, general-purpose solution" block against hardcoding to tests (pair it with a rule that tests are not removed or edited); `<default_to_action>` or `<do_not_act_before_instructions>` to shift between acting and suggesting (never both). Because forced tool use returns 400, name the tool and its condition in the prompt to make the model call it.
