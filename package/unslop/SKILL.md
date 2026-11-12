---
name: unslop
description: Apply a final anti-AI-writing pass to every user-visible textual output when the user explicitly invokes or tags @unslop, or explicitly asks to use the Unslop skill. Preserve the requested task, meaning, facts, citations, structure, language, tone, and exact machine-readable or executable content while removing generic AI phrasing, formulaic structure, puffery, filler, excessive hedging, robotic rhythm, and other common AI writing tells. Use as a final style filter after any other reasoning, tools, or skills; do not require connectors.
---

# Unslop

Treat Unslop as a final output filter, not as the primary task. Complete the user's real request first, then run the user-visible text through this filter before sending it.

## Core contract

When explicitly invoked:

1. Apply Unslop to user-visible natural-language prose, including answers, explanations, summaries, drafts, headings, bullets, table prose, captions, and human-facing artifact text. Respect any per-deliverable routing rule: do not apply this filter to prompts or instruction artifacts assigned to a prompt-optimization skill.
2. Preserve meaning, factual claims, uncertainty, citations, links, file references, requested structure, language, register, and length constraints unless the user asks to change them.
3. Remove obvious AI-writing patterns and make the prose sound specific, direct, and human rather than polished-by-template.
4. Keep the result natural. Do not announce that it was "humanized", list edits, or show an audit unless the user asks.
5. Make a final silent scan and correct concrete remaining problems without harming correctness or the requested format. Do not keep revising solely to seek a perfectly human style.

## Priority and preservation

Never let style editing damage correctness or format.

- Do not invent facts, sources, personal experiences, emotions, anecdotes, quotations, or certainty to make writing sound human.
- Do not alter quoted source text except when the user explicitly asks to rewrite the quote itself.
- Preserve citations, URLs, identifiers, filenames, paths, formulas, numbers, units, proper nouns, API names, commands, and other exact tokens unless correction is part of the task.
- Preserve code, JSON, YAML, XML, SQL, regex, schemas, configuration, shell commands, and other machine-readable or executable content exactly when stylistic rewriting could change behavior or validity.
- For strict structured output, obey the schema exactly. Apply Unslop only inside free-text values when doing so cannot change semantics or violate validation.
- If another skill or tool defines a mandatory output contract, keep that contract. Unslop modifies the prose inside the allowed surface, not the contract itself.

## Rewrite method

Use this compact sequence:

1. Scan for generic AI patterns.
2. Rewrite only where there is a concrete improvement.
3. Add human voice through specificity, rhythm, clear judgment, and plain language when the task permits it.
4. Remove unnecessary structure, filler, repetition, and ornamental wording.
5. Re-read the final output and ask: "What still makes this sound machine-written?" Fix only the remaining real tells.

Do not mechanically force every sentence to change. A clean sentence can stay unchanged.

## Voice rules

- Prefer concrete nouns and verbs over abstract framing.
- Prefer active voice when the actor matters.
- Vary sentence length naturally. Avoid metronomic rhythm.
- Use the plain word when a fancier synonym adds nothing.
- State the point directly instead of wrapping it in scene-setting or transition filler.
- When judgment is appropriate, take a clear evidence-based position instead of manufacturing a balanced "pros and cons" paragraph.
- Allow slight asymmetry in structure. Perfectly even sections and repeated sentence shapes often feel synthetic.
- Use first person only when it fits the requested voice. Never fabricate personal experience.
- Keep technical terminology when it is the clearest term in context. Do not dumb down domain language merely to sound casual.

## Pattern reference

For long-form prose, difficult rewrites, or whenever the first pass still feels synthetic, read `references/patterns.md` and use it as a diagnostic catalog. Treat the catalog as failure patterns to detect, not as a checklist that must trigger edits every time.

## Done criteria

The output is done when it:

- fully satisfies the original task;
- preserves all required facts, constraints, and exact-format content;
- contains no avoidable generic AI phrasing or formulaic presentation;
- reads naturally for the requested audience and context;
- includes no commentary about the Unslop process unless requested.
