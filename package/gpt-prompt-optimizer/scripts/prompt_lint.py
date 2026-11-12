#!/usr/bin/env python3
"""Lightweight prompt linter for deterministic warnings.

This script does not judge prompt quality. It highlights duplicated instructions,
missing contracts, vague directives, and common prompt smells for human review.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

SECTION_PATTERNS = {
    "task": re.compile(r"\b(task|tache|mission|objectif|goal)\b", re.I),
    "output": re.compile(r"\b(output|sortie|format|schema|structure|livrable)\b", re.I),
    "verification": re.compile(r"\b(verify|verification|validate|validation|check|controle)\b", re.I),
    "done": re.compile(r"\b(done criteria|definition of done|critere[s]? de fin|termine[e]?)\b", re.I),
    "tools": re.compile(r"\b(tools?|outils?|function calls?|mcp|connectors?|web search|file search|computer use|ssh|shell|terminal)\b", re.I),
    "permissions": re.compile(r"\b(confirm|confirmation|permission|approval|consent|autorisation|validation explicite)\b", re.I),
    "recovery": re.compile(r"\b(retry|reessayer|fallback|empty|incomplete|partial|conflict|erreur|failure)\b", re.I),
}

VAGUE_PATTERNS = [
    (re.compile(r"\b(be|sois) (accurate|precis|intelligent|smart|helpful|utile)\b", re.I), "vague quality directive"),
    (re.compile(r"\bthink (carefully|harder|step by step)\b", re.I), "reasoning-process directive; prefer an observable verification requirement"),
    (re.compile(r"\b(reflechis|raisonne) (bien|davantage|etape par etape)\b", re.I), "reasoning-process directive; prefer an observable verification requirement"),
    (re.compile(r"\buse all available tools\b", re.I), "overbroad tool instruction"),
    (re.compile(r"\butilise tous les outils disponibles\b", re.I), "overbroad tool instruction"),
]

CHAIN_OF_THOUGHT = re.compile(
    r"\b(chain[- ]of[- ]thought|show (your )?reasoning|reveal (your )?reasoning|"
    r"montre (ton|votre) raisonnement|revele (ton|votre) raisonnement)\b",
    re.I,
)

LOOP_INTENT = re.compile(
    r"\b(until green|until success|until satisfied|keep iterating|continue until|"
    r"jusqu.?a ce que .*verte|jusqu.?au succes|continue[r]? jusqu)\b",
    re.I,
)

LOOP_BOUND = re.compile(
    r"\b(max(?:imum)?|at most|no more than|after \d+|\d+ (?:cycles?|attempts?|strategies)|"
    r"stop after|scope ceiling|bounded|limite|au plus|maximum|apres \d+|\d+ (?:cycles?|tentatives?|strategies))\b",
    re.I,
)

DELEGATION_INTENT = re.compile(r"\b(subagents?|sub-agents?|delegate|delegation|sous-agents?)\b", re.I)
DELEGATION_MERGE = re.compile(
    r"\b(wait for|collect|merge|deduplicate|synthesize|consolidate|"
    r"attendre|collecter|fusionner|dedoublonner|synthetiser|consolider)\b",
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
    candidates = [line for line in normalized if len(line) >= 12 and not line.endswith(":" )]
    duplicate_counts = Counter(candidates)
    duplicates = [
        {"text": line, "count": count}
        for line, count in duplicate_counts.most_common()
        if count > 1
    ]

    sections = {name: bool(pattern.search(text)) for name, pattern in SECTION_PATTERNS.items()}
    warnings: list[dict[str, str]] = []

    if not sections["task"]:
        warnings.append({"code": "missing_task", "message": "No explicit task or objective marker detected."})
    if not sections["output"]:
        warnings.append({"code": "missing_output_contract", "message": "No explicit output contract or format marker detected."})
    if len(words) > 250 and not sections["verification"]:
        warnings.append({"code": "missing_verification", "message": "Long prompt has no explicit verification rule."})
    if len(words) > 350 and not sections["done"]:
        warnings.append({"code": "missing_done_criteria", "message": "Long prompt has no explicit done criteria."})
    if sections["tools"] and not sections["recovery"]:
        warnings.append({"code": "missing_tool_recovery", "message": "Tool use is mentioned but no retry, fallback, or incomplete-result rule was detected."})
    if sections["tools"] and re.search(r"\b(send|publish|delete|purchase|book|schedule|modifier|supprimer|envoyer|publier|acheter)\b", text, re.I) and not sections["permissions"]:
        warnings.append({"code": "missing_permission_boundary", "message": "Potential side effects are mentioned without an approval boundary."})
    if LOOP_INTENT.search(text) and not LOOP_BOUND.search(text):
        warnings.append({"code": "unbounded_loop", "message": "Iterative execution is requested without a cycle, strategy, scope, or stop bound."})
    if DELEGATION_INTENT.search(text) and not DELEGATION_MERGE.search(text):
        warnings.append({"code": "missing_delegation_merge", "message": "Subagents or delegation are mentioned without an explicit wait, merge, or synthesis rule."})
    if re.search(r"\b(computer use|ssh|server|service|system settings|vpn|api keys?|permissions?)\b", text, re.I) and re.search(r"\b(delete|install|restart|change|modify|upload|transfer|run|execute|supprimer|installer|redemarrer|modifier|televerser|transferer|executer)\b", text, re.I) and not sections["permissions"]:
        warnings.append({"code": "missing_machine_action_confirmation", "message": "Machine or Computer Use actions may be risky but no confirmation boundary was detected."})
    if duplicates:
        warnings.append({"code": "duplicate_instructions", "message": f"Detected {len(duplicates)} repeated instruction(s)."})
    cot_requests = []
    for match in CHAIN_OF_THOUGHT.finditer(text):
        prefix = text[max(0, match.start() - 80):match.start()].lower()
        if not re.search(r"\b(?:never|do not|don't|must not|no|ne pas|jamais|sans)\b", prefix):
            cot_requests.append(match.group(0))
    if cot_requests:
        warnings.append({"code": "chain_of_thought_request", "message": "Prompt appears to request hidden reasoning. Ask for evidence, checks, or concise rationale instead."})

    vague_hits: list[dict[str, str]] = []
    for pattern, message in VAGUE_PATTERNS:
        for match in pattern.finditer(text):
            vague_hits.append({"match": match.group(0), "message": message})
    if vague_hits:
        warnings.append({"code": "vague_directives", "message": f"Detected {len(vague_hits)} vague or overbroad directive(s)."})

    return {
        "metrics": {
            "characters": len(text),
            "words": len(words),
            "lines": len(lines),
            "nonempty_lines": len(nonempty),
        },
        "detected_sections": sections,
        "duplicates": duplicates[:20],
        "vague_directives": vague_hits[:20],
        "warnings": warnings,
        "note": "Warnings are heuristic. Review them against the actual task and measured failures.",
    }


def render_text(report: dict[str, Any]) -> str:
    out = ["Prompt lint report", "=================="]
    m = report["metrics"]
    out.append(f"Words: {m['words']} | Lines: {m['lines']} | Characters: {m['characters']}")
    out.append("Detected sections: " + ", ".join(k for k, v in report["detected_sections"].items() if v))
    if report["warnings"]:
        out.append("\nWarnings:")
        for warning in report["warnings"]:
            out.append(f"- [{warning['code']}] {warning['message']}")
    else:
        out.append("\nNo heuristic warnings detected.")
    if report["duplicates"]:
        out.append("\nRepeated instructions:")
        for item in report["duplicates"]:
            out.append(f"- {item['count']}x: {item['text']}")
    if report["vague_directives"]:
        out.append("\nVague directives:")
        for item in report["vague_directives"]:
            out.append(f"- {item['match']}: {item['message']}")
    out.append("\n" + report["note"])
    return "\n".join(out)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Lint a prompt file or stdin for common prompt smells.")
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
