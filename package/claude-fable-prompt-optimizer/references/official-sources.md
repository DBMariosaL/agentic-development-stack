# Official Anthropic Sources

Use official Anthropic properties only for current Fable research unless the user explicitly asks for broader sources.

## Preferred source order

1. The model-specific prompting page for the exact model in use.
2. The model's what's-new and migration pages for parameters, pricing, and breaking changes.
3. Feature guides on `platform.claude.com/docs` (effort, thinking, tool use, structured outputs, compaction, context editing, caching, refusals).
4. The cross-model prompting best-practices page for techniques that are not model-specific.
5. The Claude Cookbook for working implementations.
6. Official product and release posts on `anthropic.com`, and support articles on `support.claude.com`.

A model-specific page overrides the cross-model page. The cross-model page marks several techniques as measured on a particular model; treat those as measurements, not universal rules.

## Core pages verified on 2026-09-03

Prompting:

- Prompting Claude Fable 5.1: `https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-fable-5-1`
- Prompting Claude Fable 5: `https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-fable-5`
- Prompting best practices (all current models): `https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices`
- Prompting Claude Opus 5: `https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-opus-5`

Models and migration:

- What's new in Claude Fable 5.1: `https://platform.claude.com/docs/en/models/fable-5-1/whats-new-fable-5-1`
- Claude Fable 5.1 migration guide: `https://platform.claude.com/docs/en/models/fable-5-1/migration-guide`
- Introducing Claude Fable 5 and Claude Mythos 5: `https://platform.claude.com/docs/en/models/fable-5/introducing-claude-fable-5-and-claude-mythos-5`
- Models overview: `https://platform.claude.com/docs/en/models/overview`
- Choosing a model: `https://platform.claude.com/docs/en/about-claude/models/choosing-a-model`
- Pricing: `https://platform.claude.com/docs/en/about-claude/pricing`

Features that Fable prompts depend on:

- Effort: `https://platform.claude.com/docs/en/build-with-claude/effort`
- Thinking (adaptive, display, progress updates, preserved): `https://platform.claude.com/docs/en/build-with-claude/thinking`
- Preserved thinking: `https://platform.claude.com/docs/en/build-with-claude/preserved-thinking`
- Mid-conversation system messages and turn-scoped messages: `https://platform.claude.com/docs/en/build-with-claude/mid-conversation-system-messages`
- Compaction: `https://platform.claude.com/docs/en/build-with-claude/compaction`
- Context editing: `https://platform.claude.com/docs/en/build-with-claude/context-editing`
- Context windows: `https://platform.claude.com/docs/en/build-with-claude/context-windows`
- Prompt caching: `https://platform.claude.com/docs/en/build-with-claude/prompt-caching`
- Refusals and fallback: `https://platform.claude.com/docs/en/build-with-claude/refusals-and-fallback`
- Fallback credit: `https://platform.claude.com/docs/en/build-with-claude/fallback-credit`
- Structured outputs: `https://platform.claude.com/docs/en/build-with-claude/structured-outputs`
- Strict tool use: `https://platform.claude.com/docs/en/agents-and-tools/tool-use/strict-tool-use`
- Tool use overview: `https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview`
- Memory tool: `https://platform.claude.com/docs/en/agents-and-tools/tool-use/memory-tool`
- Computer use tool: `https://platform.claude.com/docs/en/agents-and-tools/tool-use/computer-use-tool`
- Browser use tool: `https://platform.claude.com/docs/en/agents-and-tools/tool-use/browser-use-tool`
- Code execution tool: `https://platform.claude.com/docs/en/agents-and-tools/tool-use/code-execution-tool`
- Token counting: `https://platform.claude.com/docs/en/build-with-claude/token-counting`
- Beta headers: `https://platform.claude.com/docs/en/api/beta-headers`
- Crop tool recipe: `https://platform.claude.com/cookbook/multimodal-crop-tool`

## Beta headers to verify before recommending

| Feature | Header |
| --- | --- |
| Per-message effort | `mid-conversation-output-config-2026-07-01` |
| Turn-scoped system messages | `mid-conversation-system-clear-at-2026-08-21` |
| Progress updates as text | `thinking-display-updates-2026-08-18` |
| Thinking block binding controls | `thinking-binding-controls-2026-08-01` |

Beta strings and availability change. Confirm each against the beta headers page or the feature guide before putting it in code.

## Research procedure

1. Open the prompting page for the exact model in use, first.
2. Open the model's what's-new page for parameters, breaking changes, and pricing.
3. Open the feature guide for anything you are about to configure.
4. Verify exact identifiers: model IDs, parameter names, accepted values, defaults, beta header strings, enforcement dates, prices.
5. Check code examples against the current SDK reference before returning code.
6. Cite the source beside the claim, and record the verification date in anything durable.

## Conflict and absence handling

- A model-specific prompting page beats the cross-model page.
- A current what's-new or feature page beats an older migration article.
- An instruction block on the Fable 5 page is a Fable 5 measurement; re-check it on Fable 5.1 before presenting it as the fix.
- Code examples using older model IDs demonstrate the feature, not the current default.
- Distinguish Claude API parameters from Claude Code, claude.ai, and Agent SDK surface behavior.
- If two official pages disagree, state the conflict rather than silently choosing.
- If nothing official confirms a parameter or behavior, mark it unverified and do not invent syntax.
