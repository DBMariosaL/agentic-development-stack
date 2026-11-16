#!/usr/bin/env python3
"""Static check for Claude Fable API incompatibilities in harness code.

Scans source files for constructs that error, degrade, or silently break on
Claude Fable 5.1 and Claude Mythos 5.1. Line-oriented regex matching: it finds
candidates for a human to confirm, not proof of a defect.

Findings are grouped by severity:
  error   documented 400 on Fable; the request will fail
  break   silently invalidates thinking blocks or the prompt cache
  degrade works, but produces a known bad user-visible behavior
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

# (code, severity, pattern, message)
CHECKS: list[tuple[str, str, re.Pattern[str], str]] = [
    (
        "forced_tool_use",
        "error",
        re.compile(
            r"tool_?choice[^\n]{0,80}?(?:[\"']any[\"']|[\"']?type[\"']?\s*[:=]\s*[\"']tool[\"'])",
            re.I,
        ),
        "tool_choice of type any or tool returns 400 invalid_request_error on Fable 5.1. Use "
        "auto plus an explicit prompt line, strict tool use (strict: true), or structured outputs.",
    ),
    (
        "thinking_budget",
        "error",
        re.compile(r"budget_?tokens", re.I),
        "thinking.budget_tokens returns 400 on Fable. Control depth with effort; cap output with "
        "max_tokens.",
    ),
    (
        "thinking_enabled_or_disabled",
        "error",
        re.compile(r"[\"']?type[\"']?\s*[:=]\s*[\"'](?:enabled|disabled)[\"'][^\n]{0,40}", re.I),
        "If this is a thinking config: type enabled (with budget) and type disabled both return "
        "400 on Fable. Omit thinking or send type adaptive. Ignore if this 'type' belongs to "
        "something else.",
    ),
    (
        "sampling_params",
        "error",
        re.compile(
            r"\b(?:temperature|top_?p|top_?k)[\"']?\s*[:=]\s*(?!1(?:\.0+)?\b)(?:0?\.\d+|[02-9]\d*)",
            re.I,
        ),
        "Non-default temperature, top_p, or top_k returns 400 on Fable.",
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
        "history_mutation",
        "break",
        re.compile(
            r"messages\s*(?:\[[^\]]*\]\s*=|\.pop\(|\.shift\(|\.splice\(|\.insert\(|\.remove\(|"
            r"\.reverse\(|\.sort\()",
            re.I,
        ),
        "In-place mutation of the messages array. Editing earlier turns invalidates every later "
        "thinking block on Fable 5.1 and restarts the prompt cache. Keep history append-only.",
    ),
    (
        "system_rebuild",
        "break",
        re.compile(r"\bsystem\s*=\s*(?:f?[\"'`]|\[|build_|render_|make_|get_)", re.I),
        "The system prompt looks rebuilt per request. If its bytes change mid-conversation, later "
        "thinking blocks are invalidated. Use a mid-conversation system message for changes.",
    ),
    (
        "tools_rebuild",
        "break",
        re.compile(r"\btools\s*=\s*(?:build_|render_|make_|get_|\[\s*\*|\[\s*\.\.\.)", re.I),
        "The tools array looks rebuilt per request. Changing it mid-conversation invalidates later "
        "thinking blocks. Use a mid-conversation tool change instead.",
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
        "a turn-scoped system message (clear_at: next_user_message).",
    ),
    (
        "thinking_blocks_stripped",
        "break",
        re.compile(
            r"(?:filter|reject|exclude|drop|strip)[^\n]{0,60}[\"']?thinking[\"']?"
            r"|type\s*[!=]=\s*[\"']thinking[\"']",
            re.I,
        ),
        "Thinking blocks look filtered out of assistant turns before replay. Pass assistant turns "
        "back exactly as returned. Stripping is only safe for a leading run, oldest first, or when "
        "you replay no thinking blocks at all after a client-side summary.",
    ),
    (
        "display_omitted_with_loop",
        "degrade",
        re.compile(r"[\"']?display[\"']?\s*[:=]\s*[\"']omitted[\"']", re.I),
        "thinking.display is omitted, so progress-update blocks come back empty and long agentic "
        "turns look silent. Set updates (beta thinking-display-updates-2026-08-18) or summarized "
        "if your UI shows progress.",
    ),
    (
        "small_max_tokens",
        "degrade",
        re.compile(r"max_?tokens[\"']?\s*[:=]\s*(?:[1-9]\d{0,3})\b", re.I),
        "max_tokens under ~10k. On Fable it must cover thinking plus the reply, not the reply "
        "alone; long deliverables truncate. Ceiling is 128k.",
    ),
    (
        "blocking_subagent",
        "degrade",
        re.compile(
            r"(?:await|wait|join|gather|result\(\))[^\n]{0,40}"
            r"(?:subagent|sub_agent|child_agent|spawn|delegate)",
            re.I,
        ),
        "Subagent launch looks blocking. Letting the lead keep working while subagents run lowers "
        "time to completion at similar quality and cost. Return immediately; deliver results in a "
        "later user message; give the lead a separate wait tool.",
    ),
    (
        "no_refusal_branch",
        "info",
        re.compile(r"stop_?reason", re.I),
        "stop_reason is inspected here. Confirm the refusal branch exists: Fable can return "
        "stop_reason refusal with a stop_details object. Permitted fallback targets are Claude "
        "Opus 4.8 and Claude Opus 5.",
    ),
    (
        "context_countdown",
        "degrade",
        re.compile(
            r"(?:tokens_?remaining|remaining_?tokens|context_?remaining|budget_?remaining|"
            r"tokens_?left|percent_?context)",
            re.I,
        ),
        "A remaining-context figure is computed here. If it is shown to the model, it triggers "
        "premature wrap-up and new-session suggestions. Keep it out of the prompt, or pair it with "
        "the ample-context reassurance.",
    ),
    (
        "base64_into_context",
        "degrade",
        re.compile(r"(?:b64encode|base64\.(?:b64)?encode|toString\([\"']base64[\"']\)|btoa\()", re.I),
        "Base64 encoding near model input. Base64 in tool output can trigger safety-classifier "
        "false positives on Fable. Remove it from the model's context.",
    ),
    (
        "legacy_model_id",
        "info",
        re.compile(
            r"[\"'](?:claude-(?:3|2)[^\"']*|claude-instant[^\"']*|"
            r"claude-(?:opus|sonnet|haiku)-4-[0-4][^\"']*)[\"']",
            re.I,
        ),
        "Legacy model ID. Confirm it is intentional (a fallback target, for example) rather than a "
        "missed migration.",
    ),
    (
        "short_timeout",
        "degrade",
        re.compile(r"(?:timeout|timeout_ms|request_timeout|deadline)[\"']?\s*[:=]\s*(?:[1-9]\d{0,2})\b", re.I),
        "Short client timeout. Fable requests on hard tasks can run for many minutes at higher "
        "effort. Confirm the unit and raise it, or restructure to check runs asynchronously.",
    ),
]

BETA_HEADERS = {
    "mid-conversation-output-config-2026-07-01": "per-message effort",
    "mid-conversation-system-clear-at-2026-08-21": "turn-scoped system messages",
    "thinking-display-updates-2026-08-18": "progress updates as text",
    "thinking-binding-controls-2026-08-01": "thinking block binding controls",
}

FEATURE_MARKERS = [
    (re.compile(r"clear_at", re.I), "mid-conversation-system-clear-at-2026-08-21"),
    (re.compile(r"[\"']?display[\"']?\s*[:=]\s*[\"']updates[\"']", re.I), "thinking-display-updates-2026-08-18"),
    (re.compile(r"prefix_mismatch_behavior|block_binding", re.I), "thinking-binding-controls-2026-08-01"),
    (
        re.compile(r"[\"']?role[\"']?\s*[:=]\s*[\"']system[\"'][^\n]{0,120}output_config", re.I),
        "mid-conversation-output-config-2026-07-01",
    ),
]


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
    for code, severity, pattern, message in CHECKS:
        for index, line in enumerate(lines, start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith(("#", "//", "*")):
                continue
            match = pattern.search(line)
            if match:
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
    # Beta features used without the matching header anywhere in the file.
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


SEVERITY_ORDER = {"error": 0, "break": 1, "degrade": 2, "info": 3}


def render_text(findings: list[dict[str, Any]], scanned: int) -> str:
    out = ["Fable API check", "==============="]
    out.append(f"Files scanned: {scanned} | Findings: {len(findings)}")
    if not findings:
        out.append("\nNo candidate incompatibilities found.")
        return "\n".join(out)

    labels = {
        "error": "ERROR - documented 400 on Fable",
        "break": "BREAK - invalidates thinking blocks or the prompt cache",
        "degrade": "DEGRADE - known bad behavior",
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
