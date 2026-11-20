#!/usr/bin/env python3
"""section_map.py — какие разделы Текста изменились и насколько.

Печатает по каждому файлу разделы (ближайший заголовок над добавленной
строкой) и число добавленных строк. Это карта кандидатов для дайджеста:
372 строки в главе выглядят как десять разных идей, пока не увидишь, что 65
из них в одном разделе.

    cd "$WTD_DIR"  # path to the WTD checkout
    python3 <skill>/scripts/section_map.py --base 5d7f83b^
    python3 <skill>/scripts/section_map.py --base 5d7f83b^ --new-headings
    python3 <skill>/scripts/section_map.py --base 5d7f83b^ text/p2-110-system.md

--new-headings отвечает на другой вопрос: какие разделы появились, а не выросли
(«новый раздел» в посте — не то же самое, что «существенно расширена»).

Без аргументов-файлов берётся wtd-скоуп: text/p1-*.md, text/p2-*.md,
text/index.md — книги и генерируемый p3 в дайджест не входят.

Stdlib only; читает через git и рабочее дерево не требует.
"""

from __future__ import annotations

import argparse
import collections
import re
import subprocess
import sys

SCOPE = [":(glob)text/p1-*.md", ":(glob)text/p2-*.md", "text/index.md"]
HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
HEADING = re.compile(r"^(#{2,4})\s+(.*?)\s*(?:\{#([\w-]+)\})?\s*$")


def git(*args: str) -> str:
    proc = subprocess.run(["git", *args], capture_output=True, text=True)
    if proc.returncode != 0:
        sys.exit(f"git {' '.join(args)}: {proc.stderr.strip()}")
    return proc.stdout


def files_of(base: str, wanted: list[str]) -> list[str]:
    if wanted:
        return wanted
    out = git("diff", f"{base}..HEAD", "--name-only", "--", *SCOPE)
    return [line for line in out.splitlines() if line.strip()]


def headings(text: str) -> list[tuple[int, int, str, str]]:
    found = []
    for number, line in enumerate(text.splitlines(), 1):
        match = HEADING.match(line)
        if match:
            found.append((number, len(match.group(1)), match.group(2), match.group(3) or ""))
    return found


def added_lines(base: str, path: str) -> list[int]:
    """Номера строк в новой версии файла, появившиеся в диапазоне."""
    diff = git("diff", f"{base}..HEAD", "-U0", "--", path)
    numbers: list[int] = []
    start = 0
    for line in diff.splitlines():
        match = HUNK.match(line)
        if match:
            start = int(match.group(1))
            continue
        if line.startswith("+") and not line.startswith("+++"):
            numbers.append(start)
            start += 1
    return numbers


def changed_sections(base: str, path: str) -> collections.Counter:
    heads = headings(git("show", f"HEAD:{path}"))
    per: collections.Counter = collections.Counter()
    for number in added_lines(base, path):
        current = None
        for line_no, level, title, anchor in heads:
            if line_no > number:
                break
            current = (level, title, anchor)
        per[current] += 1
    return per


def new_headings(base: str, path: str) -> list[str]:
    old = {head[2] for head in headings(git("show", f"{base}:{path}"))}
    fresh = [head for head in headings(git("show", f"HEAD:{path}")) if head[2] not in old]
    return [f"{'#' * level} {title}  #{anchor}" for _, level, title, anchor in fresh]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--base", required=True, metavar="REF", help="начало диапазона, напр. 5d7f83b^"
    )
    parser.add_argument(
        "--new-headings", action="store_true", help="только появившиеся разделы"
    )
    parser.add_argument("files", nargs="*", help="файлы; по умолчанию wtd-скоуп")
    args = parser.parse_args()

    for path in files_of(args.base, args.files):
        if args.new_headings:
            fresh = new_headings(args.base, path)
            if fresh:
                print(f"\n## {path}")
                for line in fresh:
                    print("   +", line)
            continue
        per = changed_sections(args.base, path)
        if not per:
            continue
        print(f"\n## {path}  (+{sum(per.values())})")
        for section, count in per.most_common():
            if section is None:
                print(f"  {count:4d}  (до первого заголовка)")
            else:
                level, title, anchor = section
                print(f"  {count:4d}  {'#' * level} {title[:70]}  #{anchor}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
