# Official Anthropic Sources

Use official Anthropic properties only for current Opus 5.5 and Opus 5 research unless the user explicitly asks for broader sources.

## Preferred source order

1. The prompting page for the target model (Opus 5.5 or Opus 5).
2. That model's what's-new and migration pages, for parameters, breaking changes, and pricing.
3. Feature guides on `platform.claude.com/docs` (effort, thinking, task budgets, fast mode, tool use, structured outputs, caching, refusals).
4. The cross-model prompting best-practices page, for techniques that are not model-specific.
5. Claude Code and Agent SDK docs on `code.claude.com`, for harness-level caps and presets.
6. The Claude Cookbook for working implementations.
7. Official product and release posts on `anthropic.com`, playbooks on the `claude.dev` blog, and support articles on `support.claude.com`.

The `claude.dev` playbooks are the best source for how people use a model inside Claude apps and Claude Code (`CLAUDE.md` rules, slash commands, settings, flagged-message handling). They are not a source for API parameters; take those from `platform.claude.com`.

A model-specific page overrides the cross-model page. The cross-model page carries guidance measured on Opus 4.5 and 4.6 — overeagerness, subagent overuse, parallel tool calling, thinking constraints. Treat each as a measurement on that model, not a universal rule, and re-check on Opus 5 before applying. Several of those blocks are amplifiers here.

## Core pages

Opus 5.5 pages verified on 2026-09-25; Opus 5 pages on 2026-09-04.

Opus 5.5:

- Prompting Claude Opus 5.5: `https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-opus-5-5`
- What's new in Claude Opus 5.5: `https://platform.claude.com/docs/en/models/opus-5-5/whats-new-opus-5-5`
- Migration guide to Claude Opus 5.5 (from Opus 5, 4.8, 4.7, 4.6 and earlier, Sonnet 5): `https://platform.claude.com/docs/en/models/opus-5-5/migration-guide`
- Getting the most out of Opus 5.5 in Claude and Claude Code (claude.dev playbook, 2026-09-22): `https://claude.dev/blog/getting-the-most-out-of-opus-5-5/`

Prompting:

- Prompting Claude Opus 5: `https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-opus-5`
- Prompting best practices (all current models): `https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices`
- Prompting Claude Opus 4.8: `https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-opus-4-8`
- Prompting Claude Fable 5.1: `https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-fable-5-1`

Model and migration:

- What's new in Claude Opus 5: `https://platform.claude.com/docs/en/models/opus-5/whats-new-opus-5`
- Claude Opus 5 overview: `https://platform.claude.com/docs/en/models/opus-5/overview`
- Claude Opus 5 migration guide: `https://platform.claude.com/docs/en/models/opus-5/migration-guide`
- Models overview: `https://platform.claude.com/docs/en/models/overview`
- Choosing a model: `https://platform.claude.com/docs/en/about-claude/models/choosing-a-model`
- Model IDs and versioning: `https://platform.claude.com/docs/en/about-claude/models/model-ids-and-versions`
- Pricing: `https://platform.claude.com/docs/en/about-claude/pricing`
- Model deprecations: `https://platform.claude.com/docs/en/about-claude/model-deprecations`

Features that Opus 5 prompts depend on:

- Effort: `https://platform.claude.com/docs/en/build-with-claude/effort`
- Thinking: `https://platform.claude.com/docs/en/build-with-claude/thinking`
- Steering thinking and cost: `https://platform.claude.com/docs/en/build-with-claude/thinking-steering-and-cost`
- Task budgets: `https://platform.claude.com/docs/en/build-with-claude/task-budgets`
- Fast mode: `https://platform.claude.com/docs/en/build-with-claude/fast-mode`
- Mid-conversation system messages and tool changes: `https://platform.claude.com/docs/en/build-with-claude/mid-conversation-system-messages`
- Prompt caching: `https://platform.claude.com/docs/en/build-with-claude/prompt-caching`
- Compaction: `https://platform.claude.com/docs/en/build-with-claude/compaction`
- Context windows: `https://platform.claude.com/docs/en/build-with-claude/context-windows`
- Refusals and fallback: `https://platform.claude.com/docs/en/build-with-claude/refusals-and-fallback`
- Structured outputs: `https://platform.claude.com/docs/en/build-with-claude/structured-outputs`
- Strict tool use: `https://platform.claude.com/docs/en/agents-and-tools/tool-use/strict-tool-use`
- Tool use overview: `https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview`
- Computer use tool: `https://platform.claude.com/docs/en/agents-and-tools/tool-use/computer-use-tool`
- Batch processing: `https://platform.claude.com/docs/en/build-with-claude/batch-processing`
- Service tiers: `https://platform.claude.com/docs/en/api/service-tiers`
- Rate limits: `https://platform.claude.com/docs/en/api/rate-limits`
- Beta headers: `https://platform.claude.com/docs/en/api/beta-headers`
- Usage and Cost API: `https://platform.claude.com/docs/en/manage-claude/usage-cost-api`

Harness:

- Agent SDK subagent caps: `https://code.claude.com/docs/en/agent-sdk/subagents#cap-subagent-depth-concurrency-and-spend`
- Agent SDK overview: `https://code.claude.com/docs/en/agent-sdk/overview`
- Claude Managed Agents: `https://platform.claude.com/docs/en/managed-agents/overview`

## Beta headers to verify before recommending

| Feature | Header |
| --- | --- |
| Per-message effort | `mid-conversation-output-config-2026-07-01` |
| Mid-conversation tool changes | `mid-conversation-tool-changes-2026-07-01` |
| Task budgets | `task-budgets-2026-03-13` |
| Fast mode | `fast-mode-2026-02-01` |
| Server-side fallback, including `"default"` mode | `server-side-fallback-2026-07-01` |
| Server-side fallback, explicit lists only | `server-side-fallback-2026-06-01` |
| 300k output tokens on the Batch API | `output-300k-2026-03-24` |
| Progress updates via `thinking.display: "updates"` (Opus 5.5) | `thinking-display-updates-2026-08-18` |
| Turn-scoped system messages (`clear_at`) | `mid-conversation-system-clear-at-2026-08-21` |
| Thinking-block binding controls and `input_transformations` | `thinking-binding-controls-2026-08-01` |
| Tool definitions inside a mid-conversation message | `inline-tools-2026-09-15` |
| Compaction on demand | `compact-2026-09-04` |

Beta strings and availability change. Confirm each against the beta headers page or the feature guide before putting it in code.

## Harness identifiers to verify

| Purpose | Identifier |
| --- | --- |
| Subagent spawn depth cap | `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH` |
| Concurrent subagent cap | `CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS` |
| Agent SDK spend cap | `max_budget_usd` |
| Minimum Claude Code version for the above | 2.1.217 |
| System prompt preset that adds delegation guidance | `claude_code` |

## Research procedure

1. Open the target model's prompting page first (Opus 5.5 by default).
2. Open its what's-new and migration pages for parameters, breaking changes, and pricing.
3. Open the feature guide for anything you are about to configure.
4. Verify exact identifiers: model IDs, parameter names, accepted values, defaults, beta header strings, minimums, prices, restrictions.
5. Check code examples against the current SDK reference before returning code.
6. Cite the source beside the claim, and record the verification date in anything durable.

## Conflict and absence handling

- The model-specific prompting page beats the cross-model page, and the Opus 5.5 page beats the Opus 5 page for Opus 5.5 workloads.
- Platform docs beat the claude.dev playbook on API behavior; the playbook is authoritative only for app and Claude Code usage patterns. Where the playbook's example conflicts with a documented damper (its merge-blocking review filter versus report-everything), explain which applies to the user's case rather than choosing silently.
- A current what's-new or feature page beats an older migration article.
- A block on the best-practices page attributed to Opus 4.5 or 4.6 is a measurement on that model; several are amplifiers on Opus 5.
- Code examples using older model IDs demonstrate the feature, not the current default.
- Distinguish Claude API parameters from Claude Code, Agent SDK, claude.ai, and Managed Agents surface behavior. Task budgets, for instance, are Messages API only.
- A restriction documented for Fable 5.1 (forced tool use, sampling parameters) is not automatically an Opus 5 restriction. Verify separately rather than transferring it.
- If two official pages disagree, state the conflict rather than silently choosing.
- If nothing official confirms a parameter or behavior, mark it unverified and do not invent syntax.
