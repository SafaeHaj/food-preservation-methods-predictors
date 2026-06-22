"""
Stage 3: Anchor-based pre-filtering of parsed Markdown.

Deterministically checks whether a paper covers the required concept groups
before incurring LLM costs. Rejections are logged to a JSONL file.

Entry point: run_filter(markdown_dir, anchor_concepts, log_path) -> list[Path]
"""

from __future__ import annotations

import json
import re
from pathlib import Path


def _compile_group(group: dict) -> tuple[str, bool, list[tuple[str, re.Pattern]]]:
    """Pre-compile regex patterns for one anchor group."""
    name = group["group"]
    required = group.get("required", False)
    patterns = [
        (term, re.compile(term, re.IGNORECASE))
        for term in group.get("terms", [])
    ]
    return name, required, patterns


def compute_coverage(
    markdown_text: str,
    anchor_concepts: list[dict],
) -> tuple[float, dict[str, list[str]]]:
    """
    Return (coverage_score, {group_name: [matched_terms]}).

    coverage_score = fraction of groups (required + optional) that have ≥1 match.
    """
    if not anchor_concepts:
        return 1.0, {}

    group_matches: dict[str, list[str]] = {}
    for group in anchor_concepts:
        name, _, patterns = _compile_group(group)
        matched = [term for term, pat in patterns if pat.search(markdown_text)]
        group_matches[name] = matched

    matched_groups = sum(1 for matches in group_matches.values() if matches)
    score = matched_groups / len(anchor_concepts)
    return score, group_matches


def passes_filter(
    group_matches: dict[str, list[str]],
    anchor_concepts: list[dict],
    threshold: float = 0.5,
) -> tuple[bool, list[str]]:
    """
    Return (passed, [missing_required_groups]).

    A paper fails if any required group has zero matches, regardless of score.
    """
    missing_required: list[str] = []
    for group in anchor_concepts:
        name = group["group"]
        if group.get("required", False) and not group_matches.get(name):
            missing_required.append(name)

    if missing_required:
        return False, missing_required

    matched_groups = sum(1 for matches in group_matches.values() if matches)
    score = matched_groups / len(anchor_concepts) if anchor_concepts else 1.0
    if score < threshold:
        return False, []

    return True, []


def log_rejection(
    md_path: Path,
    reason: str,
    missing_groups: list[str],
    log_path: Path,
) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "file": md_path.name,
        "reason": reason,
        "missing_required_groups": missing_groups,
    }
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def run_filter(
    markdown_dir: Path,
    anchor_concepts: list[dict],
    log_path: Path,
    threshold: float = 0.5,
) -> list[Path]:
    """
    Filter .md files in markdown_dir by anchor coverage.

    Returns paths of papers that passed. Logs rejections to log_path (JSONL).
    """
    md_paths = list(markdown_dir.glob("*.md"))
    if not md_paths:
        print(f"[filter] No Markdown files found in {markdown_dir}")
        return []

    if not anchor_concepts:
        print("[filter] No anchor_concepts defined — all papers pass")
        return md_paths

    print(f"[filter] Checking {len(md_paths)} papers against anchor concepts ...")
    passed: list[Path] = []

    for md_path in md_paths:
        text = md_path.read_text(encoding="utf-8")
        _, group_matches = compute_coverage(text, anchor_concepts)
        ok, missing = passes_filter(group_matches, anchor_concepts, threshold)

        if ok:
            passed.append(md_path)
        else:
            reason = (
                f"Missing required groups: {missing}"
                if missing
                else f"Coverage below threshold ({threshold})"
            )
            print(f"  [filter] REJECTED {md_path.name}: {reason}")
            log_rejection(md_path, reason, missing, log_path)

    print(f"[filter] {len(passed)}/{len(md_paths)} papers passed")
    return passed
