#!/usr/bin/env python3
"""Static check for Claude Fable API incompatibilities in harness code.

Scans source files for constructs that error, degrade, or silently break on
Claude Fable 5.2 and Claude Mythos 5.2 (most also apply to Fable 5.1).
Line-oriented regex matching: it finds candidates for a human to confirm, not
proof of a defect. Rules reflect Anthropic documentation read on 2026-11-16.

Findings are grouped by severity:
  error   documented 400 on Fable 5.2; the request will fail
  break   fails the prefix check (400 on Fable 5.2) or invalidates the cache
  degrade works, but produces a known bad behavior or cost
  info    worth confirming against the intended design

Usage:
  python fable_api_check.py agent.py client.ts
  python fable_api_check.py --format json src/
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
    ".cs", ".php", ".rs", ".kt", ".swift", ".json", ".yaml", ".yml", ".sh",
}

SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build",
    ".next", "target", ".mypy_cache", ".pytest_cache", "vendor",
}

FABLE_52_ID = re.compile(r"claude-(?:fable|mythos)-5-2", re.I)

# (code, severity, pattern, message)
CHECKS: list[tuple[str, str, re.Pattern[str], str]] = [
    (
        "forced_tool_use",
        "error",
        re.compile(
            r"tool_?choice[^\n]{0,80}?(?:[\"']any[\"']|[\"']?type[\"']?\s*[:=]\s*[\"']tool[\"'])",
            re.I,
        ),
        "tool_choice of type any or tool returns 400 invalid_request_error on Fable 5.2 and 5.1, "
        "on Messages and token counting. Use auto plus a prompt line naming the tool, strict: true, "
        "or JSON outputs (not available in CMEK organizations).",
    ),
    (
        "thinking_budget",
        "error",
        re.compile(r"budget_?tokens", re.I),
        "thinking.budget_tokens returns 400 on Fable. Control depth with effort; cap output with "
        "max_tokens.",
    ),
    (
        "thinking_type_rejected",
        "error",
        re.compile(
            r"[\"']?type[\"']?\s*[:=]\s*[\"'](?:enabled|disabled|between_tools)[\"'][^\n]{0,40}",
            re.I,
        ),
        "If this is a thinking config: enabled, disabled, and between_tools all return 400 on "
        "Fable 5.2. Omit thinking or send type adaptive. Ignore if this 'type' belongs to "
        "something else.",
    ),
    (
        "sampling_params",
        "error",
        re.compile(r"[\"']?\b(?:temperature|top_?p|top_?k)\b[\"']?\s*[:=]\s*[\d.]", re.I),
        "Sampling parameter set. On Fable, non-default values return 400, the top_p default is "
        "0.99 (so top_p 1 fails), temperature and top_p together fail, and from API version "
        "2026-10-21 any value returns 400 on every model. Remove it.",
    ),
    (
        "assistant_prefill",
        "error",
        re.compile(
            r"[\"']?role[\"']?\s*[:=]\s*[\"']assistant[\"'][^\n]{0,200}(?:partial|prefill|prefix)",
            re.I,
        ),
        "Prefilling the final assistant turn returns 400 on Fable. Use structured outputs, XML "
        "output tags, or a no-preamble instruction.",
    ),
    (
        "computer_tool_legacy",
        "error",
        re.compile(r"computer_20251124", re.I),
        "computer_20251124 returns 400 on Fable 5.2 and Mythos 5.2 everywhere except Amazon "
        "Bedrock. Declare the computer_toolset_20260801 toolset and update the agent loop.",
    ),
    (
        "history_mutation",
        "break",
        re.compile(
            r"messages\s*(?:\[[^\]]*\]\s*=|\.pop\(|\.shift\(|\.splice\(|\.insert\(|\.remove\(|"
            r"\.reverse\(|\.sort\()",
            re.I,
        ),
        "In-place mutation of the messages array. On Fable 5.2 a later request that sends thinking "
        "blocks back fails the prefix check with a 400 (bound to a different conversation). Keep "
        "history append-only; trim with compaction on demand or context editing.",
    ),
    (
        "system_rebuild",
        "break",
        re.compile(r"\bsystem\s*=\s*(?:f?[\"'`]|\[|build_|render_|make_|get_)", re.I),
        "The system prompt looks rebuilt per request (a date, a mode, an instruction file). If it "
        "changes mid-conversation, Fable 5.2 returns 400 on the next request with thinking blocks. "
        "Keep system fixed; append a role: system message or a text block with the new value.",
    ),
    (
        "tools_rebuild",
        "break",
        re.compile(r"\btools\s*=\s*(?:build_|render_|make_|get_|\[\s*\*|\[\s*\.\.\.)", re.I),
        "The tools array looks rebuilt per request. One reworded description is an edit. Declare "
        "tools once; add or remove them with tool_addition / tool_removal system messages.",
    ),
    (
        "reminder_injection",
        "break",
        re.compile(
            r"(?:reminder|nudge|system_?note|per_?turn)[^\n]{0,60}"
            r"(?:\.pop\(|\.remove\(|del |splice\(|filter\()",
            re.I,
        ),
        "A per-turn reminder appears to be injected and later removed. That is a history edit. Use "
        "a turn-scoped system message (clear_at: next_user_message) and leave it in messages.",
    ),
    (
        "thinking_blocks_stripped",
        "break",
        re.compile(
            r"(?:filter|reject|exclude|drop|strip)[^\n]{0,60}[\"']?thinking[\"']?"
            r"|type\s*[!=]=\s*[\"']thinking[\"']",
            re.I,
        ),
        "Thinking blocks look filtered out of assistant turns before replay. Send turns back "
        "exactly, including blocks with empty text. Leaving out the oldest, the newest, or all of "
        "them is allowed; a gap in between fails the prefix check.",
    ),
    (
        "drop_block_setting",
        "info",
        re.compile(r"drop_block", re.I),
        "prefix_mismatch_behavior drop_block avoids the 400 but makes the model re-think and spend "
        "more output tokens. Use it as a stopgap while fixing the edit, and log input_transformations.",
    ),
    (
        "display_omitted_with_loop",
        "degrade",
        re.compile(r"[\"']?display[\"']?\s*[:=]\s*[\"']omitted[\"']", re.I),
        "thinking.display is omitted (also the default), so progress-update blocks come back empty "
        "and long agentic turns look silent. Set updates (beta thinking-display-updates-2026-08-18) "
        "or summarized if a UI shows progress.",
    ),
    (
        "small_max_tokens",
        "degrade",
        re.compile(r"max_?tokens[\"']?\s*[:=]\s*(?:[1-9]\d{0,3})\b", re.I),
        "max_tokens under 10k. Thinking counts toward it, so Fable 5.2 can stop with stop_reason "
        "max_tokens after a thinking block and before any text. Set it large at high effort and "
        "above; ceiling is 128k.",
    ),
    (
        "blocking_subagent",
        "degrade",
        re.compile(
            r"(?:await|wait|join|gather|result\(\))[^\n]{0,40}"
            r"(?:subagent|sub_agent|child_agent|spawn|delegate)",
            re.I,
        ),
        "Subagent launch looks blocking. Letting the lead keep working while subagents run lowered "
        "time to completion at similar cost. Return immediately; deliver results in a later user "
        "message; give the lead a separate wait tool.",
    ),
    (
        "no_refusal_branch",
        "info",
        re.compile(r"stop_?reason", re.I),
        "stop_reason is inspected here. Confirm a refusal branch reads stop_details.category "
        "(cyber, bio, frontier_llm, reasoning_extraction, general_harms, null). Server-side "
        "fallback needs beta server-side-fallback-2026-07-01; Fable 5.2 targets are claude-opus-4-8 "
        "and claude-opus-5; reasoning_extraction is never retried.",
    ),
    (
        "context_countdown",
        "degrade",
        re.compile(
            r"(?:tokens_?remaining|remaining_?tokens|context_?remaining|budget_?remaining|"
            r"tokens_?left|percent_?context)",
            re.I,
        ),
        "A remaining-context or budget figure is computed here. If shown to the model, its size "
        "changes how much Fable 5.2 spends, and a countdown can trigger premature wrap-up. Test "
        "without it.",
    ),
    (
        "base64_into_context",
        "degrade",
        re.compile(r"(?:b64encode|base64\.(?:b64)?encode|toString\([\"']base64[\"']\)|btoa\()", re.I),
        "Base64 encoding near model input. Base64 in tool output was a documented false-positive "
        "trigger on Fable 5.1. Keep it out of the model's context.",
    ),
    (
        "earlier_fable_id",
        "info",
        re.compile(r"[\"'](?:claude-(?:fable|mythos)-5(?:-1)?)[\"']", re.I),
        "Earlier Fable or Mythos model ID. Confirm it is pinned on purpose; Fable 5.2 is "
        "claude-fable-5-2. Fable 5.1 cannot read Fable 5.2 thinking blocks.",
    ),
    (
        "legacy_model_id",
        "info",
        re.compile(
            r"[\"'](?:claude-(?:3|2)[^\"']*|claude-instant[^\"']*|"
            r"claude-(?:opus|sonnet|haiku)-4-[0-4][^\"']*)[\"']",
            re.I,
        ),
        "Legacy model ID. Confirm it is intentional rather than a missed migration.",
    ),
    (
        "short_timeout",
        "degrade",
        re.compile(r"(?:timeout|timeout_ms|request_timeout|deadline)[\"']?\s*[:=]\s*(?:[1-9]\d{0,2})\b", re.I),
        "Short client timeout. Fable requests on hard tasks can run for many minutes at higher "
        "effort. Confirm the unit and raise it, or check runs asynchronously.",
    ),
]

BETA_HEADERS = {
    "mid-conversation-output-config-2026-07-01": "per-message effort",
    "mid-conversation-system-clear-at-2026-08-21": "turn-scoped system messages",
    "thinking-display-updates-2026-08-18": "progress updates as text",
    "thinking-binding-controls-2026-08-01": "prefix-check controls",
    "server-side-fallback-2026-07-01": "server-side fallback",
    "inline-tools-2026-09-15": "mid-conversation tool changes",
}

# (marker, acceptable headers): any one header satisfies the marker.
FEATURE_MARKERS: list[tuple[re.Pattern[str], tuple[str, ...]]] = [
    (re.compile(r"clear_at", re.I), ("mid-conversation-system-clear-at-2026-08-21",)),
    (
        re.compile(r"[\"']?display[\"']?\s*[:=]\s*[\"']updates[\"']", re.I),
        ("thinking-display-updates-2026-08-18",),
    ),
    (re.compile(r"prefix_mismatch_behavior|block_binding", re.I), ("thinking-binding-controls-2026-08-01",)),
    (
        re.compile(r"[\"']?role[\"']?\s*[:=]\s*[\"']system[\"'][^\n]{0,120}output_config", re.I),
        ("mid-conversation-output-config-2026-07-01",),
    ),
    (re.compile(r"\bfallbacks[\"']?\s*[:=]", re.I), ("server-side-fallback-2026-07-01",)),
    (
        re.compile(r"tool_addition|tool_removal", re.I),
        ("inline-tools-2026-09-15", "mid-conversation-tool-changes-2026-07-01"),
    ),
]

ADVISOR_LINE = re.compile(r"advisor[^\n]{0,160}?[\"'](claude-[a-z0-9-]+)[\"']", re.I)
ADVISOR_OK = re.compile(r"^claude-(?:fable|mythos)-5-2$", re.I)
EFFORT_SET = re.compile(r"\beffort\b", re.I)
SUBAGENT_DEF = re.compile(r"AgentDefinition|\bagents\s*[:=]\s*\{", re.I)
SPEND_CAP = re.compile(r"max_?budget_?usd|maxBudgetUsd", re.I)


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


def finding(label: str, line: int, code: str, severity: str, message: str, excerpt: str = "") -> dict[str, Any]:
    return {
        "file": label,
        "line": line,
        "code": code,
        "severity": severity,
        "message": message,
        "excerpt": excerpt,
    }


def scan_text(text: str, label: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    lines = text.splitlines()
    for code, severity, pattern, message in CHECKS:
        for index, line in enumerate(lines, start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith(("#", "//", "*")):
                continue
            if pattern.search(line):
                findings.append(finding(label, index, code, severity, message, stripped[:160]))

    targets_52 = bool(FABLE_52_ID.search(text))

    # Advisor tool: a Fable 5.2 / Mythos 5.2 executor accepts only a 5.2 advisor.
    if targets_52:
        for index, line in enumerate(lines, start=1):
            match = ADVISOR_LINE.search(line)
            if match and not ADVISOR_OK.match(match.group(1)):
                findings.append(
                    finding(
                        label, index, "advisor_model", "error",
                        "With a Fable 5.2 or Mythos 5.2 executor, any advisor other than "
                        "claude-fable-5-2 or claude-mythos-5-2 returns 400. Change it in new "
                        "conversations: it is an edit to tools.",
                        line.strip()[:160],
                    )
                )

    # Effort left at the default after targeting Fable 5.2.
    if targets_52 and not EFFORT_SET.search(text):
        findings.append(
            finding(
                label, 0, "effort_unset", "info",
                "Fable 5.2 is targeted but effort is never set. The API default is high (Opus 5.5 "
                "defaults to medium), so traffic moved from Opus 5.5 runs one level higher. Set "
                "output_config.effort explicitly.",
            )
        )

    # Agent SDK subagents without a spend cap.
    if SUBAGENT_DEF.search(text) and not SPEND_CAP.search(text):
        findings.append(
            finding(
                label, 0, "subagents_uncapped", "info",
                "Subagents are defined but no spend cap (max_budget_usd / maxBudgetUsd) appears. "
                "Defaults are depth 3, 20 concurrent, no spend limit; a subagent without model "
                "inherits the parent's (Fable) model.",
            )
        )

    # Beta features used without a matching header anywhere in the file.
    for marker, headers in FEATURE_MARKERS:
        if marker.search(text) and not any(header in text for header in headers):
            names = " or ".join(headers)
            findings.append(
                finding(
                    label, 0, "missing_beta_header", "error",
                    f"Uses {BETA_HEADERS.get(headers[0], 'a beta feature')} but the beta header "
                    f"{names} was not found in this file. Confirm it is sent with the request.",
                )
            )
    return findings


SEVERITY_ORDER = {"error": 0, "break": 1, "degrade": 2, "info": 3}


def render_text(findings: list[dict[str, Any]], scanned: int) -> str:
    out = ["Fable API check", "==============="]
    out.append(f"Files scanned: {scanned} | Findings: {len(findings)}")
    if not findings:
        out.append("\nNo candidate incompatibilities found.")
        return "\n".join(out)

    labels = {
        "error": "ERROR - documented 400 on Fable 5.2",
        "break": "BREAK - fails the prefix check or invalidates the prompt cache",
        "degrade": "DEGRADE - known bad behavior or cost",
        "info": "INFO - confirm against intended design",
    }
    for severity in ("error", "break", "degrade", "info"):
        group = [f for f in findings if f["severity"] == severity]
        if not group:
            continue
        out.append(f"\n{labels[severity]}")
        for item in group:
            where = f"{item['file']}:{item['line']}" if item["line"] else item["file"]
            out.append(f"- [{item['code']}] {where}")
            if item["excerpt"]:
                out.append(f"    {item['excerpt']}")
            out.append(f"    -> {item['message']}")
    out.append(
        "\nRegex matching finds candidates, not proof. Confirm each against the code path that "
        "actually builds the request."
    )
    return "\n".join(out)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scan harness code for Claude Fable API incompatibilities."
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
