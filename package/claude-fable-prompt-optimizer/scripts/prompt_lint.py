#!/usr/bin/env python3
"""Deterministic prompt linter for Claude Fable prompts.

This script does not judge prompt quality. It flags patterns that are known to
be inert or actively harmful on Claude Fable models (Fable 5.2 by default; rules
read from Anthropic documentation on 2026-11-16), plus generic prompt smells
(duplication, missing contracts, unbounded loops), for human review.

Two warning classes:
  fable_*   patterns specific to Fable behavior; usually a deletion
  generic_* contract and structure gaps that apply to any model

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

# --- Fable-specific patterns -------------------------------------------------
# Each entry: (compiled pattern, warning code, message)

FABLE_PATTERNS: list[tuple[re.Pattern[str], str, str]] = [
    (
        re.compile(
            r"\b(?:answer directly without deliberat\w*|(?:do not|don't) (?:deliberate|think|reason)\b"
            r"|without (?:deliberating|thinking)|skip (?:your )?thinking|think less|minimi[sz]e (?:your )?thinking)",
            re.I,
        ),
        "fable_think_less",
        "Instruction to think less. On Fable 5.2 it does not stop thinking at medium effort and "
        "above (Fable 5.1 usually followed it). Delete it and lower effort for those turns.",
    ),
    (
        re.compile(
            r"\b(?:delegate (?:aggressively|liberally|whenever|wherever|by default)"
            r"|always delegate|use subagents? (?:wherever|where(?:ver)? possible|for everything|liberally|aggressively)"
            r"|use (?:it )?proactively|prefer (?:delegating|subagents))",
            re.I,
        ),
        "fable_standing_delegation",
        "Standing instruction to delegate. Fable 5.2 delegates readily when prompts invite it, and "
        "subagents can dominate session cost. Remove it unless tests show under-delegation; state "
        "what a subagent costs and when it is worth it instead.",
    ),
    (
        re.compile(
            r"\b(?:token budget|budget of [\d,.]+k? tokens|you have [\d,.]+k? tokens"
            r"|tokens? (?:remaining|left)|remaining (?:context|token budget)"
            r"|context (?:budget|usage) (?:is|remaining)|\d+% of (?:your )?context)",
            re.I,
        ),
        "fable_visible_token_budget",
        "A token budget or remaining-context figure shown to the model. On Fable 5.2 its size "
        "changes how much the model spends; removing a large one cut cost at equal performance in "
        "Anthropic's testing. A countdown also triggers premature wrap-up. Test without it.",
    ),
    (
        re.compile(
            r"\b(?:\d+ words or (?:fewer|less)|(?:no more than|at most|under|max(?:imum)?(?: of)?) \d+ words(?: per sentence)?"
            r"|sentences? (?:of|under|below|no longer than) \d+ words)",
            re.I,
        ),
        "fable_hard_style_limit",
        "Hard style limit. Fable 5.2 follows style rules closely and such limits make prose "
        "choppy. Remove it before adding the 'Communicating clearly' block.",
    ),
    (
        re.compile(r"\btreat (?:that|the|your|an earlier) answer as (?:done|settled)", re.I),
        "fable_treat_as_done",
        "Opus 5.5 'treat that answer as done' line. On Fable 5.2 it reduced thinking on follow-ups "
        "and made the model far less likely to point out its own earlier mistakes.",
    ),
    (
        re.compile(
            r"\b(?:messages? to (?:people|anyone) outside (?:this|the) conversation"
            r"|(?:contact|message|email)(?:ing)? anyone (?:outside|else))",
            re.I,
        ),
        "fable_broad_approval",
        "Broad approval category. A rule listing 'sending messages to people outside this "
        "conversation' made Fable 5.2 hold back about half of routine requests to colleagues. "
        "Name the specific actions that need approval and the routine ones that do not.",
    ),
    (
        re.compile(
            r"\b(?:show (?:your |me your )?(?:reasoning|thinking|thought process|work)"
            r"|explain your (?:reasoning|thinking|thought process)"
            r"|(?:output|include|print|write out|transcribe|echo|reproduce) your (?:reasoning|thinking|"
            r"chain[- ]of[- ]thought|thought process)"
            r"|chain[- ]of[- ]thought"
            r"|reflect on your (?:reasoning|thinking)"
            r"|think out loud in your (?:response|answer|reply)"
            r"|running log of your (?:reasoning|thinking))"
            r"|[\"'](?:reasoning|thinking|trace)[\"']\s*:"
            r"|<(?:thinking|scratchpad|reasoning)>",
            re.I,
        ),
        "fable_reasoning_display",
        "Asks the model to reproduce its reasoning in the response (prose, a scratchpad tag, or a "
        "reasoning/thinking/trace field). On Fable models and Opus 5.5 this can trigger the "
        "reasoning_extraction refusal, which has no fallback. Read display: summarized thinking "
        "blocks; a short explanation or evidence summary is fine.",
    ),
    (
        re.compile(
            r"\b(?:hold (?:all )?(?:findings|results|updates|output)"
            r"|(?:no|avoid|don't|do not) (?:narrat|commentary|running commentary|progress updates|"
            r"intermediate (?:updates|messages))"
            r"|(?:save|wait|reserve)[^.\n]{0,40}(?:for the )?final (?:response|message|summary)"
            r"|silent(?:ly)? until (?:done|complete|finished))",
            re.I,
        ),
        "fable_anti_narration",
        "Anti-narration rule. Fable can already write little user-facing text during long tool "
        "runs; this makes agents look silent. Delete it before adding any request for updates.",
    ),
    (
        re.compile(
            r"\b(?:(?:do not|don't|never|avoid)\s+(?:use|using)\s+"
            r"(?:markdown|bullet|bullets|bullet points|headers?|headings?|lists?|bold|"
            r"emphasis|tables?)"
            r"|no (?:bullet points|bullets|markdown|headers?|lists?|bold)"
            r"|avoid_excessive_markdown)",
            re.I,
        ),
        "fable_anti_formatting",
        "Anti-formatting rule. Measured on Fable 5.1: it already under-formats, so this suppresses "
        "structure the content needs. Delete it or say when formatting helps; re-test on 5.2.",
    ),
    (
        re.compile(
            r"(?:\bCRITICAL\b|\bIMPORTANT\b|\bMANDATORY\b|\bALWAYS\b|\bNEVER\b|\bMUST\b)"
            r"[^.\n]{0,60}\b(?:tool|skill|function|search|retriev)",
            re.I | re.M,
        ),
        "fable_aggressive_tool_language",
        "Emphatic tool-triggering language. Overtriggering is documented for Opus 4.5 and 4.6, not "
        "for Fable: test it. Prefer \"Use <tool> when <condition>.\"",
    ),
    (
        re.compile(
            r"\b(?:prefill|pre-fill|prefilled (?:assistant|response)"
            r"|(?:start|begin) your (?:response|answer|reply) with [\"'`])",
            re.I,
        ),
        "fable_prefill",
        "Prefill-style construction. A prefilled assistant turn returns 400 on Fable. Use "
        "structured outputs, XML output tags, or a direct no-preamble instruction.",
    ),
    (
        re.compile(r"\b(?:budget_tokens|thinking budget|reasoning budget|token budget for thinking)\b", re.I),
        "fable_thinking_budget",
        "Thinking-budget reference. budget_tokens returns 400 on Fable. Control depth with effort "
        "and cap output with max_tokens.",
    ),
    (
        re.compile(r"tool_choice[^\n]{0,60}(?:\"any\"|'any'|\btype\"?\s*:\s*\"?tool)", re.I),
        "fable_forced_tool_use",
        "Forced tool use. tool_choice any/tool returns 400 on Fable 5.2 and 5.1. Use auto plus a "
        "line naming the tool and its condition, strict tool use, or JSON outputs.",
    ),
    (
        re.compile(r"\b(?:temperature|top_p|top_k)\s*[:=]\s*[\d.]", re.I),
        "fable_sampling_params",
        "Sampling parameter. Non-default values return 400 on Fable; from API version 2026-10-21 "
        "any value returns 400 on every model.",
    ),
    (
        re.compile(
            r"\b(?:think (?:carefully|harder|deeply|step by step)"
            r"|be (?:accurate|thorough|smart|intelligent|helpful|careful)"
            r"|take your time"
            r"|use all available tools"
            r"|if in doubt,? use)",
            re.I,
        ),
        "fable_inert_directive",
        "Directive with no observable contract. Fable thinks before almost every reply at high "
        "effort; effort, not wording, controls depth. Replace with a check or a trigger condition.",
    ),
]

NEVER_LINE = re.compile(r"\bnever\b", re.I)
NEVER_SCOPED = re.compile(r"\b(?:unless|except|because|since|so that|without (?:asking|approval)|ask)\b", re.I)
OWNERSHIP = re.compile(r"owner and (?:the )?long-term maintainer", re.I)
SCOPE_LIMIT = re.compile(
    r"\b(?:no drive-by|minimal (?:change|diff)|smallest (?:possible )?change|do not refactor|don't refactor|"
    r"only (?:change|touch|edit) )",
    re.I,
)

# --- Generic contract patterns ----------------------------------------------

SECTION_PATTERNS = {
    "task": re.compile(r"\b(task|objective|goal|mission|your job|tache|objectif|r[eé]sultat attendu)\b", re.I),
    "output": re.compile(r"\b(output|format|schema|structure|deliverable|return|sortie|livrable)\b", re.I),
    "reason": re.compile(r"\b(because|so that|why this matters|this enables|in order to|the reason)\b", re.I),
    "verification": re.compile(r"\b(verify|verification|validate|validation|check|audit|controle)\b", re.I),
    "done": re.compile(r"\b(done when|done criteria|definition of done|complete only when|termin[eé]e?|fini quand|crit[eè]res? de fin)\b", re.I),
    "tools": re.compile(
        r"\b(tools?|outils?|function calls?|mcp|connectors?|web search|bash|shell|"
        r"computer use|browser|subagents?)\b",
        re.I,
    ),
    "permissions": re.compile(
        r"\b(confirm|confirmation|permission|approval|ask (?:the )?user|autorisation|effets? permis|interdits?|(?:ni|aucun) push)\b", re.I
    ),
    "recovery": re.compile(
        r"\b(retry|fallback|empty|incomplete|partial|conflict|stale|malformed|failure|erreur)\b", re.I
    ),
    "scope": re.compile(r"\b(in scope|out of scope|scope|do not (?:add|refactor|extend)|follow-up|domaine|p[eé]rim[eè]tre|en lecture seule|aucun changement hors|ni document ni commentaire)\b", re.I),
}

# French mandate headings: they count only as a whole heading line, possibly followed by
# a parenthesis or punctuation, and never inside fenced code.
FR_TITLES = {
    "task": r"r[eé]sultat(?: demand[eé])?|objet(?: de ce tour)?|besoin|exigences?|d[eé]faut|ce qui est demand[eé]|ce que le pilote attend en plus du brief|port[eé]e de ce tour|passe cibl[eé]e",
}
FR_TITLES = {
    name: re.compile(r"(?m)^#{1,6}[ \t]+(?:" + forms + r")[ \t]*(?:[(:,;.!?\u2013\u2014-][^\n]*)?\r?$", re.I)
    for name, forms in FR_TITLES.items()
}
FENCED = re.compile(r"(?ms)^[ \t]*(`{3,}|~{3,}).*?^[ \t]*\1[ \t]*\r?$")

SIDE_EFFECT_VERBS = re.compile(
    r"\b(send|publish|deploy|delete|drop|purchase|pay|schedule|push|merge|commit|"
    r"restart|install|overwrite|revoke|email|post)\b",
    re.I,
)

AUTONOMY_MARKER = re.compile(
    r"\b(operating autonomously|user is not watching|without asking|end your turn only when|"
    r"proceed without asking|finishing work|avoid stopping while you still owe|do not stop unless needed|"
    r"sans (?:t|vous )?.?arr[eê]ter|sans demander|va au bout|ce que tu d[eé]cides seul|ce qui remonte|remonte dans ta remise|dis-le dans ta remise|outil refus[eé])\b",
    re.I,
)

LONG_RUN_MARKER = re.compile(
    r"\b(autonomous|long[- ]running|overnight|multi[- ]?day|until (?:complete|done|green|success)|"
    r"keep (?:going|working)|hours|continue until)\b",
    re.I,
)

LOOP_BOUND = re.compile(
    r"\b(at most|no more than|maximum|max(?:imum)? of|after \d+|\d+ (?:cycles?|attempts?|"
    r"strategies|iterations?|retries)|stop after|scope ceiling|bounded)\b",
    re.I,
)

EVIDENCE_MARKER = re.compile(
    r"\b(audit each claim|against a tool result|point to evidence|report outcomes faithfully|"
    r"evidence for)\b",
    re.I,
)

DELEGATION_INTENT = re.compile(r"\b(subagents?|sub-agents?|delegate|delegation)\b", re.I)
DELEGATION_CONTRACT = re.compile(
    r"\b(when (?:to )?delegat|keep working|non[- ]?overlapping|read[- ]only|ownership|"
    r"merge|deduplicate|concurren|depth|wait for|costs?|brief|ne lances? aucun)\b",
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
    unfenced = FENCED.sub("", text)
    sections.update({name: sections.get(name, False) or bool(p.search(unfenced))
                     for name, p in FR_TITLES.items()})
    warnings: list[dict[str, Any]] = []

    # Fable-specific findings, with the matched text so the reviewer can locate it.
    for pattern, code, message in FABLE_PATTERNS:
        hits = []
        for match in pattern.finditer(text):
            line_no = text.count("\n", 0, match.start()) + 1
            hits.append({"line": line_no, "match": match.group(0)[:120]})
        if hits:
            warnings.append(
                {"code": code, "message": message, "severity": "fable", "hits": hits[:10]}
            )

    # Absolute "never" rules with no scope or reason on the same line.
    never_hits = []
    for line_no, line in enumerate(lines, start=1):
        if NEVER_LINE.search(line) and not NEVER_SCOPED.search(line):
            never_hits.append({"line": line_no, "match": line.strip()[:120]})
    if never_hits:
        warnings.append(
            {
                "code": "fable_absolute_never",
                "message": (
                    "Unscoped 'never' rule. Fable 5.2 treats 'never' as absolute and follows "
                    "accumulated cautions closely. Give the rule its scope and reason, or turn it "
                    "into an approval step ('ask before deleting files')."
                ),
                "severity": "fable",
                "hits": never_hits[:10],
            }
        )

    # Ownership sentence combined with a scope limit: the limit does not cancel it.
    if OWNERSHIP.search(text) and SCOPE_LIMIT.search(text):
        warnings.append(
            {
                "code": "fable_ownership_vs_scope",
                "message": (
                    "The ownership sentence and a scope limit appear together. On Fable 5.2 the "
                    "limit does not cancel it: the model still consolidated code in more than half "
                    "of runs. Keep one: ownership for restructuring, or no ownership for narrow "
                    "changes."
                ),
                "severity": "fable",
                "hits": [],
            }
        )

    # Generic contract findings.
    def add(code: str, message: str) -> None:
        warnings.append({"code": code, "message": message, "severity": "generic", "hits": []})

    if not sections["task"]:
        add("generic_missing_task", "No explicit task or objective marker detected.")
    if not sections["output"]:
        add("generic_missing_output_contract", "No explicit output contract or format marker detected.")
    if len(words) > 120 and not sections["reason"]:
        add(
            "generic_missing_rationale",
            "No stated reason behind the request. Fable performs better when it knows what the "
            "output enables and for whom.",
        )
    if len(words) > 250 and not sections["verification"]:
        add("generic_missing_verification", "Long prompt has no explicit verification rule.")
    if len(words) > 350 and not sections["done"]:
        add("generic_missing_done_criteria", "Long prompt has no explicit done criteria.")
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
    if LONG_RUN_MARKER.search(text) and not LOOP_BOUND.search(text):
        add(
            "generic_unbounded_loop",
            "Long-running or iterative execution with no cycle, strategy, or scope bound.",
        )
    if LONG_RUN_MARKER.search(text) and not AUTONOMY_MARKER.search(text):
        add(
            "fable_missing_autonomy_contract",
            "Long-running work with no completion contract. Fable 5.2 can end a turn listing what "
            "remains, offering to continue, or at an ordinary obstacle, more often at low and "
            "medium effort. Consider the documented 'Finishing work' block.",
        )
        warnings[-1]["severity"] = "fable"
    if LONG_RUN_MARKER.search(text) and not EVIDENCE_MARKER.search(text):
        add(
            "fable_missing_progress_grounding",
            "Long-running work with no rule requiring progress claims to be audited against tool "
            "results. This is the documented fix for fabricated status reports.",
        )
        warnings[-1]["severity"] = "fable"
    if LONG_RUN_MARKER.search(text) and not sections["scope"]:
        add(
            "generic_missing_scope_boundary",
            "Long-running work with no in-scope/out-of-scope boundary. Expect unrequested fixes "
            "and extra committed tests.",
        )
    if DELEGATION_INTENT.search(text) and not DELEGATION_CONTRACT.search(text):
        add(
            "generic_missing_delegation_contract",
            "Subagents are mentioned with no delegation trigger, ownership, blocking, or merge rule.",
        )
    if duplicates:
        add("generic_duplicate_instructions", f"Detected {len(duplicates)} repeated instruction(s).")

    fable_count = sum(1 for w in warnings if w["severity"] == "fable")

    return {
        "metrics": {
            "characters": len(text),
            "words": len(words),
            "lines": len(lines),
            "nonempty_lines": len(nonempty),
            "fable_warnings": fable_count,
            "generic_warnings": len(warnings) - fable_count,
        },
        "detected_sections": sections,
        "duplicates": duplicates[:20],
        "warnings": warnings,
        "note": (
            "Warnings are heuristic. Review each against the actual task and measured failures. "
            "Fable-class warnings usually call for deleting text, not adding it."
        ),
    }


def render_text(report: dict[str, Any]) -> str:
    out = ["Fable prompt lint report", "========================"]
    m = report["metrics"]
    out.append(
        f"Words: {m['words']} | Lines: {m['lines']} | Characters: {m['characters']}"
    )
    out.append(
        f"Fable-specific warnings: {m['fable_warnings']} | Generic warnings: {m['generic_warnings']}"
    )
    detected = ", ".join(k for k, v in report["detected_sections"].items() if v)
    out.append("Detected sections: " + (detected or "none"))

    fable = [w for w in report["warnings"] if w["severity"] == "fable"]
    generic = [w for w in report["warnings"] if w["severity"] != "fable"]

    if fable:
        out.append("\nFable-specific (consider deleting):")
        for w in fable:
            out.append(f"- [{w['code']}] {w['message']}")
            for hit in w["hits"]:
                out.append(f"    line {hit['line']}: {hit['match']}")
    if generic:
        out.append("\nContract and structure:")
        for w in generic:
            out.append(f"- [{w['code']}] {w['message']}")
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
        description="Lint a prompt file or stdin for Fable-hostile patterns and contract gaps."
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
