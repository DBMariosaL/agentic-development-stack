#!/usr/bin/env python3
"""Profile CSV, JSON, or JSONL evaluation datasets with the standard library."""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

FIELD_HINTS = {
    "input": ("input", "prompt", "question", "request", "user_input", "messages"),
    "output": ("output", "response", "answer", "model_output", "actual"),
    "expected": ("expected", "reference", "target", "ideal", "ground_truth"),
    "label": ("label", "rating", "grade", "pass", "success", "good_bad", "status"),
    "feedback": ("feedback", "critique", "output_feedback", "comment", "notes", "reason"),
    "grader": ("grader", "grader_result", "score", "eval_score"),
    "latency": ("latency", "latency_ms", "duration", "elapsed"),
    "tokens": ("tokens", "total_tokens", "input_tokens", "output_tokens", "reasoning_tokens"),
    "cost": ("cost", "cost_usd", "price"),
}


def load_rows(path: Path) -> list[dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as fh:
            return [dict(row) for row in csv.DictReader(fh)]
    if suffix in {".jsonl", ".ndjson"}:
        rows: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as fh:
            for number, line in enumerate(fh, start=1):
                if not line.strip():
                    continue
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ValueError(f"line {number} is not a JSON object")
                rows.append(value)
        return rows
    if suffix == ".json":
        value = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(value, list):
            if not all(isinstance(row, dict) for row in value):
                raise ValueError("JSON array must contain objects")
            return value
        if isinstance(value, dict):
            for key in ("rows", "data", "items", "examples", "results"):
                rows = value.get(key)
                if isinstance(rows, list) and all(isinstance(row, dict) for row in rows):
                    return rows
        raise ValueError("JSON must be an array of objects or contain rows/data/items/examples/results")
    raise ValueError("supported formats: .csv, .json, .jsonl, .ndjson")


def is_missing(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def scalar_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def infer_semantic_fields(fields: Iterable[str]) -> dict[str, list[str]]:
    normalized = {field.lower().strip(): field for field in fields}
    result: dict[str, list[str]] = {}
    for category, hints in FIELD_HINTS.items():
        matches: list[str] = []
        for hint in hints:
            for lowered, original in normalized.items():
                if lowered == hint or lowered.endswith("_" + hint) or hint in lowered:
                    if original not in matches:
                        matches.append(original)
        result[category] = matches
    return result


def numeric_values(rows: list[dict[str, Any]], field: str) -> list[float]:
    values: list[float] = []
    for row in rows:
        value = row.get(field)
        if is_missing(value) or isinstance(value, bool):
            continue
        try:
            values.append(float(value))
        except (TypeError, ValueError):
            continue
    return values


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * q
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def profile(rows: list[dict[str, Any]], top_n: int) -> dict[str, Any]:
    all_fields = sorted({str(key) for row in rows for key in row.keys()})
    semantic = infer_semantic_fields(all_fields)
    row_count = len(rows)

    field_profiles: dict[str, Any] = {}
    for field in all_fields:
        present = [row.get(field) for row in rows if not is_missing(row.get(field))]
        texts = [scalar_text(value) for value in present]
        counts = Counter(texts)
        numeric = numeric_values(rows, field)
        item: dict[str, Any] = {
            "present": len(present),
            "missing": row_count - len(present),
            "coverage": round(len(present) / row_count, 4) if row_count else 0.0,
            "unique": len(counts),
            "top_values": counts.most_common(top_n),
        }
        if numeric and len(numeric) >= max(2, len(present) // 2):
            item["numeric"] = {
                "min": min(numeric),
                "median": percentile(numeric, 0.5),
                "p90": percentile(numeric, 0.9),
                "max": max(numeric),
                "mean": sum(numeric) / len(numeric),
            }
        field_profiles[field] = item

    label_fields = semantic.get("label", []) + semantic.get("grader", [])
    label_summary = {
        field: field_profiles[field]["top_values"]
        for field in label_fields
        if field in field_profiles
    }

    readiness_checks = {
        "has_at_least_3_rows": row_count >= 3,
        "has_input_field": bool(semantic.get("input")),
        "has_output_field": bool(semantic.get("output")),
        "has_annotation_or_grader_field": bool(semantic.get("label") or semantic.get("feedback") or semantic.get("grader")),
    }

    return {
        "rows": row_count,
        "fields": all_fields,
        "semantic_field_candidates": semantic,
        "readiness_checks": readiness_checks,
        "label_summary": label_summary,
        "field_profiles": field_profiles,
        "note": "Field inference is heuristic. Confirm the schema before drawing evaluation conclusions.",
    }


def render_text(report: dict[str, Any]) -> str:
    out = ["Evaluation dataset profile", "=========================="]
    out.append(f"Rows: {report['rows']} | Fields: {len(report['fields'])}")
    out.append("Fields: " + ", ".join(report["fields"]))
    out.append("\nSemantic field candidates:")
    for category, fields in report["semantic_field_candidates"].items():
        if fields:
            out.append(f"- {category}: {', '.join(fields)}")
    out.append("\nReadiness checks:")
    for check, value in report["readiness_checks"].items():
        out.append(f"- {check}: {'yes' if value else 'no'}")
    if report["label_summary"]:
        out.append("\nLabel/grader distributions:")
        for field, values in report["label_summary"].items():
            formatted = ", ".join(f"{value}={count}" for value, count in values)
            out.append(f"- {field}: {formatted}")
    out.append("\nField coverage:")
    for field, item in report["field_profiles"].items():
        out.append(f"- {field}: {item['present']}/{report['rows']} present, {item['unique']} unique")
    out.append("\n" + report["note"])
    return "\n".join(out)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Profile an evaluation dataset.")
    parser.add_argument("path", help="CSV, JSON, JSONL, or NDJSON dataset")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--top", type=int, default=10, help="Top values per field (default: 10)")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    path = Path(args.path)
    try:
        rows = load_rows(path)
        report = profile(rows, max(1, args.top))
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError, csv.Error) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_text(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
