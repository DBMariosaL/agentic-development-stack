# Behavior Fixes

Symptom-driven index. Find the row that matches what the user actually observes, apply the smallest fix, and note which layer owns it. Instruction blocks below are Anthropic's documented text; each is marked with the model it was measured on. Re-verify before presenting as current, and re-test a Fable 5 block on Fable 5.1.

Verified against the official prompting pages on 2026-09-03.

## Index

| Symptom | Layer that owns the fix | Section |
| --- | --- | --- |
| Unsure which effort to run; latency or cost too high | API parameter | [Effort](#effort) |
| Agent goes silent for minutes; final message covers only the last step | Harness first, then prompt | [Silent agent](#silent-agent) |
| One tool call per turn in a coding or computer-use loop | Turn-scoped prompt | [Serial tool calls](#serial-tool-calls) |
| 400 `bound to a different conversation`; cache constantly cold | Message assembly | [History edits](#history-edits) |
| Prose is dense, long sentences, few paragraph breaks | Prompt | [Writing density](#writing-density) |
| Chat replies under-formatted for the content | Prompt (usually a deletion) | [Formatting](#formatting) |
| Summaries reproduce source wording unmarked | Prompt example | [Quoting sources](#quoting-sources) |
| Turn ends on "Next, I'll..."; asks permission for requested work | Prompt | [Early stopping](#early-stopping) |
| Client compaction summaries lose constraints and decisions | Prompt (summarizer) | [Compaction](#compaction) |
| Unrequested fixes, refactors, extra committed tests | Prompt | [Scope creep](#scope-creep) |
| Answers from memory instead of searching | API parameter or prompt | [Search triggering](#search-triggering) |
| Benign coding requests return `stop_reason: "refusal"` | Prompt phrasing and tool output | [Safeguard false positives](#safeguard-false-positives) |
| Whole files rewritten for small changes | Prompt | [Whole-file rewrites](#whole-file-rewrites) |
| Long deliverables hit `max_tokens` or take very long at high effort | API parameter and prompt | [Long outputs](#long-outputs) |
| Lead agent idles while subagents run | Tool semantics | [Subagent blocking](#subagent-blocking) |
| Chart and dense-image answers miss detail | Tool inventory | [Vision detail](#vision-detail) |
| Fabricated status reports on long runs | Prompt | [Progress claims](#progress-claims) |
| Model suggests a new session over context limits | Harness first, then prompt | [Context anxiety](#context-anxiety) |
| Unrequested emails, branches, backups, state changes | Prompt | [Unrequested actions](#unrequested-actions) |
| Overplanning on ambiguous tasks | Prompt | [Overplanning](#overplanning) |
| Unrequested tidying and refactoring at high effort | Prompt | [Gold-plating](#gold-plating) |
| Verbose, over-structured, root-cause-essay responses | Prompt | [Verbosity](#verbosity) |
| Final summary unreadable after a long agentic run | Prompt | [Readability](#readability) |
| Deliverable content lost inside a summarized turn | Tool inventory | [Send-to-user](#send-to-user) |
| Only suggests changes instead of making them | Prompt | [Suggest vs act](#suggest-vs-act) |
| Speculates about code it never opened | Prompt | [Grounding](#grounding) |
| Hardcodes to make tests pass | Prompt | [Test gaming](#test-gaming) |

## Effort

`high` is the default and the recommended starting point. Sweep `low`, `medium`, `xhigh`, and `max` against your own evals. Effort level names do not correspond to the same amount of thinking across models, so re-run the sweep after any model change.

On Fable 5.1, gains over Fable 5 appear at every level and are largest at the higher settings. `medium` roughly matches Fable 5 at lower cost. `low` is often competitive with Opus and Sonnet models on cost per task while scoring higher, so include it wherever you would otherwise run a smaller model at higher effort. Two behaviors are effort-specific: reduced search triggering at `low`, and long pre-writing thinking at `xhigh` and `max`.

## Silent agent

Fable 5.1 writes fewer user-facing updates during long tool-calling turns than Fable 5, more so at higher effort and in longer chains.

Check three things in order:

1. **Is the client receiving updates at all?** Progress notes come back as `thinking` blocks immediately before each tool call, and those are empty under the default `thinking.display` of `"omitted"`. Set `display: "updates"` (beta header `thinking-display-updates-2026-08-18`) and render every non-empty `thinking` block as a status line, or use `"summarized"` to get them alongside summarized reasoning.
2. **Does the prompt suppress narration?** Remove lines such as "hold all findings for the final response", written for earlier models that over-narrated.
3. **Only then add prompt text.** For pair programming and other human-in-the-loop work (Fable 5.1):

```text
Before you start, say in a line what you're about to do; brief updates while you work help the user follow along. Close with a short recap that stands on its own — what you found, what you did, and what's next — so a reader who only sees the last message has the full picture.
```

If your product collapses or hides tool output, tell the model, or it will run commands to "show" output the UI never displays. Deliver as a turn-scoped system message (Fable 5.1):

```text
Only you see that command's output — the user's terminal shows at most a few lines of it. If the user needs to read any of it, put it in your reply.
```

## Serial tool calls

Fable 5.1 issues parallel calls as expected when a request names several things to fetch. It may go one call per turn in coding and computer-use loops where the next independent reads are only implied. Answer quality is unaffected; the cost is extra turns, round trips, and wall-clock time.

Append this after each round of tool results, as a fresh turn-scoped system message (Fable 5.1):

```text
First privately list what you need next; then request every item that doesn't depend on another's result in this one response.
```

Placement matters. Add a new copy each turn as a `role: "system"` message with `clear_at: "next_user_message"` (beta header `mid-conversation-system-clear-at-2026-08-21`) and leave earlier copies byte-for-byte in place; the API stops rendering them and they cost no input tokens. Deleting or rewriting them is a history edit. Without the beta, put the sentence in a text block after the `tool_result` blocks in the same user message.

The cross-model version of this instruction, for prompts that need it in the system prompt rather than per turn, is the `<use_parallel_tool_calls>` block on the best-practices page.

## History edits

Append each assistant turn exactly as the API returned it, thinking blocks included, and never edit earlier turns between requests. On Fable 5.1, thinking blocks are valid only in the exact conversation that produced them; replaying a block after its prefix changed returns a 400 whose message says `The block is bound to a different conversation`, or drops the block with `thinking.block_binding.prefix_mismatch_behavior: "drop_block"` (beta header `thinking-binding-controls-2026-08-01`). Enforced for accounts created on or after 2026-08-31; expected to become universal.

The edits that trip the check are the same ones that restart the prompt cache:

- injecting a per-turn reminder and removing it next request — use a turn-scoped system message instead;
- summarizing older turns in place — let server-side compaction or context editing trim;
- rebuilding `system` or `tools` mid-session — use a mid-conversation system message or mid-conversation tool change;
- an image or document URL that serves different bytes on a later request.

These stay safe: removing a leading run of thinking blocks oldest-first, server-side compaction and context editing, moving `cache_control` markers, and changing `effort` between requests.

If you compact on the client, the simplest safe shape is to replace the whole history with one summary message plus the new user turn and replay no thinking blocks at all. Because cache reads are cheaper on Fable 5.1, compacting early to save cost may no longer be the right tradeoff; test later compaction points.

To find edits your harness already makes, run a session with `prefix_mismatch_behavior: "drop_block"` and log `input_transformations`, or capture the raw requests over a few turns and confirm consecutive requests are byte-identical up to the appended turns.

## Writing density

Fable 5.1 uses fewer stock phrases and less unexplained jargon than earlier models, but its prose can run denser than Fable 5's: longer sentences, fewer paragraph breaks. Defining the anti-pattern works better than asking for brevity. Put it in a user message (preferred) or the system prompt (Fable 5.1):

```text
Mannered prose substitutes metaphor and flourish for direct statement. Instead of "a parameter worth varying," the mannered writer produces "a dial worth turning." Instead of "this point still matters," they write "this point earns its keep." The phrases exist to display the writer, not to convey the idea, and readers can tell. That is why mannered prose irritates: it makes the reader work harder so the writer can perform. It is also imprecise. Metaphors drag in connotations the writer did not choose and cannot control. The fix is to say what you mean. When a literal phrase is available, use it.
```

The short version usually also works: `Please remove all mannered prose.`

## Formatting

Fable 5.1 uses bold, headers, and lists less than earlier Claude models. Anti-formatting rules written for models that over-formatted now suppress structure the content needs. First delete them. Replace with a rule that says when formatting is appropriate (Fable 5.1):

```text
Use lists and bullet points when asked to, or when the content is multifaceted enough that they help with clarity. If the person explicitly requests minimal formatting, always format your responses without bullet points, headers, lists, or bold emphasis, as requested. In conversational, personal, or emotional exchanges, keep to plain prose.
```

The long `<avoid_excessive_markdown_and_bullet_points>` block from the best-practices page is written for models that over-format. Do not carry it onto Fable 5.1.

## Quoting sources

When summarizing documents, Fable 5.1 is more likely than Fable 5 to reproduce source passages without marking them as quotations. The documented fix is one complete example in the system prompt: the request, the response, and a rationale explaining why the response is correct (Fable 5.1).

```text
<example>
<user>look up how the Riverton Ledger and the Coast Dispatch each covered the Harbor Bridge closure and compare their reporting</user>
<response>
[web_search: Harbor Bridge closure Riverton Ledger]
[web_search: Harbor Bridge closure Coast Dispatch]
Both outlets agree on the basics: the bridge closed on March 3 after inspectors found cracked welds, and the state expects repairs to take about eight months. Where they differ is emphasis. The Ledger treats it as a local-economy story. The Dispatch frames it as a funding failure; its editorial calls the closure "entirely foreseeable." Read together, the Ledger explains who is affected now and the Dispatch explains how it came to this — neither account alone gives the whole picture.
</response>
<rationale>CORRECT: The response is organized around where the two outlets agree and differ, not as a walk through either article. Each outlet's reporting is conveyed in one or two sentences of the assistant's own indirect speech. One short marked phrase from one source; every other claim is reworded. The response is still specific and complete.</rationale>
</example>
```

Replace the `[web_search: ...]` lines with your own tool name so the model reads them as templated tool output rather than literal text to emit.

## Early stopping

Fable executes very long tasks without much methodology guidance when the goal is clear, but on complex asynchronous work it sometimes describes what it would do next instead of doing it, or asks permission for a step the original request already covered.

Two system prompt additions together mitigate this; apply both. If prompt length is constrained, the first carries most of the effect (Fable 5.1):

```text
You are operating autonomously. The user is not watching in real time and cannot answer questions mid-task, so asking 'Want me to…?' or 'Shall I…?' will block the work. For reversible actions that follow from the original request, proceed without asking. Stop only for destructive actions or genuine scope changes the user must decide. Offering follow-ups after the task is done is fine; asking permission before doing the work is not.

Exception: when the user is describing a problem, asking a question, or thinking out loud rather than requesting a change, the deliverable is your assessment. Report your findings and stop. Don't apply a fix until they ask for one.

Before ending your turn, check your last paragraph. If it is a plan, an analysis, a question, a list of next steps, or a promise about work you have not done ('I'll…', 'let me know when…'), do that work now with tool calls. That includes retrying after errors and gathering missing information yourself. Do not stop because the context or session is long. End your turn only when the task is complete or you are blocked on input only the user can provide.

Before running a command that changes system state (such as restarts, deletes, or config edits), check that the evidence actually supports that specific action. A signal that pattern-matches to a known failure may have a different cause.
```

Keep the opening sentence as written; it carries much of the effect. If your product needs specific confirmations, add a sentence listing them right after it. This block can also make the model less likely to ask about genuinely ambiguous requests, so check that tradeoff on your own tasks.

The second defines the request as the scope of the deliverable (Fable 5.1):

```text
# Delivering work
The user's request — or the plan they approved — sets the scope, and the scope is the deliverable: don't quietly narrow, widen, or swap it. Read ambiguity the way a careful colleague would: make routine judgment calls yourself, and check in only when different readings would lead to materially different work. If you see a real problem with the task as specified, say so in a sentence or two and keep building under stated assumptions; if the user hears the concern and reaffirms, that is their decision, so deliver the full request.

If a question comes up partway, first do everything that doesn't depend on the answer; then state the assumption you made, or — when going ahead on a wrong guess would be unsafe or would make the work useless — put the question at the end of a turn that also delivers that progress. If one part turns out to be blocked, complete every other part in full and say exactly what you left out and why — the whole task is the deliverable, and scaling it down is the user's call, not yours. A step you have decided on is something to run, not to announce: describing the next step and ending the turn leaves it undone until the user replies.

Keep changes to what the request needs. Something else you notice worth doing — cleanup or documentation the task didn't call for, a change to a file the task didn't require — is a suggestion to make at the end, not a change to make; actions clearly beyond what the ask implies, and risky or destructive ones, still need the user's go-ahead.
```

The checkpoint counterpart, for defining where pausing is genuinely appropriate (Fable 5):

```text
Pause for the user only when the work genuinely requires them: a destructive or irreversible action, a real scope change, or input that only they can provide. If you hit one of these, ask and end the turn, rather than ending on a promise.
```

## Compaction

Server-side compaction already preserves the right things. If you compact on the client, Fable 5.1 responds well to being told explicitly what the summary must retain:

```text
Summarize the transcript inside <summary></summary> tags. Include relevant information in the summary such that this conversation will be continued by a new context window without needing to redo work or be reprovided with relevant constraints or context. Be sure to preserve: (1) any difficulties or problems that came up, and how they were handled or resolved; (2) any possibilities, options, or approaches that were raised, tried, or set aside, and why; (3) anything that was asked for, decided, agreed, ruled out, or established as a preference, constraint, or boundary — stated exactly; (4) exactly where things stand now — what has been covered, settled, or completed so far; (5) anything still open, unresolved, promised, or expected to happen next; (6) specific details that would be hard to reconstruct — names, numbers, dates, exact wording, links or references — kept exactly. Be complete on these even at the cost of length; keep everything else concise. Weight the two voices differently: keep what the user said, asked for, shared, or established carefully and close to their own words; your own explanations and reasoning can be condensed much further, to what they concluded or produced — as long as nothing in the six items above is dropped.
```

## Scope creep

On open-ended feature work, Fable 5.1 delivers what was asked and sometimes more: nearby fixes, unmentioned extensions, more committed test files than the change warrants. With this instruction, unrequested additions and committed test code drop substantially with no measurable change in task success (Fable 5.1):

```text
If, while working or testing, you find a pre-existing bug, a performance concern, or behavior the task doesn't mention, don't fix, optimize or extend it in this change unless the requested behavior cannot work without it; report it as a follow-up in your summary. Where the task is ambiguous, implement the reading its wording and the surrounding code most directly support, state that assumption in your summary, and don't build for the other readings as well. Verify your work however you like; scratch scripts and quick checks need not be kept. Commit tests only where the task asks for them or this repository already keeps tests for this kind of change, sized like the neighboring test files — roughly one focused test per stated behavior — and don't turn scratch checks into additional permanent test files. This is about extras only: implement every behavior the task asks for, completely.
```

## Search triggering

At `low` effort, Fable 5.1 calls search and retrieval tools less often and answers from memory more. Often the cheapest fix is raising effort for the affected turns only, mid-conversation, rather than for the whole session.

Otherwise, nudge toward verification in the system prompt (Fable 5.1):

```text
When a query centers on a name you do not confidently recognize, or recognize from a fast-moving area like AI models and developer tools where the landscape shifts within months, the name itself is the thing to verify: search before answering, and include the name as the user wrote it in at least one query alongside any reformulations. This holds even when you have some background on it — partial background is exactly what makes an out-of-date answer sound authoritative, so familiarity is not a reason to skip the search.
```

## Safeguard false positives

Fable 5.1's classifiers produce fewer false positives than Fable 5's did at launch, and finding vulnerabilities in source code is permitted. A blocked request returns HTTP 200 with `stop_reason: "refusal"` and a `stop_details` object naming the policy area.

Three situations raise the false-positive rate:

- **Compile-check phrasing.** Ask "Are there any bugs in this program?" instead of "Does this program compile without errors?"
- **Lesser-known languages.** Give the model context about the language, ideally access to its documentation.
- **Base64 in tool output.** Tools that return base64-encoded data into context can trigger false positives; removing them is the recommended fix.

On Fable 5, a distinct trigger is the `reasoning_extraction` category: prompts, skills, or harness instructions telling the model to echo, transcribe, or explain its internal reasoning as response text. Audit for reflection and show-your-thinking instructions when migrating. If your application needs reasoning visibility, read the structured `thinking` blocks and use a send-to-user tool for progress.

Configure server-side or client-side fallback so declined requests re-route. Permitted fallback targets for Fable 5.1 are Claude Opus 4.8 and Claude Opus 5.

## Whole-file rewrites

Fable 5.1 is more likely than Fable 5 to rewrite an entire text file instead of making a targeted edit. The result is usually the same, but unless the file is short or mostly changing, the rewrite costs more output tokens and time. Append to the system prompt or first user message (Fable 5.1):

```text
The number of tokens used to edit files is best minimized, all else being equal. Therefore, when it will not affect the end result, try to surgically edit a file rather than rewrite the entire thing.
```

## Long outputs

At `xhigh` and especially `max`, Fable 5.1 can think for a long time before writing, sometimes drafting most of a long deliverable in thinking and then writing it again as the reply. The simplest fix is to run these requests at `high` and move up only where a quality gain is measured.

If you do run at `xhigh` or `max`:

- set `max_tokens` to cover thinking plus the reply, not just the expected reply length;
- append this to the end of the user message, replacing `[max_tokens]` with the actual value (Fable 5.1):

```text
Everything produced in one reply, including any reasoning or drafting done before the reply, counts toward a single limit of about [max_tokens] tokens. If that limit is reached before the reply is finished, the person receives a cut-off response and has to start over. Composing an entire output or deliverable in full as reasoning and then again as a reply would double the length of the turn without improving the result, so don't do that.

Instead, when the person has asked for a long or effort-intensive deliverable such as a multi-section document, a large table or dataset, or a complete code file, spend extra effort on understanding the request, checking the inputs the answer depends on, settling the structure and other difficult decisions, and otherwise using the reasoning space to reason and the output space to write an output. Usually it is not needed to draft an output multiple times.
```

## Subagent blocking

Do not force the lead agent to stop and wait for each subagent. On coding tasks, letting the lead continue while subagents run lowers average time to completion at similar quality, token usage, and cost. The setup is three tool-semantics changes:

- the tool that starts a subagent returns immediately;
- each subagent's result comes back to the lead in a later `user` message;
- the lead gets a separate tool it can call when it wants to wait.

The model still often chooses to wait; the savings come from the runs where it carries on.

Prompt counterpart (Fable 5):

```text
Delegate independent subtasks to subagents and keep working while they run. Intervene if a subagent goes off track or is missing relevant context.
```

If delegation is excessive rather than absent, damp it instead:

```text
Use subagents when tasks can run in parallel, require isolated context, or involve independent workstreams that don't need to share state. For simple tasks, sequential operations, single-file edits, or tasks where you need to maintain context across steps, work directly rather than delegating.
```

## Vision detail

Fable does its best work on dense charts and complex visual input when it can iteratively analyze, crop, and visually verify. Run it as an agent with a container holding the raw images or videos and basic image-processing libraries preinstalled. If a container is too much overhead, an image-cropping tool alone delivers most of the uplift: it returns a chosen region cropped and enlarged, letting the model examine details and scaling test-time compute with image tokens. Fable is also trained to use bash and crop tools on flipped, blurry, or noisy images.

## Progress claims

On long autonomous runs, instruct the model to audit progress against actual tool results. In Anthropic's testing this nearly eliminated fabricated status reports even on tasks designed to elicit them (Fable 5):

```text
Before reporting progress, audit each claim against a tool result from this session. Only report work you can point to evidence for; if something is not yet verified, say so explicitly. Report outcomes faithfully: if tests fail, say so with the output; if a step was skipped, say that; when something is done and verified, state it plainly without hedging.
```

## Context anxiety

In very long sessions, Fable can suggest a new session, offer to summarize and hand off, or trim its own work. This is most often triggered by a harness that shows a remaining-token countdown to the model. Stop surfacing explicit context-budget counts where you can. If the harness must show them (Fable 5):

```text
You have ample context remaining. Do not stop, summarize, or suggest a new session on account of context limits. Continue the work.
```

For harnesses that compact or persist state to files, the cross-model version tells the model that compaction is automatic and to save progress before the window refreshes rather than wrapping up early.

## Unrequested actions

Fable can occasionally take actions nobody asked for: drafting an email, creating defensive git-branch backups. Define the boundary (Fable 5):

```text
When the user is describing a problem, asking a question, or thinking out loud rather than requesting a change, the deliverable is your assessment. Report your findings and stop. Don't apply a fix until they ask for one. Before running a command that changes system state (restarts, deletes, config edits), check that the evidence actually supports that specific action. A signal that pattern-matches to a known failure may have a different cause.
```

For destructive-action gating specifically, the cross-model reversibility block enumerates the categories that warrant confirmation (deletes, force pushes, published-commit amends, anything visible to others) and forbids destructive shortcuts such as `--no-verify`.

## Overplanning

To keep Fable from overplanning when a task is ambiguous (Fable 5):

```text
When you have enough information to act, act. Do not re-derive facts already established in the conversation, re-litigate a decision the user has already made, or narrate options you will not pursue in user-facing messages. If you are weighing a choice, give a recommendation, not an exhaustive survey. This does not apply to thinking blocks.
```

## Gold-plating

On routine work at higher effort, Fable can gather context and deliberate beyond what the task needs, and tidy or refactor unbidden (Fable 5):

```text
Don't add features, refactor, or introduce abstractions beyond what the task requires. A bug fix doesn't need surrounding cleanup and a one-shot operation usually doesn't need a helper. Don't design for hypothetical future requirements: do the simplest thing that works well. Avoid premature abstraction and half-finished implementations. Don't add error handling, fallbacks, or validation for scenarios that cannot happen. Trust internal code and framework guarantees. Only validate at system boundaries (user input, external APIs). Don't use feature flags or backwards-compatibility shims when you can just change the code.
```

Note the tension with higher effort's benefits: high effort also produces the best verification behavior and the most rigorous output. Damp the tidying rather than dropping effort, unless a sweep shows lower effort holds quality.

## Verbosity

Instruction following is strong enough that a short brevity instruction is as effective as enumerating each unwanted pattern (surveying options it won't pursue, root-cause essays, heavily structured PR descriptions, comments narrating the next line) (Fable 5):

```text
Lead with the outcome. Your first sentence after finishing should answer "what happened" or "what did you find": the thing the user would ask for if they said "just give me the TLDR." Supporting detail and reasoning come after. Being readable and being concise are different things, and readability matters more.

The way to keep output short is to be selective about what you include (drop details that don't change what the reader would do next), not to compress the writing into fragments, abbreviations, arrow chains like A → B → fails, or jargon.
```

## Readability

In extended agentic conversations, Fable can produce text that is hard to follow: arrow-chain shorthand, deep implementation detail, references to thinking the user never saw. A communication-style addendum mitigates it (Fable 5):

```text
Terse shorthand is fine between tool calls (that's you thinking out loud, and brevity there is good). Your final summary is different: it's for a reader who didn't see any of that.

If you've been working for a while without the user watching (overnight, across many tool calls, since they last spoke), your final message is their first look at any of it. Write it as a re-grounding, not a continuation of your working thread: the outcome first, then the one or two things you need from them, each explained as if new. The vocabulary you built up while working is yours, not theirs; leave it behind unless you re-introduce it.

When you write the summary at the end, drop the working shorthand. Write complete sentences. Spell out terms. Don't use arrow chains, hyphen-stacked compounds, or labels you made up earlier. When you mention files, commits, flags, or other identifiers, give each one its own plain-language clause. Open with the outcome: one sentence on what happened or what you found. Then the supporting detail. If you have to choose between short and clear, choose clear.
```

## Send-to-user

For long asynchronous agents, give the model a way to surface a message the user must see exactly as written without ending its turn. Tool inputs are never summarized, so the content arrives intact. Render the input directly in your UI and return a simple acknowledgement as the tool result.

```json
{
  "name": "send_to_user",
  "description": "Display a message directly to the user. Use this for progress updates, partial results, or content the user must see exactly as written before the task finishes.",
  "input_schema": {
    "type": "object",
    "properties": {
      "message": {
        "type": "string",
        "description": "The content to display to the user."
      }
    },
    "required": ["message"]
  }
}
```

Defining the tool is not enough; without an instruction Fable rarely calls it. Pair it with elicitation language (Fable 5):

```text
Between tool calls, when you have content the user must read verbatim (a partial deliverable, a direct answer to their question), call the send_to_user tool with that content. Use send_to_user only for user-facing content, not for narration or reasoning.
```

Do not route narration or reasoning through it; over-calling defeats the purpose. For agents that only narrate routine progress, the model's own summaries are typically adequate.

## Suggest vs act

Fable follows instructions literally. "Can you suggest some changes" gets suggestions; "Change this function" gets changes. To shift the default toward action, use the cross-model `<default_to_action>` block; to shift it toward research and recommendations, use `<do_not_act_before_instructions>`. Both are on the best-practices page. Do not stack them.

Because forced tool use is unavailable on Fable 5.1, an explicit prompt line is the mechanism for making the model call a tool rather than answer in text: name the tool and the condition, for example "Use the `get_weather` tool to answer." Fable 5.1 follows explicit tool instructions reliably.

## Grounding

To minimize hallucinations about code (cross-model):

```text
<investigate_before_answering>
Never speculate about code you have not opened. If the user references a specific file, you MUST read the file before answering. Make sure to investigate and read relevant files BEFORE answering questions about the codebase. Never make any claims about code before investigating unless you are certain of the correct answer - give grounded and hallucination-free answers.
</investigate_before_answering>
```

For long-document work, the documented pattern is quote-first: have the model extract relevant passages into `<quotes>` tags before answering.

## Test gaming

To prevent hardcoding to test cases and helper-script workarounds (cross-model):

```text
Please write a high-quality, general-purpose solution using the standard tools available. Do not create helper scripts or workarounds to accomplish the task more efficiently. Implement a solution that works correctly for all valid inputs, not just the test cases. Do not hard-code values or create solutions that only work for specific test inputs. Instead, implement the actual logic that solves the problem generally.

Focus on understanding the problem requirements and implementing the correct algorithm. Tests are there to verify correctness, not to define the solution. Provide a principled implementation that follows best practices and software design principles.

If the task is unreasonable or infeasible, or if any of the tests are incorrect, please inform me rather than working around them. The solution should be robust, maintainable, and extendable.
```

For multi-window work, pair it with a rule that tests are not to be removed or edited, since that leads to missing or buggy functionality.
