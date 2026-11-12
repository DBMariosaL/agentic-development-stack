#!/usr/bin/env python3
"""Deterministic prompt linter for Claude Opus 5.5 and Opus 5 prompts.

This script does not judge prompt quality. It flags instructions that amplify a
behavior the model already has (thinking, verification, self-correction,
delegation, narration, progress updates), instructions that self-limit output
the model would otherwise produce, Opus 5.5 refusal risks, missing done
criteria and stop rules on agentic prompts, and generic contract gaps, for
human review. Works on system prompts, CLAUDE.md files, and skills.

Three warning classes:
  amplifier_*  duplicates a built-in behavior; usually a deletion
  opus_*       Opus 5.5 / Opus 5-specific problem expressed in prompt text
  generic_*    contract and structure gaps that apply to any model

Usage:
  python prompt_lint.py prompt.md
  python prompt_lint.py --format json prompt.md
  cat prompt.md | python prompt_lint.py
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

# --- Amplifiers: instructions that double a built-in Opus 5.5 / 5 behavior ----
# (pattern, code, message)

AMPLIFIER_PATTERNS: list[tuple[re.Pattern[str], str, str]] = [
    (
        re.compile(
            r"\b(?:(?:final|explicit|separate|additional)\s+verification\s+step"
            r"|verification\s+(?:step|stage|pass|phase)"
            r"|verify\s+your\s+(?:work|answer|output|results?)"
            r"|(?:use|spawn|launch)\s+(?:a\s+)?sub-?agents?\s+to\s+(?:verify|check|review\s+your)"
            r"|self[- ]verif)",
            re.I,
        ),
        "amplifier_verification",
        "Verification instruction. Opus 5.5 and Opus 5 verify their own work unprompted; this causes "
        "over-verification and wasted tokens with no quality gain. Delete it - do not soften it. "
        "Running named tests or linters is external validation and is fine to keep.",
    ),
    (
        re.compile(
            r"\b(?:double[- ]check"
            r"|re-?verify"
            r"|re-?check"
            r"|check\s+your\s+(?:work|answer|output)\s+(?:again|before)"
            r"|review\s+your\s+(?:own\s+)?(?:answer|response|work)\s+before"
            r"|make\s+sure\s+to\s+verify)",
            re.I,
        ),
        "amplifier_double_check",
        "Double-check or re-verify instruction. Opus 5.5 and 5 catch and fix their own mistakes well; "
        "this compounds with that behavior and adds cost without improving results. It also "
        "manufactures the correction narration a correction-limiter would suppress.",
    ),
    (
        re.compile(
            r"\b(?:delegate\s+(?:aggressively|liberally|freely|whenever|as\s+much)"
            r"|use\s+sub-?agents?\s+(?:aggressively|liberally|whenever\s+possible|where\s+possible|"
            r"as\s+much\s+as)"
            r"|prefer\s+(?:to\s+)?delegat"
            r"|spawn\s+(?:as\s+many|multiple)\s+sub-?agents)",
            re.I,
        ),
        "amplifier_delegation",
        "Delegation encouragement. Opus 5 already delegates readily (Opus 5.5 runs fan-outs well); this multiplies cost and "
        "wall-clock on small tasks. Replace with a rule naming which scenarios qualify, and add "
        "deterministic caps where the harness supports them.",
    ),
    (
        re.compile(
            r"\b(?:(?:explain|describe|narrate|announce|tell\s+(?:me|the\s+user))\s+"
            r"(?:what|each\s+step|every\s+step)[^.\n]{0,40}(?:you(?:'re| are)?\s+doing|as\s+you\s+(?:work|go))"
            r"|provide\s+(?:detailed|frequent|regular)\s+(?:updates|commentary|narration)"
            r"|keep\s+(?:me|the\s+user)\s+informed\s+at\s+(?:every|each))",
            re.I,
        ),
        "amplifier_narration",
        "Narration request. Opus 5 narrates readily in agentic sessions and per-message output is "
        "already longer than prior models'. If narration is heavy, delete this and add a cadence "
        "instruction instead.",
    ),
    (
        re.compile(
            r"\b(?:do\s+not\s+(?:think|reason)\b"
            r"|don'?t\s+(?:think|reason)\b"
            r"|no\s+(?:thinking|reasoning)\s+(?:blocks?|steps?|out\s+loud)"
            r"|skip\s+(?:the\s+)?(?:thinking|reasoning)"
            r"|avoid\s+(?:thinking|reasoning)\s+(?:before|about))",
            re.I,
        ),
        "amplifier_no_thinking",
        "A do-not-think rule. With thinking disabled this increases <thinking> tag leakage into "
        "visible output; with thinking enabled it is inert. Remove it either way.",
    ),
    (
        re.compile(
            r"\b(?:think\s+(?:very\s+)?(?:carefully|hard(?:er)?|deeply|thoroughly|step[- ]by[- ]step)"
            r"|take\s+your\s+time\s+(?:to\s+)?think"
            r"|let'?s\s+think\s+step\s+by\s+step"
            r"|reason\s+(?:carefully|step[- ]by[- ]step)\s+before)",
            re.I,
        ),
        "amplifier_think_instruction",
        "Thinking instruction. Opus 5.5 always thinks before replying and decides how much; in "
        "Anthropic's chat testing, deleting such a line made replies start sooner with no clear "
        "quality loss. Delete it. Control depth with effort; for quick answers say 'Answer directly.'",
    ),
    (
        re.compile(
            r"\b(?:after\s+(?:every|each)\s+\d+\s+(?:tool\s+calls?|steps?|actions?)"
            r"|every\s+\d+\s+(?:tool\s+calls?|steps?)[^.\n]{0,40}(?:summar|update|report)"
            r"|(?:summarize|report)\s+(?:your\s+)?progress\s+(?:every|after\s+each|regularly))",
            re.I,
        ),
        "amplifier_progress_scaffolding",
        "Forced progress-summary scaffolding. Opus 5.5 and 5 write progress updates between tool "
        "calls on their own. Delete it; if updates are too rare, describe the cadence you want "
        "(intent before the first tool call, recap at the end) or add a harness reminder.",
    ),
    (
        re.compile(
            r"\b(?:be\s+(?:accurate|thorough|smart|intelligent|careful|meticulous)"
            r"|take\s+your\s+time"
            r"|use\s+all\s+available\s+tools"
            r"|if\s+in\s+doubt,?\s+use)",
            re.I,
        ),
        "amplifier_inert_directive",
        "Directive with no observable contract. Inert at best on Opus 5, and causes overthinking "
        "or tool overtriggering at worst. Replace with a trigger condition or an acceptance "
        "criterion.",
    ),
]

# --- Opus 5.5 / Opus 5-specific prompt-level problems ----------------------

OPUS_PATTERNS: list[tuple[re.Pattern[str], str, str]] = [
    (
        re.compile(
            r"\b(?:only\s+report\s+(?:high|critical|severe|major|significant)"
            r"|report\s+only\s+(?:high|critical|severe|major|the\s+most)"
            r"|be\s+conservative\b"
            r"|(?:ignore|skip|omit|don'?t\s+(?:report|mention|flag))\s+(?:minor|small|nit|low[- ]severity|"
            r"trivial)"
            r"|filter\s+out\s+(?:minor|low)"
            r"|limit\s+(?:yourself\s+)?to\s+(?:the\s+)?(?:top\s+)?\d+\s+(?:issues|findings|bugs))",
            re.I,
        ),
        "opus_self_limiting_report",
        "Self-limiting reporting instruction. The model follows this literally and reports less. "
        "If the output feeds recall-sensitive work, ask for everything at every severity and "
        "filter separately. Keep it only if the filter is the real acceptance criterion (e.g. "
        "'problems you'd block the merge for' for a human reviewer).",
    ),
    (
        re.compile(
            r"\b(?:(?:show|include|output|write\s+out|print|reproduce|reveal|display|share)\s+"
            r"(?:me\s+)?(?:all\s+)?(?:your|the)\s+(?:full\s+|complete\s+|internal\s+|raw\s+)?"
            r"(?:reasoning|chain[- ]of[- ]thought|thought\s+process|thinking|scratchpad)"
            r"|explain\s+your\s+reasoning\s+step[- ]by[- ]step"
            r"|(?:reasoning|chain[- ]of[- ]thought|thinking)\s+(?:in|inside)\s+(?:the|your)\s+"
            r"(?:response|reply|answer|output)"
            r"|<(?:reasoning|scratchpad|chain_of_thought)>)",
            re.I,
        ),
        "opus_reasoning_extraction",
        "Asks the model to reproduce its reasoning in the reply. On Opus 5.5 this can be declined "
        "with the reasoning_extraction refusal category, which server-side fallback never retries. "
        "Ask for a bounded rationale instead ('Explain why you chose this approach in three "
        "sentences'), or read summarized thinking blocks (display: summarized).",
    ),
    (
        re.compile(
            r"\b(?:(?:avoid|don'?t\s+(?:use|make\s+it\s+look)|no)\s+(?:a\s+)?"
            r"(?:generic|ai[- ]looking|cookie[- ]cutter|templat(?:e|ed)|bland|default)\s*"
            r"(?:ai\s+)?(?:look|design|aesthetic|style|feel)"
            r"|make\s+it\s+(?:look\s+)?(?:unique|original|not\s+generic))",
            re.I,
        ),
        "opus_vague_design_exclusion",
        "Generic design exclusion. On Opus 5.5 'avoid a generic look' mostly swaps one default "
        "style for another. Name the specific patterns to leave out (e.g. cream background, "
        "italic accent words, '01/02/03' labels, monospace labels, pill buttons) and iterate.",
    ),
    (
        re.compile(
            r"\b(?:lower(?:ing)?\s+(?:the\s+)?effort[^.\n]{0,60}(?:shorter|brief|concise|length)"
            r"|(?:shorter|brief|concise)[^.\n]{0,60}\blower(?:ing)?\s+(?:the\s+)?effort"
            r"|effort\s*[:=]\s*[\"']?(?:low|medium)[\"']?[^.\n]{0,60}(?:shorter|concise|brief))",
            re.I,
        ),
        "opus_effort_as_length",
        "Effort is being used as a length control. On Opus 5.5 and 5 effort controls thinking volume, not "
        "visible response length. Prompt for length explicitly and use effort for cost.",
    ),
    (
        re.compile(
            r"\b(?:thinking[^\n]{0,30}[\"']?disabled[\"']?"
            r"|[\"']?type[\"']?\s*[:=]\s*[\"']disabled[\"'])",
            re.I,
        ),
        "opus_thinking_disabled",
        "Thinking appears to be disabled. On Opus 5.5 that returns a 400 at every effort level. On "
        "Opus 5 it is capped at effort high or below (400 above that) and produces leaked tool "
        "calls and internal XML tags. Thinking enabled at low effort usually performs better.",
    ),
    (
        re.compile(
            r"\b(?:CRITICAL|IMPORTANT|MANDATORY|ALWAYS|NEVER|MUST)"
            r"[^.\n]{0,60}\b(?:tool|skill|function|search|retriev)",
            re.I | re.M,
        ),
        "opus_aggressive_tool_language",
        "Emphatic tool-triggering language. Recent Claude models follow plain instructions "
        "reliably and overtrigger on insistence. Prefer \"Use <tool> when <condition>.\"",
    ),
    (
        re.compile(
            r"\b(?:prefill|pre-fill|prefilled\s+(?:assistant|response)"
            r"|(?:start|begin)\s+your\s+(?:response|answer|reply)\s+with\s+[\"'`])",
            re.I,
        ),
        "opus_prefill",
        "Prefill-style construction. Assistant prefill on the last turn is unsupported from the "
        "4.6 generation onward and returns a 400. Use structured outputs, XML output tags, or a "
        "direct no-preamble instruction.",
    ),
]

# --- Generic contract patterns ----------------------------------------------

SECTION_PATTERNS = {
    "task": re.compile(r"\b(task|objective|goal|mission|your job)\b", re.I),
    "output": re.compile(r"\b(output|format|schema|structure|deliverable|return|report at the end)\b", re.I),
    "reason": re.compile(r"\b(because|so that|why this matters|this enables|in order to|the reason)\b", re.I),
    "scope": re.compile(
        r"\b(in scope|out of scope|scope|deliver what was asked|stop short of|"
        r"do not (?:add|refactor|extend))\b",
        re.I,
    ),
    "tools": re.compile(
        r"\b(tools?|function calls?|mcp|connectors?|web search|bash|shell|computer use|browser|"
        r"sub-?agents?)\b",
        re.I,
    ),
    "permissions": re.compile(r"\b(confirm|confirmation|permission|approval|ask (?:the )?user)\b", re.I),
    "recovery": re.compile(
        r"\b(retry|fallback|empty|incomplete|partial|conflict|stale|malformed|failure)\b", re.I
    ),
    "length": re.compile(
        r"\b(concise|brief|keep (?:responses|outputs)|do not pad|match the length|"
        r"lead with the outcome|tone_preference|filler)\b",
        re.I,
    ),
}

SIDE_EFFECT_VERBS = re.compile(
    r"\b(send|publish|deploy|delete|drop|purchase|pay|schedule|push|merge|commit|"
    r"restart|install|overwrite|revoke|email|post)\b",
    re.I,
)

USER_FACING_MARKER = re.compile(
    r"\b(user|customer|reader|chat|conversation|assistant for|respond to|reply)\b", re.I
)

WRITES_FILES_MARKER = re.compile(
    r"\b(write (?:a |the )?(?:report|document|summary|file|markdown)|save to|"
    r"\.md\b|deliverable|slide deck|spreadsheet|presentation)\b",
    re.I,
)

AGENTIC_MARKER = re.compile(
    r"\b(repositor(?:y|ies)|codebase|test suite|tests? pass|migrat\w*|refactor\w*|audit\w*|"
    r"end[- ]to[- ]end|long[- ]running|autonomous\w*|unattended|agent\w*|tool calls?|CLAUDE\.md)\b",
    re.I,
)
DONE_CRITERION = re.compile(
    r"\b(done (?:means|when|looks like)|definition of done|finish line|you(?:'re| are) done when|"
    r"acceptance criteria|success criteria|complete when|until (?:the |all )?tests pass|"
    r"the task is (?:complete|done|finished) when)\b",
    re.I,
)
STOP_RULE = re.compile(
    r"\b(stop and ask|ask (?:me|the user) (?:only|before|first|when)|check in (?:only|when|before)|"
    r"keep going|carry on|continue without|don'?t stop|without stopping|blocked on me|"
    r"requires? (?:explicit )?confirmation|before anything destructive)\b",
    re.I,
)
RESEARCH_MARKER = re.compile(
    r"\b(research|investigat\w*|literature|sources?|citations?|due diligence|fact[- ]check\w*)\b", re.I
)
UNCONFIRMED_RULE = re.compile(
    r"\b(couldn'?t (?:confirm|find|verify)|could not (?:confirm|find|verify)|unconfirmed|unverified|"
    r"where you looked|mark (?:anything|what))\b",
    re.I,
)

DELEGATION_INTENT = re.compile(r"\b(sub-?agents?|delegate|delegation|parallel agents)\b", re.I)
DELEGATION_LIMIT = re.compile(
    r"\b(only for|do not delegate|keep spawn counts low|genuinely independent|"
    r"cap|max(?:imum)?|concurren|depth)\b",
    re.I,
)


def normalize_instruction(line: str) -> str:
    line = re.sub(r"^[\s>*#\-+\d.()]+", "", line.strip().lower())
    line = re.sub(r"[`*_]", "", line)
    line = re.sub(r"\s+", " ", line)
    return line.strip(" .;:")


def lint_prompt(text: str) -> dict[str, Any]:
    lines = [line.rstrip() for line in text.splitlines()]
    nonempty = [line for line in lines if line.strip()]
    words = re.findall(r"\b\w+\b", text, flags=re.UNICODE)

    normalized = [normalize_instruction(line) for line in nonempty]
    candidates = [line for line in normalized if len(line) >= 12 and not line.endswith(":")]
    duplicate_counts = Counter(candidates)
    duplicates = [
        {"text": line, "count": count}
        for line, count in duplicate_counts.most_common()
        if count > 1
    ]

    sections = {name: bool(pattern.search(text)) for name, pattern in SECTION_PATTERNS.items()}
    warnings: list[dict[str, Any]] = []

    def scan(patterns: list[tuple[re.Pattern[str], str, str]], severity: str) -> None:
        for pattern, code, message in patterns:
            hits = []
            for match in pattern.finditer(text):
                line_no = text.count("\n", 0, match.start()) + 1
                hits.append({"line": line_no, "match": match.group(0)[:120]})
            if hits:
                warnings.append(
                    {"code": code, "message": message, "severity": severity, "hits": hits[:10]}
                )

    scan(AMPLIFIER_PATTERNS, "amplifier")
    scan(OPUS_PATTERNS, "opus")

    def add(code: str, message: str, severity: str = "generic") -> None:
        warnings.append({"code": code, "message": message, "severity": severity, "hits": []})

    if not sections["task"]:
        add("generic_missing_task", "No explicit task or objective marker detected.")
    if not sections["output"]:
        add("generic_missing_output_contract", "No explicit output contract or format marker detected.")
    if len(words) > 120 and not sections["reason"]:
        add(
            "generic_missing_rationale",
            "No stated reason behind the request. The model connects a task to relevant context "
            "better when it knows what the output enables and for whom.",
        )
    if USER_FACING_MARKER.search(text) and not sections["length"]:
        add(
            "opus_missing_length_calibration",
            "User-facing prompt with no length calibration. Opus 5's default replies run longer "
            "than prior Opus models' (re-measure on Opus 5.5), and effort will not shorten them.",
            "opus",
        )
    if WRITES_FILES_MARKER.search(text) and not re.search(
        r"\b(match the length|do not pad|filler|boilerplate)\b", text, re.I
    ):
        add(
            "opus_missing_deliverable_calibration",
            "The prompt produces written files but has no deliverable-length rule. Files Opus 5 "
            "writes to disk run long, and a conversational conciseness rule does not cover them.",
            "opus",
        )
    if len(words) > 200 and not sections["scope"]:
        add(
            "opus_missing_scope_boundary",
            "No scope boundary. Opus 5 can expand a task, adding steps that were not requested.",
            "opus",
        )
    agentic = bool(AGENTIC_MARKER.search(text))
    if agentic and not DONE_CRITERION.search(text):
        add(
            "opus_missing_done_criterion",
            "Agentic or multi-step prompt with no observable done criterion. Opus 5.5 works longer "
            "on its own; a concrete finish line ('done means: ... and the test suite passes') is "
            "how it knows it has arrived.",
            "opus",
        )
    if agentic and not STOP_RULE.search(text):
        add(
            "opus_missing_stop_rule",
            "Agentic prompt with no rule on when to stop and ask versus keep going. Opus 5.5 "
            "sometimes stops to report mid-task; name the stops you want (blocked on the user, "
            "before destructive actions) and the ones you don't.",
            "opus",
        )
    if RESEARCH_MARKER.search(text) and not UNCONFIRMED_RULE.search(text):
        add(
            "opus_missing_unconfirmed_marker",
            "Research or analysis prompt with no instruction to surface gaps. Add: 'Mark anything "
            "you couldn't confirm, and say where you looked.'",
            "opus",
        )
    if sections["tools"] and not sections["recovery"]:
        add(
            "generic_missing_tool_recovery",
            "Tool use is mentioned with no retry, fallback, or incomplete-result rule.",
        )
    if sections["tools"] and SIDE_EFFECT_VERBS.search(text) and not sections["permissions"]:
        add(
            "generic_missing_permission_boundary",
            "Potential side effects are mentioned without an approval boundary.",
        )
    if DELEGATION_INTENT.search(text) and not DELEGATION_LIMIT.search(text):
        add(
            "opus_unbounded_delegation",
            "Subagents are mentioned with no qualifying scenario or cap. Opus 5 delegates readily; "
            "pair a prompt rule with deterministic depth, concurrency, and spend caps.",
            "opus",
        )
    if duplicates:
        add("generic_duplicate_instructions", f"Detected {len(duplicates)} repeated instruction(s).")

    counts = Counter(w["severity"] for w in warnings)

    return {
        "metrics": {
            "characters": len(text),
            "words": len(words),
            "lines": len(lines),
            "nonempty_lines": len(nonempty),
            "amplifier_warnings": counts.get("amplifier", 0),
            "opus_warnings": counts.get("opus", 0),
            "generic_warnings": counts.get("generic", 0),
        },
        "detected_sections": sections,
        "duplicates": duplicates[:20],
        "warnings": warnings,
        "note": (
            "Warnings are heuristic. Review each against the actual task and measured failures. "
            "Amplifier warnings call for deleting text, not rewording it."
        ),
    }


def render_text(report: dict[str, Any]) -> str:
    out = ["Opus 5.5 / Opus 5 prompt lint report", "===================================="]
    m = report["metrics"]
    out.append(f"Words: {m['words']} | Lines: {m['lines']} | Characters: {m['characters']}")
    out.append(
        f"Amplifiers: {m['amplifier_warnings']} | Opus-specific: {m['opus_warnings']} | "
        f"Generic: {m['generic_warnings']}"
    )
    detected = ", ".join(k for k, v in report["detected_sections"].items() if v)
    out.append("Detected sections: " + (detected or "none"))

    groups = [
        ("amplifier", "AMPLIFIERS - delete these; the model already does this"),
        ("opus", "OPUS 5.5 / 5-SPECIFIC - misconfiguration, refusal risk, or missing calibration"),
        ("generic", "CONTRACT AND STRUCTURE"),
    ]
    for severity, label in groups:
        group = [w for w in report["warnings"] if w["severity"] == severity]
        if not group:
            continue
        out.append(f"\n{label}")
        for w in group:
            out.append(f"- [{w['code']}] {w['message']}")
            for hit in w["hits"]:
                out.append(f"    line {hit['line']}: {hit['match']}")

    if not report["warnings"]:
        out.append("\nNo heuristic warnings detected.")
    if report["duplicates"]:
        out.append("\nRepeated instructions:")
        for item in report["duplicates"]:
            out.append(f"- {item['count']}x: {item['text']}")
    out.append("\n" + report["note"])
    return "\n".join(out)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Lint a prompt file or stdin for Opus 5.5 / Opus 5 amplifiers and contract gaps."
    )
    parser.add_argument("path", nargs="?", help="Prompt text file. Reads stdin when omitted or '-'.")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if not args.path or args.path == "-":
            text = sys.stdin.read()
        else:
            text = Path(args.path).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if not text.strip():
        print("error: prompt is empty", file=sys.stderr)
        return 2

    report = lint_prompt(text)
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_text(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
