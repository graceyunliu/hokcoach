"""Audit Coach knowledge-base coverage and schema health.

This is intentionally deterministic and offline. It does not translate or
rewrite coaching knowledge; it reports which loaded principles are missing a
human-reviewed English counterpart so English generation can fail closed.

Usage:
    python -m tools.audit_knowledge_base
    python -m tools.audit_knowledge_base --strict-en
    python -m tools.audit_knowledge_base --json
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from core.knowledge_engine import KNOWLEDGE_DIR, load_all_principles


def build_report(knowledge_dir: Path = KNOWLEDGE_DIR) -> dict[str, Any]:
    """Return a stable, machine-readable report for CI and local review."""
    principles = load_all_principles(knowledge_dir)
    missing_en = [p.id for p in principles if not (p.text_en or "").strip()]
    return {
        "knowledge_dir": str(knowledge_dir),
        "total_loaded": len(principles),
        "english_translated": len(principles) - len(missing_en),
        "english_coverage": (
            round((len(principles) - len(missing_en)) / len(principles), 4)
            if principles else 1.0
        ),
        "missing_english_ids": missing_en,
        "by_origin": dict(Counter(p.origin_file for p in principles)),
        "by_tier": dict(Counter(p.tier or "unmarked" for p in principles)),
    }


def render_text(report: dict[str, Any]) -> str:
    """Render a concise human-readable report without losing exact IDs."""
    missing = report["missing_english_ids"]
    lines = [
        "Coach knowledge-base audit",
        f"Loaded principles: {report['total_loaded']}",
        f"English coverage: {report['english_translated']}/{report['total_loaded']} "
        f"({report['english_coverage']:.1%})",
        f"Missing English IDs: {', '.join(missing) if missing else 'none'}",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--knowledge-dir", type=Path, default=KNOWLEDGE_DIR)
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument(
        "--strict-en",
        action="store_true",
        help="exit 1 when any loaded principle lacks English text_en",
    )
    args = parser.parse_args(argv)
    report = build_report(args.knowledge_dir)
    print(json.dumps(report, ensure_ascii=False, indent=2) if args.as_json
          else render_text(report))
    if args.strict_en and report["missing_english_ids"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["build_report", "render_text", "main"]
