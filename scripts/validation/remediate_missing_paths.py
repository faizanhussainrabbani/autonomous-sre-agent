#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import os
from pathlib import Path

IGNORED_DIR_NAMES = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "htmlcov",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
}


def index_files(repo_root: Path) -> dict[str, list[Path]]:
    by_name: dict[str, list[Path]] = {}
    for p in repo_root.rglob("*"):
        if not p.is_file():
            continue
        if any(part in IGNORED_DIR_NAMES for part in p.parts):
            continue
        by_name.setdefault(p.name, []).append(p)
    return by_name


def normalize_posix(path_str: str) -> str:
    return path_str.replace(os.sep, "/")


def strip_parent_prefix(path_part: str) -> str:
    s = path_part
    while s.startswith("../"):
        s = s[3:]
    if s.startswith("./"):
        s = s[2:]
    return s


def resolve_high_confidence_candidate(
    repo_root: Path,
    source: Path,
    path_part: str,
    by_name: dict[str, list[Path]],
) -> Path | None:
    basename = Path(path_part).name

    # 1) Direct unique basename resolution.
    candidates = by_name.get(basename, []) if basename else []
    if len(candidates) == 1:
        return candidates[0]

    # 2) Root-relative stripped prefix resolution.
    stripped = strip_parent_prefix(path_part)
    if stripped:
        direct = repo_root / stripped
        if direct.exists():
            return direct

    # 3) Canonical openspec subtree mapping for sibling change/spec references.
    if stripped:
        # Match unique suffix anywhere in repo.
        suffix_matches = [
            p
            for p in repo_root.rglob("*")
            if p.exists()
            and normalize_posix(p.as_posix()).endswith("/" + normalize_posix(stripped))
        ]
        if len(suffix_matches) == 1:
            return suffix_matches[0]

        # Prefer openspec/changes scoped candidates if source is under openspec.
        if "openspec" in source.as_posix() and stripped.startswith("phase-"):
            scoped = [
                p
                for p in repo_root.rglob("*")
                if p.exists()
                and "openspec/changes/" in normalize_posix(p.as_posix())
                and normalize_posix(p.as_posix()).endswith("/" + normalize_posix(stripped))
            ]
            if len(scoped) == 1:
                return scoped[0]

    return None


def remediate(repo_root: Path, in_csv: Path) -> tuple[int, int, int]:
    rows = list(csv.DictReader(in_csv.open(encoding="utf-8")))
    missing = [r for r in rows if r.get("issue_type") == "MISSING_PATH"]

    by_name = index_files(repo_root)

    attempted = 0
    fixed = 0
    skipped = 0

    for row in missing:
        source = repo_root / row["source_file"]
        target = row["target"]

        if not source.exists() or not source.is_file():
            skipped += 1
            continue

        if "#" in target:
            path_part, frag = target.split("#", 1)
            suffix = "#" + frag
        else:
            path_part = target
            suffix = ""

        candidate = resolve_high_confidence_candidate(
            repo_root=repo_root,
            source=source,
            path_part=path_part,
            by_name=by_name,
        )
        if candidate is None:
            skipped += 1
            continue

        new_rel = normalize_posix(os.path.relpath(candidate, start=source.parent)) + suffix

        old_token = f"({target})"
        new_token = f"({new_rel})"

        content = source.read_text(encoding="utf-8", errors="ignore")
        if old_token not in content:
            skipped += 1
            continue

        attempted += 1
        updated = content.replace(old_token, new_token)
        source.write_text(updated, encoding="utf-8")
        fixed += 1

    return attempted, fixed, skipped


def main() -> int:
    parser = argparse.ArgumentParser(description="Auto-remediate high-confidence MISSING_PATH markdown issues.")
    parser.add_argument("--repo", default=".", help="Repository root")
    parser.add_argument(
        "--issues-csv",
        default=".copilot-tracking/link-integrity/markdown-link-issues.csv",
        help="Input CSV from strict_markdown_link_check.py",
    )
    args = parser.parse_args()

    repo_root = Path(args.repo).resolve()
    in_csv = Path(args.issues_csv)
    if not in_csv.is_absolute():
        in_csv = repo_root / in_csv

    if not in_csv.exists():
        raise SystemExit(f"Issues CSV not found: {in_csv}")

    attempted, fixed, skipped = remediate(repo_root, in_csv)
    print(f"Remediation attempted: {attempted}")
    print(f"Remediation fixed: {fixed}")
    print(f"Remediation skipped: {skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
