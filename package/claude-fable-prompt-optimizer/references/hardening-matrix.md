# Hardening Matrix

Add controls only for risks that actually exist in this workload. On Fable, the first pass is subtraction: an audit that only adds rules usually makes the prompt worse.

## Risk to control

| Risk | Controls to add |
| --- | --- |
| Current or changing facts | Retrieval requirement, name-verification nudge, freshness window, source priority, citations at point of use |
| Empty or weak retrieval | Alternate queries, broader and narrower search, source fallback, explicit unresolved result |
| Conflicting sources | Report the conflict, compare authority and date, justify the choice |
| Unmarked quotation in summaries | One complete example with a rationale showing indirect speech and marked quotes |
| Strict machine format | Structured outputs or strict tool use first; otherwise exact schema, no extra text, defined error object |
| Multiple deliverables | Coverage check before finalizing, explicit section order, no early finalization |
| Long or paginated work | Progress tracking, pagination rules, deduplication, stop condition |
| Multiple tools | Per-tool trigger condition, prerequisites, batching of independent calls, synthesis, no repeated work |
| Serial tool calls in an agent loop | Turn-scoped batching nudge appended after each round of tool results |
| Tool side effects | Authorization boundary, pre-flight summary, explicit confirmation, post-flight validation |
| Destructive or irreversible actions | Enumerated gated categories, evidence-supports-this-command rule, no destructive shortcuts, rollback path |
| Untrusted content in context | Delimit data, ignore embedded instructions, preserve source hierarchy, treat screen content as untrusted |
| Long autonomous run | Autonomy contract, evidence-grounded progress claims, verification interval, scope ceiling, stop condition |
| Silent agent | `thinking.display`, removal of anti-narration lines, then explicit update request |
| Content the user must see verbatim mid-run | Send-to-user tool plus elicitation instruction |
| Multiple context windows | State files, structured test status, setup scripts, prescriptive restart instructions, no token countdown to the model |
| Client-side compaction | Documented summarization instruction, no thinking blocks replayed, append-only assembly |
| Subagent orchestration | Delegation trigger, depth and concurrency limits, non-overlapping ownership, non-blocking returns, merge rules |
| Scope creep | Report-as-follow-up rule, single-reading rule for ambiguity, test-sizing rule |
| Gold-plating at high effort | No-refactor, no-speculative-abstraction, boundary-only-validation rule |
| Whole-file rewrites | Surgical-edit instruction |
| Long single-reply deliverable | Run at `high`, size `max_tokens` for thinking plus reply, single-limit note |
| Dense or mannered prose | Mannered-prose definition in a user message |
| Under-formatted chat replies | Delete anti-formatting blocks, add a when-formatting-helps rule |
| Unreadable final summary after a long run | Readability addendum for the closing message |
| Refusal risk in a benign domain | Bug-finding phrasing over compile-check phrasing, language documentation in context, no base64 in tool output, fallback configured |
| Reflection or reasoning-display instructions | Delete them; read structured thinking blocks instead |
| History-editing harness | Turn-scoped system messages, mid-conversation system and tool changes, server-side trimming, `prefix_mismatch_behavior` monitoring |
| Latency or cost constraint | Effort sweep including `low`, per-message effort, later compaction point, cost-per-task comparison |
| Legacy prompt or skill | Deletion pass, eval at default, re-add only measured needs |
| Code or runtime integration | Separate prompt defects from message-assembly, parameter, timeout, and application defects |
| Dataset-driven optimization | Baseline, failure taxonomy, one change at a time, regression set, manual review |

## Escalation rule

Start with the minimal pattern. Add one control per credible failure mode. A longer prompt is justified only when it prevents a specific observed error or encodes a product requirement. On Fable specifically, the marginal control is more likely to cost quality than to buy reliability, because the behaviors most controls target no longer occur.

## Anti-patterns

Prompt-level:

- Repeating the same rule in several sections.
- "Be accurate", "be smart", "think carefully" with no observable contract.
- Asking for hidden reasoning, reflection, or a reasoning transcript instead of evidence and checks.
- Enumerating every unwanted behavior instead of defining the anti-pattern once.
- Carrying an anti-formatting block onto Fable 5.1.
- Leaving an anti-narration line in place and then adding a request for more updates.
- "CRITICAL", "you MUST", all-caps insistence for tool triggering.
- Exposing every available tool regardless of relevance.
- Requiring confirmation for harmless read-only work.
- Permitting destructive or external actions with no boundary.
- Running an until-green loop with no cycle, strategy, scope, or stop bound.
- Designing around prefill or forced tool use, neither of which exists on Fable 5.1.
- Treating the highest effort level as automatically optimal.

Harness-level:

- Injecting a per-turn reminder and deleting it on the next request.
- Rebuilding `system` or `tools` between requests in the same conversation.
- Summarizing older turns in place.
- Replaying thinking blocks after a prefix change without a `prefix_mismatch_behavior` decision.
- Leaving `thinking.display` at `"omitted"` in a UI that shows progress.
- Blocking the lead agent on every subagent return.
- Sizing `max_tokens` for the expected reply only.
- Showing the model a remaining-token countdown.
- Returning base64 blobs into context.
- Client timeouts sized for prior-model turn lengths.
- No refusal branch in a production integration.
- Changing several prompt and configuration variables at once during evaluation.
