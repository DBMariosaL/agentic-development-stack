# Add controls for an identified risk

| Failure risk | Useful control |
| --- | --- |
| Wrong or partial result | Observable acceptance criteria and deliverable coverage |
| Unnecessary pauses | Clear authorized scope and actual decision boundary |
| Conflicting instructions | Trace active rule, priority, and task applicability |
| Unsupported facts | Relevant sources, claim support, explicit absence handling |
| Injection in documents or tools | Separate instructions from untrusted evidence |
| Empty, stale, or partial retrieval | Coverage check, alternate retrieval, unresolved status |
| Machine parsing | Schema, permitted missing values, refusal/incomplete handling |
| Tool dependencies or async work | Required inputs, pending state, wait before dependent claims |
| Ambiguous mutation outcome | Inspect resulting state before retry |
| Excessive verification | Acceptance-linked checks and a stop after sufficient evidence |
| Delegation overhead | Independent scope, bounded concurrency, parent integration |
| Expensive repeated calls | User budget or meaningful progress-based termination |
| Compaction or steering | Preserve decisions, completed artifacts, pending work and scope |
| Runtime incompatibility | Separate code/configuration changes from prompt changes |
| Visual fidelity | Actual references, properties to preserve, rendered inspection |

The controls are options, not a checklist to paste wholesale. A simple rewrite may need only an output sentence. Preserve required domain procedures even when they are long. Do not remove a user's explicit constraint in the name of autonomy.