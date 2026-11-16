# Official Anthropic Sources

Use official Anthropic properties only for current Fable research unless the user explicitly asks for broader sources. Third-party field reports are experiment ideas: label them as such and keep them out of configuration claims.

## Preferred source order

1. The model-specific prompting page for the exact model in use.
2. The model's what's-new and migration pages for parameters, pricing, and breaking changes.
3. Feature guides on `platform.claude.com/docs` (effort, thinking, preserved thinking, tool use, refusals).
4. Claude Code and Agent SDK docs on `code.claude.com/docs` for surface behavior (subagents, model aliases, effort defaults in the CLI).
5. The cross-model prompting best-practices page for techniques that are not model-specific.
6. Official product and release posts on `anthropic.com`, and support articles on `support.claude.com`.

A model-specific page overrides the cross-model page. Instruction blocks are measurements on the model whose page carries them.

## Core pages verified on 2026-11-16

Prompting:

- Prompting Claude Fable 5.2: `https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-fable-5-2`
- Prompting Claude Fable 5.1: `https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-fable-5-1`
- Prompting Claude Fable 5: `https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-fable-5`
- Prompting Claude Opus 5.5: `https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-opus-5-5`
- Prompting best practices (all current models): `https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices`

Models, migration, pricing:

- What's new in Claude Fable 5.2: `https://platform.claude.com/docs/en/models/fable-5-2/whats-new-fable-5-2`
- Claude Fable 5.2 and Mythos 5.2 migration guide: `https://platform.claude.com/docs/en/models/fable-5-2/migration-guide`
- Models overview: `https://platform.claude.com/docs/en/models/overview`
- Optimizing for cost and intelligence (orchestrator and advisor measurements): `https://platform.claude.com/docs/en/about-claude/models/optimizing-for-cost-and-intelligence`
- Product page: `https://www.anthropic.com/claude/fable`
- Launch post: `https://www.anthropic.com/claude-fable-and-mythos-5-2`
- Pricing: `https://platform.claude.com/docs/en/about-claude/pricing` (5.2 prices read from the what's-new page)

Features Fable prompts and harnesses depend on:

- Effort: `https://platform.claude.com/docs/en/build-with-claude/effort`
- Per-message effort: `https://platform.claude.com/docs/en/build-with-claude/effort-per-message`
- Thinking (types, display, progress updates, sampling, output limits): `https://platform.claude.com/docs/en/build-with-claude/thinking`
- Preserved thinking: `https://platform.claude.com/docs/en/build-with-claude/preserved-thinking`
- Prefix checks: `https://platform.claude.com/docs/en/build-with-claude/preserved-thinking/prefix-checks`
- Change tools or instructions without failing the prefix check: `https://platform.claude.com/docs/en/build-with-claude/preserved-thinking/change-tools-or-instructions`
- Mid-conversation system messages and tool changes: `https://platform.claude.com/docs/en/build-with-claude/mid-conversation-system-messages`
- Compaction on demand: `https://platform.claude.com/docs/en/build-with-claude/compaction-on-demand`
- Context editing: `https://platform.claude.com/docs/en/build-with-claude/context-editing`
- Refusals and fallback: `https://platform.claude.com/docs/en/build-with-claude/refusals-and-fallback`
- Strict tool use: `https://platform.claude.com/docs/en/agents-and-tools/tool-use/strict-tool-use`
- Structured outputs: `https://platform.claude.com/docs/en/build-with-claude/structured-outputs`
- Computer use tool: `https://platform.claude.com/docs/en/agents-and-tools/tool-use/computer-use-tool`
- Advisor tool: `https://platform.claude.com/docs/en/agents-and-tools/tool-use/advisor-tool`
- Task budgets: `https://platform.claude.com/docs/en/build-with-claude/task-budgets`
- Beta headers (usage only; strings live on each feature page): `https://platform.claude.com/docs/en/api/beta-headers`

Claude Code and Agent SDK:

- Subagents in Claude Code: `https://code.claude.com/docs/en/sub-agents`
- Subagents in the Agent SDK: `https://code.claude.com/docs/en/agent-sdk/subagents`
- Model configuration (the `fable` alias, effort defaults, fallback): `https://code.claude.com/docs/en/model-config`

## Beta headers read on 2026-11-16

| Feature | Header | Source page |
| --- | --- | --- |
| Per-message effort | `mid-conversation-output-config-2026-07-01` | Prompting Fable 5.2 |
| Turn-scoped system messages (`clear_at`) | `mid-conversation-system-clear-at-2026-08-21` | Mid-conversation system messages |
| Progress updates as text (`display: "updates"`) | `thinking-display-updates-2026-08-18` | Thinking |
| Prefix-check controls, `input_transformations` | `thinking-binding-controls-2026-08-01` | Prefix checks |
| Server-side fallback (`fallbacks`) | `server-side-fallback-2026-07-01` | Refusals and fallback |
| Mid-conversation tool changes, inline definitions | `inline-tools-2026-09-15` | Mid-conversation system messages |
| Mid-conversation tool changes by reference | `mid-conversation-tool-changes-2026-07-01` | Mid-conversation system messages |
| MCP server added through `tool_addition` | `mcp-client-2026-09-15` | Change tools or instructions |
| Compaction on demand | `compact-2026-09-04` | What's new in Fable 5.2 |
| Context editing | `context-management-2025-06-27` | Change tools or instructions |

The beta headers page no longer lists strings; confirm each on its feature page before putting it in code. Platform coverage differs per header.

## Research procedure

1. Open the prompting page for the exact model in use, first.
2. Open the model's what's-new page for parameters, breaking changes, and pricing.
3. Open the feature guide for anything you are about to configure.
4. For Claude Code or Agent SDK work, open the `code.claude.com` page: CLI defaults differ from API defaults.
5. Verify exact identifiers: model IDs, parameter names, accepted values, defaults, beta strings, prices.
6. Cite the source beside the claim, and record the verification date in anything durable.

## Conflict and absence handling

- A model-specific prompting page beats the cross-model page; a current what's-new or feature page beats an older migration article.
- Surface defaults differ and are not conflicts: Fable 5.2 defaults to `high` effort on the Claude API (effort page) and to `medium` in Claude Code and Claude apps (model-config page, launch post). Say which surface a claim covers.
- Code examples using older model IDs demonstrate the feature, not the current default.
- If two official pages disagree, state the conflict rather than silently choosing.
- If nothing official confirms a parameter or behavior, mark it `requires verification` and do not invent syntax.
