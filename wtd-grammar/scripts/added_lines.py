#!/usr/bin/env python3
"""git diff BASE..HEAD -> {file: [[new_line_no, text], ...]} for added lines.

Usage: added_lines.py BASE_REF [-- pathspec ...]
Writes build/added_lines.json. Numbers are post-image line numbers, which is
what a report needs; `git diff | grep '^+'` throws them away with the headers.
Pass pathspecs explicitly: in git `text/*.md` also matches `text/books/*.md`.
"""
import collections
import json
import os
import re
import subprocess
import sys


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    base = argv[0]
    rest = argv[1:]
    if rest and rest[0] == '--':
        rest = rest[1:]
    scope = rest or ['text/p*.md', 'text/index.md']

    files = subprocess.run(
        ['git', 'diff', '--name-only', base + '..HEAD', '--', *scope],
        capture_output=True, text=True, check=True).stdout.split()

    out = collections.OrderedDict()
    hunk = re.compile(r'^@@ -\d+(?:,\d+)? \+(\d+)')
    for f in files:
        diff = subprocess.run(
            ['git', 'diff', '-U0', base + '..HEAD', '--', f],
            capture_output=True, text=True, check=True).stdout.splitlines()
        line_no = 0
        rows = []
        for ln in diff:
            m = hunk.match(ln)
            if m:
                line_no = int(m.group(1))
                continue
            if ln.startswith(('+++', '---')):
                continue
            if ln.startswith('+'):
                rows.append((line_no, ln[1:]))
                line_no += 1
            elif not ln.startswith('-'):
                line_no += 1
        out[f] = rows

    os.makedirs('build', exist_ok=True)
    json.dump(out, open('build/added_lines.json', 'w'), ensure_ascii=False)
    for f, rows in out.items():
        print(f'### {f}  (+{len(rows)})')
    print('TOT', sum(len(r) for r in out.values()))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
