# Hardening Matrix

Add controls only for risks that exist in this workload. On Fable, the first pass is subtraction: Fable 5.2 follows instructions, style rules, and stored cautions closely, so each extra rule is more likely to be obeyed past its purpose than to be ignored [P].

## Risk to control

| Risk | Controls to add |
| --- | --- |
| Current or changing facts | Retrieval requirement, name verification, freshness window, source priority, citations at point of use |
| Empty or weak retrieval | Alternate queries, source fallback, explicit unresolved result |
| Conflicting sources | Report the conflict, compare authority and date, justify the choice |
| Strict machine format | Strict tool use or JSON outputs (not in CMEK organizations); otherwise exact schema, validation in code, defined error object |
| Multiple deliverables | Coverage check before finalizing, explicit section order |
| Multiple tools | Per-tool trigger condition, prerequisites, independent calls together, synthesis |
| Tool side effects | Authorization boundary, pre-flight summary, confirmation, post-flight validation |
| Destructive or irreversible actions | Named gated actions with scope and reason, evidence-supports-this-command rule, no destructive shortcuts, rollback path |
| Untrusted content in context | Delimit data; files others can edit go in `tool_result`, not `system`; screen content untrusted |
| Long autonomous run | "Finishing work" block, evidence-grounded progress claims, verification interval, scope ceiling, stop condition |
| Early stops at `low` or `medium` | "Finishing work" block, or raise effort for that phase |
| Unneeded approvals, held work | Delete stale cautions; list steps needing no approval; replace "never" with scoped rules |
| Unwanted restructuring, or unwanted duplication | Ownership sentence on or off, chosen per task and per subagent |
| Silent agent | `thinking.display`, turn-scoped reminder, then opening-line and recap text |
| Content the user must see verbatim mid-run | Send-to-user tool from the first request, plus elicitation |
| Multiple context windows | State files, structured test status, setup scripts, restart instructions, no token countdown |
| Subagent orchestration | Delegation worth-it rule with stated cost, model and effort per role, brief contents, ownership, non-blocking returns, depth/concurrency/spend caps in the harness |
| Subagent reports to a Fable parent | Status-first report contract, evidence pointers, unverified items labelled, model named |
| Over-delegation | Remove delegate lines; cost-focused subagent tool description |
| Low-context final reader | "Communicating clearly" block; remove hard sentence-length rules first |
| Refusal risk | No reasoning in reply text or JSON fields; fallback configured per subagent call; verification programs for legitimate cyber or bio work |
| History-editing harness | Append-only assembly, system messages, tool additions and removals, compaction on demand, `prefix_mismatch_behavior` decision |
| Model routing or fallback | Expect lost Fable 5.2 reasoning on switch; minimize bounces |
| Latency or cost constraint | Effort sweep including `low`, per-message effort, cheaper subagent models, Opus 5.5 comparison |
| Legacy prompt, skill, memory | Deletion pass, eval at default, re-add only measured needs |
| Code or runtime integration | Separate prompt defects from message-assembly, parameter, timeout, and application defects |

## Escalation rule

Start with the minimal pattern. Add one control per credible failure mode. A longer prompt is justified only when it prevents an observed error or encodes a product requirement.

## Anti-patterns

Prompt-level:

- The same rule in several sections, or in both the system prompt and a skill.
- "Be accurate", "think carefully", "answer directly without deliberating" with no observable contract.
- Asking for reasoning in the reply, a scratchpad section, or a `reasoning` field.
- Standing "delegate" or "use subagents where possible" lines.
- Absolute "never" rules without scope; vague approval categories.
- Hard style limits such as maximum sentence length.
- A token budget shown to the model.
- The ownership sentence in a narrow-patch prompt, or its absence where restructuring is the point.
- "Treat that answer as done" lines where self-correction matters.
- "CRITICAL", "you MUST" for tool triggering.
- Designing around prefill or forced tool use.
- Treating the highest effort level as automatically optimal.

Harness-level:

- Editing `system`, `tools`, or earlier messages mid-conversation, including a reminder injected and later removed.
- An MCP tool list that changes between requests without pinning.
- Shipping `"drop_block"` permanently to hide edits.
- `thinking.display` left at `"omitted"` in a UI that shows progress.
- `max_tokens` sized for the reply only.
- Leaving `effort` unset after moving traffic from Opus 5.5.
- Subagents that inherit the lead's model by accident.
- No depth, concurrency, or spend cap on fan-out.
- No refusal branch; no fallback on subagent calls.
- Changing several prompt and configuration variables in one experiment.
