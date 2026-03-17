#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def extract_status(text: str) -> str:
    fm_match = re.search(r"(?ms)^---\n(.*?)\n---\n", text)
    if fm_match:
        frontmatter = fm_match.group(1)
        status_match = re.search(r"(?im)^status\s*:\s*\"?([^\n\"]+)\"?\s*$", frontmatter)
        if status_match:
            return status_match.group(1).strip()

    md_match = re.search(r"(?im)^\*\*Status:\*\*\s*(.+?)\s*$", text)
    if md_match:
        return md_match.group(1).strip()

    return "UNSPECIFIED"


def extract_version(text: str) -> str:
    fm_match = re.search(r"(?ms)^---\n(.*?)\n---\n", text)
    if fm_match:
        frontmatter = fm_match.group(1)
        for key in ("version", "ms.date"):
            m = re.search(rf"(?im)^{re.escape(key)}\s*:\s*\"?([^\n\"]+)\"?\s*$", frontmatter)
            if m and key == "version":
                return m.group(1).strip()

    md_match = re.search(r"(?im)^\*\*Version:\*\*\s*(.+?)\s*$", text)
    if md_match:
        return md_match.group(1).strip()

    return ""


def extract_title(text: str, rel_path: str) -> str:
    fm_match = re.search(r"(?ms)^---\n(.*?)\n---\n", text)
    if fm_match:
        frontmatter = fm_match.group(1)
        title_match = re.search(r"(?im)^title\s*:\s*\"?([^\n\"]+)\"?\s*$", frontmatter)
        if title_match:
            return title_match.group(1).strip()

    h1 = re.search(r"(?m)^#\s+(.+?)\s*$", text)
    if h1:
        return h1.group(1).strip()

    return rel_path


def broken_links(path: Path, text: str) -> list[str]:
    links = []
    for match in re.finditer(r"\[[^\]]+\]\(([^)]+)\)", text):
        target = match.group(1).strip()
        if target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        target = target.split("#", 1)[0].strip()
        if not target or target.startswith("<"):
            continue
        resolved = (path.parent / target).resolve()
        if not resolved.exists():
            links.append(match.group(1).strip())
    return sorted(set(links))


def collect_markdown() -> list[Path]:
    files = set()

    for p in (ROOT / "docs").rglob("*.md"):
        files.add(p)
    for p in (ROOT / "openspec").rglob("*.md"):
        files.add(p)

    for name in ("README.md", "CHANGELOG.md", "CONTRIBUTING.md", "AGENTS.md"):
        p = ROOT / name
        if p.exists():
            files.add(p)

    return sorted(files)


def main() -> None:
    files = collect_markdown()
    records = []
    broken_link_records = []
    missing_version_docs = []

    for path in files:
        rel = path.relative_to(ROOT).as_posix()
        text = read_text(path)
        status = extract_status(text)
        version = extract_version(text)
        title = extract_title(text, rel)
        links = broken_links(path, text)

        if links:
            broken_link_records.append({"path": rel, "links": links})
        if rel.startswith("docs/") and not version:
            missing_version_docs.append(rel)

        records.append(
            {
                "path": rel,
                "status": status,
                "version": version,
                "title": title,
                "lines": len(text.splitlines()),
                "broken_links": links,
            }
        )

    counts = {
        "total": len(records),
        "docs": sum(1 for r in records if r["path"].startswith("docs/")),
        "openspec": sum(1 for r in records if r["path"].startswith("openspec/")),
        "phases": sum(1 for r in records if r["path"].startswith("phases/")),
        "root": sum(1 for r in records if "/" not in r["path"]),
    }

    status_counts: dict[str, int] = {}
    for r in records:
        key = r["status"]
        status_counts[key] = status_counts.get(key, 0) + 1

    payload = {
        "generated": str(date.today()),
        "counts": counts,
        "status_counts": dict(sorted(status_counts.items(), key=lambda kv: kv[0].lower())),
        "missing_version_docs": sorted(missing_version_docs),
        "broken_links": sorted(broken_link_records, key=lambda x: x["path"]),
        "records": records,
    }

    out_dir = ROOT / "docs" / "reports" / "audit-data"
    out_dir.mkdir(parents=True, exist_ok=True)

    today = date.today().isoformat()
    json_path = out_dir / f"documentation_audit_{today}.json"
    csv_path = out_dir / f"documentation_inventory_{today}.csv"

    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["path", "status", "version", "title", "lines", "broken_link_count"],
        )
        writer.writeheader()
        for r in records:
            writer.writerow(
                {
                    "path": r["path"],
                    "status": r["status"],
                    "version": r["version"],
                    "title": r["title"],
                    "lines": r["lines"],
                    "broken_link_count": len(r["broken_links"]),
                }
            )

    print(f"Wrote: {json_path.relative_to(ROOT)}")
    print(f"Wrote: {csv_path.relative_to(ROOT)}")
    print(f"Counts: {counts}")
    print(f"Broken-link files: {len(broken_link_records)}")


if __name__ == "__main__":
    main()
