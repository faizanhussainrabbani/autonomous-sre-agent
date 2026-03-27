#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import unquote


LINK_RE = re.compile(r"(!?)\[([^\]]*)\]\(([^)]+)\)")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*$")
HTML_ID_RE = re.compile(r"<a\s+id=[\"']([^\"']+)[\"']\s*>", re.IGNORECASE)

EXTERNAL_SCHEMES = (
    "http://",
    "https://",
    "mailto:",
    "ftp://",
    "tel:",
    "data:",
)

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


@dataclass
class Issue:
    source_file: str
    line: int
    link_text: str
    target: str
    issue_type: str
    details: str
    recommended_fix: str


@dataclass
class LinkRef:
    line: int
    link_text: str
    target: str


def normalize_target(raw: str) -> str:
    t = raw.strip()
    if t.startswith("<") and t.endswith(">"):
        t = t[1:-1].strip()
    return unquote(t)


def iter_links(md_path: Path) -> Iterable[LinkRef]:
    in_fence = False
    fence_marker = ""

    with md_path.open("r", encoding="utf-8", errors="ignore") as f:
        for line_no, line in enumerate(f, start=1):
            stripped = line.lstrip()

            if stripped.startswith("```") or stripped.startswith("~~~"):
                marker = stripped[:3]
                if not in_fence:
                    in_fence = True
                    fence_marker = marker
                elif marker == fence_marker:
                    in_fence = False
                    fence_marker = ""
                continue

            if in_fence:
                continue

            for m in LINK_RE.finditer(line):
                link_text = m.group(2).strip()
                target = normalize_target(m.group(3))
                yield LinkRef(line=line_no, link_text=link_text, target=target)


ANCHOR_CACHE: dict[Path, set[str]] = {}


def slugify_heading(text: str) -> str:
    value = text.strip()
    value = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", value)
    value = re.sub(r"`([^`]*)`", r"\1", value)
    value = re.sub(r"[*_~]", "", value)
    value = re.sub(r"&[a-zA-Z]+;", "", value)
    value = value.lower()
    value = re.sub(r"[^a-z0-9\-\s]", "", value)
    value = re.sub(r"\s+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value


def collect_anchors(md_path: Path) -> set[str]:
    cached = ANCHOR_CACHE.get(md_path)
    if cached is not None:
        return cached

    anchors: set[str] = set()
    in_fence = False
    fence_marker = ""

    with md_path.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            stripped = line.lstrip()
            if stripped.startswith("```") or stripped.startswith("~~~"):
                marker = stripped[:3]
                if not in_fence:
                    in_fence = True
                    fence_marker = marker
                elif marker == fence_marker:
                    in_fence = False
                    fence_marker = ""
                continue

            if in_fence:
                continue

            for m in HTML_ID_RE.finditer(line):
                anchors.add(m.group(1).strip().lower())

            hm = HEADING_RE.match(stripped)
            if hm:
                heading_text = hm.group(2)
                heading_text = re.sub(r"\s+#+\s*$", "", heading_text)
                slug = slugify_heading(heading_text)
                if slug:
                    anchors.add(slug)

    ANCHOR_CACHE[md_path] = anchors
    return anchors


def validate_link(repo_root: Path, source: Path, link: LinkRef) -> Issue | None:
    target = link.target

    if not target:
        return Issue(
            source_file=str(source.relative_to(repo_root)),
            line=link.line,
            link_text=link.link_text,
            target=target,
            issue_type="EMPTY_TARGET",
            details="Link target is empty.",
            recommended_fix="Provide a valid relative target.",
        )

    lowered = target.lower()

    if lowered.startswith(EXTERNAL_SCHEMES):
        return None

    if lowered.startswith("file://") or lowered.startswith("vscode://"):
        return Issue(
            source_file=str(source.relative_to(repo_root)),
            line=link.line,
            link_text=link.link_text,
            target=target,
            issue_type="ABSOLUTE_URI",
            details="Absolute URI used instead of repository-relative path.",
            recommended_fix="Replace with a relative path from source document.",
        )

    if target.startswith("#"):
        fragment = target[1:].strip().lower()
        if not fragment:
            return None
        anchors = collect_anchors(source)
        if fragment not in anchors:
            return Issue(
                source_file=str(source.relative_to(repo_root)),
                line=link.line,
                link_text=link.link_text,
                target=target,
                issue_type="MISSING_ANCHOR",
                details="Anchor not found in source file.",
                recommended_fix="Use an existing heading slug or add a matching heading.",
            )
        return None

    path_part, fragment = (target.split("#", 1) + [""])[:2]
    rel_path = Path(path_part)
    resolved = (source.parent / rel_path).resolve()

    try:
        resolved.relative_to(repo_root.resolve())
    except ValueError:
        return Issue(
            source_file=str(source.relative_to(repo_root)),
            line=link.line,
            link_text=link.link_text,
            target=target,
            issue_type="OUTSIDE_REPO",
            details="Relative target resolves outside repository root.",
            recommended_fix="Use an in-repo relative path.",
        )

    if not resolved.exists():
        return Issue(
            source_file=str(source.relative_to(repo_root)),
            line=link.line,
            link_text=link.link_text,
            target=target,
            issue_type="MISSING_PATH",
            details="Relative target path does not exist.",
            recommended_fix="Update to the correct existing file or directory path.",
        )

    if fragment:
        if resolved.is_file() and resolved.suffix.lower() == ".md":
            anchors = collect_anchors(resolved)
            if fragment.lower() not in anchors:
                return Issue(
                    source_file=str(source.relative_to(repo_root)),
                    line=link.line,
                    link_text=link.link_text,
                    target=target,
                    issue_type="MISSING_ANCHOR",
                    details=f"Anchor '{fragment}' not found in target markdown file.",
                    recommended_fix="Use an existing heading slug in target file.",
                )
        else:
            return Issue(
                source_file=str(source.relative_to(repo_root)),
                line=link.line,
                link_text=link.link_text,
                target=target,
                issue_type="ANCHOR_ON_NON_MARKDOWN",
                details="Anchor fragment used on non-markdown target.",
                recommended_fix="Remove fragment or point to a markdown file with that anchor.",
            )

    return None


def run(repo_root: Path) -> tuple[list[Issue], int, int]:
    markdown_files = sorted(
        p
        for p in repo_root.rglob("*.md")
        if not any(part in IGNORED_DIR_NAMES for part in p.parts)
    )
    issues: list[Issue] = []
    links_checked = 0

    for md in markdown_files:
        for link in iter_links(md):
            links_checked += 1
            issue = validate_link(repo_root, md, link)
            if issue is not None:
                issues.append(issue)

    return issues, len(markdown_files), links_checked


def write_csv(path: Path, issues: list[Issue]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "source_file",
                "line",
                "link_text",
                "target",
                "issue_type",
                "details",
                "recommended_fix",
            ]
        )
        for i in issues:
            writer.writerow(
                [
                    i.source_file,
                    i.line,
                    i.link_text,
                    i.target,
                    i.issue_type,
                    i.details,
                    i.recommended_fix,
                ]
            )


def main() -> int:
    parser = argparse.ArgumentParser(description="Strict markdown link checker (path + anchors).")
    parser.add_argument("--repo", default=".", help="Repository root path")
    parser.add_argument(
        "--csv",
        default=".copilot-tracking/link-integrity/markdown-link-issues.csv",
        help="Output CSV path",
    )
    parser.add_argument(
        "--strict-exit",
        action="store_true",
        help="Exit non-zero when issues are found",
    )
    args = parser.parse_args()

    repo_root = Path(args.repo).resolve()
    issues, files_scanned, links_checked = run(repo_root)

    csv_path = Path(args.csv)
    if not csv_path.is_absolute():
        csv_path = repo_root / csv_path
    write_csv(csv_path, issues)

    print(f"Markdown files scanned: {files_scanned}")
    print(f"Internal markdown links checked: {links_checked}")
    print(f"Issues found: {len(issues)}")
    print(f"CSV report: {csv_path}")

    if issues:
        print("Top issues:")
        for issue in issues[:20]:
            print(
                f"- {issue.source_file}:{issue.line} [{issue.issue_type}] {issue.target}"
            )

    if args.strict_exit and issues:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
