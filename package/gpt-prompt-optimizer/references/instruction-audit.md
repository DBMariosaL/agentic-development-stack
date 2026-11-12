# Audit an instruction stack

Use for conflicting prompts, skills, AGENTS.md, repeated approval pauses, or accumulated workarounds.

Inspect the active instruction path for the target task: applicable instructions, loaded skill entrypoints, referenced workflow sections, tool descriptions, prompt assembly, and examples. Start with relevant files; expand only when a rule points elsewhere or the cause remains unexplained. Distinguish present-on-disk from actually loaded.

Classify each consequential rule:

| Keep | Narrow | Remove or relocate |
| --- | --- | --- |
| Product contract, domain invariant, explicit user constraint | A useful rule with an overbroad trigger | Duplicate text or generic encouragement |
| Real authorization boundary | A checkpoint needed only for an unresolved consequential choice | Obsolete workaround unsupported by current failures |
| Necessary executable procedure or schema | Mandatory review/delegation applied to small tasks | Mode-specific detail loaded for unrelated tasks |

Trace an undesired pause to its exact source when possible. Report the rule and why it applies; do not label every conservative interpretation an explicit requirement. A user preference can override a skill guideline, but cannot override higher-priority instructions or runtime permissions.

For discovery metadata, describe the actual capability and discriminating trigger. Avoid treating any mention of code, files, or data as a request for prompt optimization. Put shared instructions in the entrypoint and conditional detail in linked references. A skill should not require an inventory of all other skills to handle a simple rewrite.

## Example boundary repairs

These are illustrative replacements, not mandatory clauses.

- "Ask before every file change" in a locally authorized editing task: distinguish the approved edit from operations beyond that scope.
- "Stop after the first implementation for review": keep it for a requested review checkpoint; otherwise define the verified deliverable as the finish point.
- "Always use three agents": decide from independent work, tool availability, budget, and merging cost.
- "Read the whole repository first": inspect the dependency path needed to understand the change, then expand for unresolved questions.
- "Repeat until perfect": specify acceptance evidence and a meaningful resource or no-progress stop.

Preserve explicit user requirements even if expensive. Flag their tradeoffs rather than silently deleting them. Keep useful examples and fragile operational steps until their purpose is understood.

Return the revised artifact plus material behavior changes when requested. For an audit-only request, propose changes without editing other files. During a rename, inspect direct callers and update in-scope references; preserve unrelated instructions and historical records.