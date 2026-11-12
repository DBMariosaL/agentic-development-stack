#!/usr/bin/env python3
"""Static check for Claude Opus 5.5 and Opus 5 API and harness misconfiguration.

Scans source files for constructs that error, silently break, or degrade on
Claude Opus 5.5 or Claude Opus 5. Line-oriented regex matching: it finds
candidates for a human to confirm, not proof of a defect.

Model-aware: each file is scanned for model IDs. Checks scoped to Opus 5.5
(claude-opus-5-5) run only when that ID appears in the file, or when no model
ID appears at all (then they are reported as info, since the target is unknown).

Findings are grouped by severity:
  error   documented 400 or hard failure on the target model
  break   silently wrong after migration, or silently loses the prompt cache
  degrade works, but produces a known bad cost, latency, or output outcome
  info    worth confirming against the intended design

Usage:
  python opus_api_check.py agent.py client.ts
  python opus_api_check.py --format json --severity break src/
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterator

SOURCE_SUFFIXES = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".go", ".rb", ".java",
    ".cs", ".php", ".rs", ".kt", ".swift", ".json", ".yaml", ".yml", ".sh", ".env",
}

SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build",
    ".next", "target", ".mypy_cache", ".pytest_cache", "vendor",
}

# Scopes: "all" runs everywhere; "opus55" runs when claude-opus-5-5 is present
# (or no model ID is found, downgraded to info).
# (code, severity, pattern, message, scope)
CHECKS: list[tuple[str, str, re.Pattern[str], str, str]] = [
    (
        "thinking_disabled",
        "error",
        re.compile(r"[\"']?type[\"']?\s*[:=]\s*[\"']disabled[\"']", re.I),
        "If this is a thinking config: on Opus 5.5 thinking cannot be disabled and this returns a "
        "400 at every effort level. On Opus 5 it is accepted only at effort high or below (400 at "
        "xhigh or max) and leaks tool calls and internal XML tags. Remove the thinking field and "
        "lower effort instead.",
        "all",
    ),
    (
        "thinking_budget_tokens",
        "error",
        re.compile(r"budget_?[Tt]okens", re.I),
        "Manual thinking budget. thinking: {type: enabled, budget_tokens} returns a 400 on Opus 4.7 "
        "and later, Opus 5 and 5.5 included. Use adaptive thinking (or omit the field) and control "
        "depth with output_config.effort.",
        "all",
    ),
    (
        "sampling_params",
        "error",
        re.compile(r"[\"']?\b(?:temperature|top_p|top_k|topP|topK)\b[\"']?\s*[:=]\s*[0-9.]", re.I),
        "Sampling parameter. Any non-default temperature, top_p, or top_k returns a 400 on Opus 4.7 "
        "and later, Opus 5 and 5.5 included. Omit it and steer with the prompt.",
        "all",
    ),
    (
        "forced_tool_choice",
        "error",
        re.compile(
            r"tool_?[Cc]hoice[^\n]{0,40}[\"']?type[\"']?\s*[:=]\s*[\"'](?:any|tool)[\"']", re.I
        ),
        "Forced tool use. On Opus 5.5, tool_choice type any or tool returns a 400 (also on token "
        "counting). Use tool_choice auto with strict: true, or structured outputs, and say in the "
        "prompt when the tool applies.",
        "opus55",
    ),
    (
        "legacy_computer_tool",
        "error",
        re.compile(r"computer_20251124|computer-use-2025-11-24", re.I),
        "Legacy computer use tool. On Opus 5.5 via the Claude API or Google Cloud, computer_20251124 "
        "returns a 400. Use {type: computer_toolset_20260801}, drop the beta header, and handle "
        "member tool_use blocks and toolset_name. Bedrock still accepts the old tool.",
        "opus55",
    ),
    (
        "prefill",
        "error",
        re.compile(
            r"[\"']?role[\"']?\s*[:=]\s*[\"']assistant[\"'][^\n]{0,200}(?:partial|prefill|prefix)",
            re.I,
        ),
        "Assistant prefill on the last turn is unsupported from the 4.6 generation onward and "
        "returns a 400. Use structured outputs, XML output tags, or a no-preamble instruction.",
        "all",
    ),
    (
        "task_budget_below_minimum",
        "error",
        re.compile(r"[\"']?total[\"']?\s*[:=]\s*(?:[1-9]\d{0,3}|1[0-9]\d{3})\b"),
        "If this is task_budget.total: the minimum accepted value is 20,000 tokens on every model "
        "that supports task budgets. Smaller values return a 400.",
        "all",
    ),
    (
        "content_zero_text",
        "break",
        re.compile(
            r"content\s*\[\s*0\s*\]\s*(?:\.\s*text|\[\s*[\"']text[\"']\s*\])"
            r"|content\s*\.\s*(?:first|\[0\])\s*\.\s*text",
            re.I,
        ),
        "Reading content[0].text. On Opus 5 and 5.5 thinking is on, so a response can begin "
        "with thinking blocks before the first text block. Select content blocks by their type "
        "field instead.",
        "all",
    ),
    (
        "first_stream_block_as_text",
        "break",
        re.compile(r"content_block_start[^\n]{0,80}(?:index\s*[=:]{1,2}\s*0|\[0\])", re.I),
        "Treating the first streamed content block as text. On Opus 5 the first block is often a "
        "thinking block. Branch on the block type.",
        "all",
    ),
    (
        "thinking_blocks_stripped",
        "break",
        re.compile(
            r"(?:filter|reject|exclude|drop|strip)[^\n]{0,60}[\"']?thinking[\"']?"
            r"|type\s*[!=]=\s*[\"']thinking[\"']",
            re.I,
        ),
        "Thinking blocks look filtered out before replay, or skipped when rendering. Tool-use "
        "loops must pass thinking blocks back complete and unmodified. On Opus 5.5, progress "
        "updates between tool calls also arrive as thinking blocks: a UI that skips them goes "
        "silent (set thinking.display to updates and render non-empty blocks).",
        "all",
    ),
    (
        "top_level_effort_mutated",
        "break",
        re.compile(
            r"(?:output_config|outputConfig)[^\n]{0,60}effort[\"']?\s*[:=]\s*(?:[a-z_]+\s*[?(]|\$\{|"
            r"[a-z_]+\.[a-z_]+|[a-z_]+\s*\})",
            re.I,
        ),
        "Top-level effort looks computed per request. Changing it between requests does not "
        "preserve cached prefixes. Use per-message effort (beta "
        "mid-conversation-output-config-2026-07-01), which keeps the cache.",
        "all",
    ),
    (
        "remaining_decremented",
        "break",
        re.compile(r"[\"']?remaining[\"']?\s*[:=][^\n]{0,60}[-]\s*(?:tokens|spent|used|[a-z_]+)", re.I),
        "task_budget.remaining looks decremented client-side. If you also resend full history, the "
        "model sees an under-reported budget and wraps up early; the changed value also "
        "invalidates any cache prefix containing it. Pass remaining only when your own code "
        "rewrites history.",
        "all",
    ),
    (
        "small_max_tokens",
        "degrade",
        re.compile(r"max_?tokens[\"']?\s*[:=]\s*(?:[1-9]\d{0,3})\b", re.I),
        "max_tokens under ~10k. It must cover thinking plus the reply. At xhigh or max effort, "
        "start at 64k; on Opus 5.5, which thinks more per turn, 128k worked well for agentic "
        "coding. Reaching it truncates with stop_reason max_tokens.",
        "all",
    ),
    (
        "high_effort_small_budget",
        "degrade",
        re.compile(r"effort[\"']?\s*[:=]\s*[\"']?(?:xhigh|max)[\"']?", re.I),
        "Running at xhigh or max effort. Confirm max_tokens is at least 64k and that no request "
        "disables thinking. On Opus 5.5, reserve these levels for measured gains: each level "
        "thinks more per turn than on Opus 5.",
        "all",
    ),
    (
        "uncapped_subagents",
        "degrade",
        re.compile(r"(?:spawn|launch|create)_?(?:sub_?agent|agent)|Task\s*\(|subagent_type", re.I),
        "Subagent spawning. Opus 5 delegates readily; Opus 5.5 runs long fan-outs well. Confirm a "
        "prompt rule naming which scenarios "
        "qualify, plus deterministic caps: CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH, "
        "CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS, or the SDK max_budget_usd (Claude Code 2.1.217+).",
        "all",
    ),
    (
        "fast_mode_no_fallback",
        "degrade",
        re.compile(r"[\"']?speed[\"']?\s*[:=]\s*[\"']fast[\"']", re.I),
        "Fast mode is enabled. It costs double the model rate ($8/$40 per MTok on Opus 5.5, "
        "$10/$50 on Opus 5), has dedicated rate limits that "
        "return 429, is Claude API only, and switching speeds invalidates the cache. Confirm a "
        "fallback path to standard speed and that latency justifies the price.",
        "all",
    ),
    (
        "legacy_verification_stage",
        "degrade",
        re.compile(
            r"(?:verification|verify|double_?check|self_?check)_?(?:step|stage|pass|phase|agent|prompt)",
            re.I,
        ),
        "A separate verification stage. Opus 5 and 5.5 verify their own work unprompted; legacy "
        "verification scaffolding causes over-verification and wasted tokens with no quality gain.",
        "all",
    ),
    (
        "legacy_model_id",
        "info",
        re.compile(
            r"[\"'](?:claude-(?:3|2)[^\"']*|claude-instant[^\"']*|"
            r"claude-opus-4-[0-8][^\"']*|claude-sonnet-4-[0-6][^\"']*|claude-opus-5)[\"']",
            re.I,
        ),
        "Older model ID. Confirm it is intentional (a pinned baseline or fallback target) rather "
        "than a missed migration; Anthropic now starts most workloads on claude-opus-5-5. A "
        "fallback from Opus 5.5 to any model but Fable 5.1 or Mythos 5.1 drops its thinking.",
        "all",
    ),
    (
        "refusal_branch",
        "info",
        re.compile(r"stop_?reason", re.I),
        "stop_reason is inspected here. Confirm the refusal branch reads stop_details.category "
        "(Opus 5.5 adds bio and reasoning_extraction to cyber) and fallbacks are configured (beta "
        "server-side-fallback-2026-07-01 supports \"default\"; reasoning_extraction is never "
        "retried). On Opus 5.5 unattended loops, also confirm a text-only end_turn is not treated "
        "as task completion.",
        "all",
    ),
    (
        "priority_tier",
        "info",
        re.compile(r"service_?tier|priority[_-]?tier", re.I),
        "Service tier reference. Priority Tier is not supported on Opus 5 or 5.5, and fast mode is not "
        "available with a Priority Tier commitment.",
        "all",
    ),
]

BETA_HEADERS = {
    "mid-conversation-output-config-2026-07-01": "per-message effort",
    "mid-conversation-tool-changes-2026-07-01": "mid-conversation tool changes",
    "task-budgets-2026-03-13": "task budgets",
    "fast-mode-2026-02-01": "fast mode",
    "server-side-fallback-2026-07-01": "server-side fallback with default mode",
    "output-300k-2026-03-24": "300k output tokens on the Batch API",
    "thinking-display-updates-2026-08-18": "thinking.display updates",
    "mid-conversation-system-clear-at-2026-08-21": "turn-scoped system messages (clear_at)",
    "thinking-binding-controls-2026-08-01": "thinking-block binding controls",
}

FEATURE_MARKERS = [
    (re.compile(r"task_?budget|taskBudget", re.I), "task-budgets-2026-03-13"),
    (re.compile(r"[\"']?speed[\"']?\s*[:=]\s*[\"']fast[\"']", re.I), "fast-mode-2026-02-01"),
    (
        re.compile(r"[\"']?role[\"']?\s*[:=]\s*[\"']system[\"'][^\n]{0,120}output_?[Cc]onfig", re.I),
        "mid-conversation-output-config-2026-07-01",
    ),
    (re.compile(r"[\"']?fallbacks[\"']?\s*[:=]\s*[\"']default[\"']", re.I), "server-side-fallback-2026-07-01"),
    (re.compile(r"[\"']?display[\"']?\s*[:=]\s*[\"']updates[\"']", re.I), "thinking-display-updates-2026-08-18"),
    (re.compile(r"clear_?[Aa]t", re.I), "mid-conversation-system-clear-at-2026-08-21"),
    (re.compile(r"prefix_mismatch_behavior|block_binding", re.I), "thinking-binding-controls-2026-08-01"),
]

OPUS55_ID = re.compile(r"claude-opus-5-5|anthropic\.claude-opus-5-5", re.I)
ANY_MODEL_ID = re.compile(r"claude-[a-z0-9.-]+|anthropic\.claude", re.I)
EFFORT_SET = re.compile(r"[\"']?effort[\"']?\s*[:=]", re.I)
DISPLAY_SET = re.compile(r"[\"']?display[\"']?\s*[:=]", re.I)
AGENTIC_MARKER = re.compile(r"tool_use|tool_result|stop_reason", re.I)

SEVERITY_ORDER = {"error": 0, "break": 1, "degrade": 2, "info": 3}


def iter_files(paths: list[str]) -> Iterator[Path]:
    for raw in paths:
        path = Path(raw)
        if path.is_file():
            yield path
        elif path.is_dir():
            for child in sorted(path.rglob("*")):
                if not child.is_file():
                    continue
                if any(part in SKIP_DIRS for part in child.parts):
                    continue
                if child.suffix.lower() in SOURCE_SUFFIXES:
                    yield child
        else:
            print(f"warning: not found: {raw}", file=sys.stderr)


def scan_text(text: str, label: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    lines = text.splitlines()
    is_opus55 = bool(OPUS55_ID.search(text))
    model_unknown = not ANY_MODEL_ID.search(text)
    for code, severity, pattern, message, scope in CHECKS:
        if scope == "opus55":
            if is_opus55:
                pass
            elif model_unknown:
                severity = "info"
                message = "[target model unknown; applies if this runs on claude-opus-5-5] " + message
            else:
                continue
        for index, line in enumerate(lines, start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith(("#", "//", "*")):
                continue
            if pattern.search(line):
                findings.append(
                    {
                        "file": label,
                        "line": index,
                        "code": code,
                        "severity": severity,
                        "message": message,
                        "excerpt": stripped[:160],
                    }
                )
    if is_opus55 and not EFFORT_SET.search(text):
        findings.append(
            {
                "file": label,
                "line": 0,
                "code": "opus55_effort_omitted",
                "severity": "degrade",
                "message": (
                    "claude-opus-5-5 is used but no effort value was found in this file. The default "
                    "on Opus 5.5 is medium (Opus 5 defaulted to high). Set effort explicitly and "
                    "choose it from a sweep."
                ),
                "excerpt": "",
            }
        )
    if is_opus55 and AGENTIC_MARKER.search(text) and not DISPLAY_SET.search(text):
        findings.append(
            {
                "file": label,
                "line": 0,
                "code": "opus55_progress_updates_hidden",
                "severity": "info",
                "message": (
                    "Agentic loop on claude-opus-5-5 with no thinking.display setting found. Text "
                    "between tool calls now arrives as progress-update thinking blocks, empty at the "
                    "default display omitted. If users watch the run, set display: updates (beta "
                    "thinking-display-updates-2026-08-18) and render those blocks."
                ),
                "excerpt": "",
            }
        )
    for marker, header in FEATURE_MARKERS:
        if marker.search(text) and header not in text:
            findings.append(
                {
                    "file": label,
                    "line": 0,
                    "code": "missing_beta_header",
                    "severity": "error",
                    "message": (
                        f"Uses {BETA_HEADERS[header]} but the beta header {header} was not found in "
                        "this file. Confirm it is sent with the request."
                    ),
                    "excerpt": "",
                }
            )
    return findings


def render_text(findings: list[dict[str, Any]], scanned: int) -> str:
    out = ["Opus 5.5 / Opus 5 API check", "==========================="]
    out.append(f"Files scanned: {scanned} | Findings: {len(findings)}")
    if not findings:
        out.append("\nNo candidate misconfigurations found.")
        return "\n".join(out)

    labels = {
        "error": "ERROR - documented 400 or hard failure",
        "break": "BREAK - silently wrong after migration, or loses the cache",
        "degrade": "DEGRADE - known bad cost, latency, or output outcome",
        "info": "INFO - confirm against intended design",
    }
    for severity in ("error", "break", "degrade", "info"):
        group = [f for f in findings if f["severity"] == severity]
        if not group:
            continue
        out.append(f"\n{labels[severity]}")
        for finding in group:
            where = f"{finding['file']}:{finding['line']}" if finding["line"] else finding["file"]
            out.append(f"- [{finding['code']}] {where}")
            if finding["excerpt"]:
                out.append(f"    {finding['excerpt']}")
            out.append(f"    -> {finding['message']}")
    out.append(
        "\nRegex matching finds candidates, not proof. Confirm each against the code path that "
        "actually builds the request."
    )
    return "\n".join(out)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scan harness code for Claude Opus 5.5 and Opus 5 API and configuration problems."
    )
    parser.add_argument("paths", nargs="+", help="Files or directories to scan.")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument(
        "--severity",
        choices=("error", "break", "degrade", "info"),
        default="info",
        help="Minimum severity to report (default: info, i.e. everything).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    threshold = SEVERITY_ORDER[args.severity]
    findings: list[dict[str, Any]] = []
    scanned = 0

    for path in iter_files(args.paths):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            print(f"warning: {exc}", file=sys.stderr)
            continue
        scanned += 1
        findings.extend(scan_text(text, str(path)))

    findings = [f for f in findings if SEVERITY_ORDER[f["severity"]] <= threshold]
    findings.sort(key=lambda f: (SEVERITY_ORDER[f["severity"]], f["file"], f["line"]))

    if args.format == "json":
        print(json.dumps({"files_scanned": scanned, "findings": findings}, ensure_ascii=False, indent=2))
    else:
        print(render_text(findings, scanned))

    return 1 if any(f["severity"] in ("error", "break") for f in findings) else 0


if __name__ == "__main__":
    raise SystemExit(main())
