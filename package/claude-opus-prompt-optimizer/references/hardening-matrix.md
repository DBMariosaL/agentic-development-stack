# Hardening Matrix

Add controls only for risks that actually exist in this workload. On Opus 5.5 and Opus 5 the first pass is removal: an audit that only adds rules usually makes the prompt slower and more expensive without making it better.

## Risk to control

| Risk | Controls to add |
| --- | --- |
| Replies too long for the product | Conciseness instruction, plus a short reminder near the end of a long system prompt |
| Bloated files written to disk | Separate deliverable-length calibration |
| Heavy narration during agentic work | Narration cadence instruction with positive examples |
| Wasted tokens on self-verification | Delete verification, double-check, and re-verify instructions; delete separate verification stages |
| Subagent sprawl | Delegation rule naming the qualifying scenarios, plus deterministic depth, concurrency, and spend caps |
| Correction chatter in a user-facing product | Correction-narration limiter; do not pair with a double-check instruction |
| Review or analysis reporting too little | Remove self-limiting language; ask for everything and filter in a separate pass |
| Task growing steps nobody asked for | Explicit scope block; do not stack a separate ask-if-unsure rule on top |
| Fragmented specification producing partial work | Deliver the complete spec up front in one brief |
| House style ignored in documents, decks, spreadsheets | State the style or template explicitly |
| Leaked tool calls or internal XML tags | Enable thinking; if impossible, cap effort at `high` and add the combined artifact mitigation; remove any do-not-think rule |
| 400 on requests that disable thinking | Lower effort to `high` or below, or remove the `thinking` field |
| `content[0].text` undefined after migration | Select content blocks by `type`; replay thinking blocks unmodified |
| Unexpected cost rise after migration | Re-baseline: thinking tokens now bill as output and count toward `max_tokens` |
| Runaway agentic spend | Task budget sized from a measured no-budget baseline, with `max_tokens` as the hard ceiling |
| Refusal-like behavior or early stops after adding a budget | Raise the budget; stop decrementing `remaining` client-side |
| Truncated output at `xhigh` or `max` | `max_tokens` at 64k or above |
| Cold cache in a long session | Per-message effort instead of top-level changes; fixed budget; mid-conversation tool changes |
| Latency-critical workload | Effort step-down first; fast mode last, with its 2x price stated |
| Current or changing facts | Retrieval requirement, freshness window, source priority, citations at point of use |
| Empty or weak retrieval | Alternate queries, broader and narrower search, source fallback, explicit unresolved result |
| Strict machine format | Structured outputs or strict tool use first; otherwise exact schema, no extra text, defined error object |
| Multiple tools | Per-tool trigger condition, prerequisites, synthesis, no repeated work |
| Tool side effects | Authorization boundary, pre-flight summary, explicit confirmation, post-flight validation |
| Destructive or irreversible actions | Enumerated gated categories, no destructive shortcuts, rollback path — reconciled with the scope block |
| Untrusted content in context | Delimit data, ignore embedded instructions, preserve source hierarchy |
| Vision-critical work | Crop and zoom tooling rather than higher effort; re-validate legacy prompt workarounds |
| Legacy prompt or skill from Opus 4.8 or earlier | Amplifier pass, fresh effort sweep, re-baselined cost |
| Dataset-driven optimization | Baseline, failure taxonomy, one change at a time, regression set, manual review |

### Opus 5.5 additions

| Risk | Controls to add |
| --- | --- |
| Long run stops at a plausible milestone or overshoots | Whole task in one message with an observable done criterion and named stop conditions |
| Unattended loop ends on a text-only turn | Harness treats `end_turn` text as a report; checklist; continuation naming open items, capped at 2–3; standing instruction at the end of the system prompt from the first request |
| Human-in-the-loop run stops too little or too much | `CLAUDE.md` or system rule naming which stops are wanted; pair-programming variant asks for plan and recap |
| Silent UI during agentic turns | `thinking.display: "updates"`, render progress-update thinking blocks, harness reminder after ~5 silent steps |
| Slow first token in chat | Delete "think carefully"; lower effort; settled-answers paragraph; `Answer directly without deliberating.` last |
| `reasoning_extraction` refusals | Delete reasoning-in-reply instructions; ask for a bounded rationale; read `display: "summarized"` |
| Bio or cyber refusals | Refusal branch reading `stop_details.category`, fallback configured, awareness that fallback drops thinking |
| 400 on replayed thinking blocks | Append-only conversation; mid-conversation system messages and `tool_addition` instead of prefix edits |
| Forced tool use needed | `tool_choice: auto` plus strict tool use or structured outputs, and a prompt trigger condition |
| Missed context in multi-app automation | Explore-broadly sentence; untrusted content kept out of searched records |
| Injection through user-pasted text | `<pasted_content id>` wrapping plus the system note |
| Slow agent team | Harness time signal (elapsed vs budget), hard timeout kept |
| Generic frontend output | Named exclusion list, iterated |
| Research hides gaps | "Mark anything you couldn't confirm, and say where you looked." |
| Context loss on long Claude Code runs | Task list in a file the model updates |

## Escalation rule

Start with the minimal pattern. Add one control per credible failure mode. A longer prompt is justified only when it prevents a specific observed error or encodes a product requirement.

Opus 5.5 and Opus 5 share a distinctive asymmetry: adding an instruction that duplicates a built-in behavior costs tokens and latency on *every* request, while the behavior it targets was already handled. The expected value of a speculative control is negative.

## Anti-patterns

Prompt-level:

- Any instruction to verify, double-check, or re-verify.
- A subagent whose job is to check the main agent's work.
- Encouraging delegation, or leaving delegation entirely unbounded.
- Trying to shorten responses by lowering effort.
- Calibrating one length surface and assuming the others follow.
- Asking the model to pre-filter its own findings by severity or importance.
- Stacking a scope block and an ask-if-unsure rule that pull against each other.
- Telling the model not to think or not to reason.
- "Be accurate", "be thorough" with no observable contract.
- "Think carefully", "think step by step", "think hard" — Opus 5.5 always thinks; these slow first tokens with no clear quality gain.
- Asking for the model's reasoning, chain of thought, or thought process in the reply (`reasoning_extraction` on Opus 5.5).
- "After every N tool calls, summarize progress" scaffolding — progress updates are built in.
- "Avoid a generic look" instead of a named exclusion list.
- A long agentic task with no done criterion and no stated stop conditions.
- Adding the unattended standing instruction to a human-in-the-loop product, or midway through a session.
- "CRITICAL", "you MUST", all-caps insistence for tool triggering.
- Exposing every available tool regardless of relevance.
- Requiring confirmation for harmless read-only work.
- Permitting destructive or external actions with no boundary.
- Designing around prefill, which is unsupported from the 4.6 generation onward.
- Carrying Opus 4.6-era overeagerness and subagent-damping blocks across without re-measuring.
- Feeding a hard task's specification in fragments across turns.

Harness-level:

- Reading `content[0].text` or assuming the first streamed block is text.
- Stripping or modifying thinking blocks before replaying them with tool results.
- Disabling thinking as a cost measure.
- `max_tokens` sized for the expected reply only, or under 64k at `xhigh` and `max`.
- A task budget guessed rather than measured, or below the 20,000-token minimum.
- Decrementing `task_budget.remaining` client-side while also resending full history.
- Mutating top-level `effort`, budget values, or `speed` mid-session and losing the cache.
- Uncapped subagent depth and concurrency, or a pinned Claude Code SDK below 2.1.217.
- A custom system prompt on Claude Code with no delegation guidance at all.
- No refusal branch in a production integration.
- No fallback path when fast mode is rate limited.
- Changing several cost levers at once during evaluation.
- On Opus 5.5: any `thinking` value other than adaptive or omitted; forced `tool_choice`; `computer_20251124` on the Claude API or Google Cloud.
- On Opus 5.5: editing `system`, `tools`, or earlier messages mid-conversation.
- On Opus 5.5: rendering only `text` blocks in an agentic UI, or treating a text-only `end_turn` as task completion.
- On Opus 5.5: omitting `effort` and inheriting `medium` without having swept, or carrying an Opus 5 level over unchanged.
- A router or fallback that silently moves conversations off Opus 5.5 without accounting for lost thinking.
