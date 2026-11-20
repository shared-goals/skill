#!/usr/bin/env python3
"""Mechanical typography pass over added lines.

Usage: scan_typography.py [build/added_lines.json]
Reports: double spaces inside a phrase, space before punctuation, latin letters
inside cyrillic words. Trailing double space is a markdown line break, so it is
reported separately rather than as an error.
"""
import json
import re
import sys

CYR = re.compile(r'[а-яА-ЯёЁ]')
LAT = re.compile(r'[a-zA-Z]')
WORD = re.compile(r'^[^\wа-яА-ЯёЁ]+|[^\wа-яА-ЯёЁ]+$')


def main(path='build/added_lines.json'):
    data = json.load(open(path))
    inner, trailing, before_punct, homoglyph = [], [], [], []
    for f, rows in data.items():
        for n, t in rows:
            if not t.strip():
                continue
            if re.search(r'\S  +\S', t):
                inner.append((f, n, t.strip()[:90]))
            elif re.search(r'\S  +$', t):
                trailing.append((f, n, t.strip()[-60:]))
            if re.search(r'\s+[.,;:](?=\s|$)', t):
                before_punct.append((f, n, t.strip()[-70:]))
            for w in re.findall(r'\S+', t):
                core = WORD.sub('', w)
                if len(core) < 3 or 'http' in w or '](' in w or '#' in core:
                    continue
                if CYR.search(core) and LAT.search(core):
                    homoglyph.append((f, n, core))

    for title, rows in (('DOUBLE-SPACE (inside phrase)', inner),
                        ('TRAILING-DOUBLE-SPACE (likely markdown break)', trailing),
                        ('SPACE-BEFORE-PUNCT', before_punct),
                        ('LATIN/CYR MIX (homoglyph)', homoglyph)):
        print(f'{title}: {len(rows)}')
        for f, n, frag in rows:
            print('   ', f, n, repr(frag))


if __name__ == '__main__':
    main(*sys.argv[1:2])
