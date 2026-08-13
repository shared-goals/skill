#!/usr/bin/env python3
"""Lint the WTD llm-wiki (~/wiki by default, or $WIKI_PATH / argv[1]).

Checks:
  1. Broken [[wikilinks]] — targets that are not existing wiki pages.
  2. Orphan pages — no inbound [[wikilinks]] from other pages.
  3. index.md completeness — every page appears in the index.
  4. Frontmatter — required fields (title, created, updated, type, tags, sources).
  5. raw/text symlink coverage vs the source corpus repo.

Exit code 0 = healthy; 1 = issues found. Prints findings grouped by severity.

Usage:
    python3 lint.py [wiki_path]
"""
import os
import re
import sys
from collections import defaultdict

DEFAULT_WIKI = os.path.expanduser("~/wiki")
SOURCE_TEXT_DIR = "/Users/shag/Work/whattodo/text"
PAGE_DIRS = ["entities", "concepts", "comparisons", "queries"]
REQUIRED_FM = ["title", "created", "updated", "type", "tags", "sources"]


def collect_pages(wiki: str) -> dict:
    pages = {}
    for d in PAGE_DIRS:
        dpath = os.path.join(wiki, d)
        if not os.path.isdir(dpath):
            continue
        for f in sorted(os.listdir(dpath)):
            if f.endswith(".md"):
                pages[f[:-3]] = os.path.join(dpath, f)
    return pages


def main() -> int:
    wiki = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("WIKI_PATH", DEFAULT_WIKI)
    pages = collect_pages(wiki)
    if not pages:
        print(f"ERROR: no wiki pages found under {wiki}")
        return 2

    outbound = defaultdict(list)
    for slug, path in pages.items():
        content = open(path, encoding="utf-8").read()
        for m in re.finditer(r"\[\[([^\]]+)\]\]", content):
            outbound[slug].append(m.group(1).split("|")[0].strip())

    # 1. Broken wikilinks
    broken = {}
    for slug, targets in outbound.items():
        bad = sorted(set(t for t in targets if t not in pages))
        if bad:
            broken[slug] = bad

    # 2. Orphans
    inbound = defaultdict(list)
    for slug, targets in outbound.items():
        for t in targets:
            inbound[t].append(slug)
    orphans = sorted(slug for slug in pages if not inbound[slug])

    # 3. Index completeness
    index_path = os.path.join(wiki, "index.md")
    index_content = open(index_path, encoding="utf-8").read() if os.path.exists(index_path) else ""
    not_in_index = sorted(slug for slug in pages if f"[[{slug}]]" not in index_content)

    # 4. Frontmatter
    missing_fm = {}
    for slug, path in pages.items():
        content = open(path, encoding="utf-8").read()
        if not content.startswith("---"):
            missing_fm[slug] = ["no frontmatter"]
            continue
        fm = content.split("---", 2)[1]
        miss = [f for f in REQUIRED_FM if not re.search(rf"^{f}:", fm, re.M)]
        if miss:
            missing_fm[slug] = miss

    # 5. raw symlink coverage
    raw_dir = os.path.join(wiki, "raw", "text")
    raw_md = {f for f in os.listdir(raw_dir) if f.endswith(".md")} if os.path.isdir(raw_dir) else set()
    src_md = {f for f in os.listdir(SOURCE_TEXT_DIR) if f.endswith(".md")} if os.path.isdir(SOURCE_TEXT_DIR) else set()
    missing_raw = sorted(src_md - raw_md)

    issues = []
    if broken:
        issues.append(f"BROKEN WIKILINKS ({sum(len(v) for v in broken.values())}):")
        for slug in sorted(broken):
            issues.append(f"  {slug}: {broken[slug]}")
    if orphans:
        issues.append(f"ORPHANS ({len(orphans)}): {orphans}")
    if not_in_index:
        issues.append(f"NOT IN index.md ({len(not_in_index)}): {not_in_index}")
    if missing_fm:
        issues.append(f"FRONTMATTER ISSUES ({len(missing_fm)}):")
        for slug in sorted(missing_fm):
            issues.append(f"  {slug}: {missing_fm[slug]}")
    if missing_raw:
        issues.append(f"MISSING raw/text SYMLINKS ({len(missing_raw)}): {missing_raw}")

    print(f"Wiki: {wiki}")
    print(f"Pages: {len(pages)} "
          f"(entities={len(os.listdir(os.path.join(wiki, 'entities')))}, "
          f"concepts={len(os.listdir(os.path.join(wiki, 'concepts')))}, "
          f"comparisons={len(os.listdir(os.path.join(wiki, 'comparisons')))})")
    if issues:
        print("\n" + "\n\n".join(issues))
        return 1
    print("All checks passed: no broken links, no orphans, index complete, frontmatter valid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
