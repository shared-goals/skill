#!/usr/bin/env python3
"""Выгрузить каталог правил orfogrammka.ru в JSON [{section, title, url}].

Usage: scrape_rules.py [out.json]   (по умолчанию: orfogrammka-rules.json)

Разделы отдают ссылки в percent-encoded виде, текст ссылки стоит сразу после
href. URL в JSON раскодирован (кириллицей) — так он читаем и в markdown, и в
браузере. Полный индекс нужен, чтобы в отчёте выбирать существующее правило,
а не сочинять URL.
"""
import json
import re
import subprocess
import sys
import urllib.parse
from collections import Counter

BASE = "https://orfogrammka.ru"
SECTIONS = ["/орфография", "/пунктуация", "/грамматика", "/стилистика",
            "/типографика", "/семантика", "/буква_ё"]


def get(path):
    url = BASE + urllib.parse.quote(path)
    return subprocess.run(["curl", "-sS", "-L", "--max-time", "40", url],
                          capture_output=True, text=True).stdout


def main(out_path="orfogrammka-rules.json"):
    rows = []
    for sect in SECTIONS:
        page = get(sect)
        prefix = urllib.parse.unquote(sect) + "/"
        seen = set()
        for href, anchor in re.findall(r'href="(/[^"]*)"[^>]*>([^<]{1,200})</a>', page):
            url = urllib.parse.unquote(href)
            if not url.startswith(prefix) or url in seen:
                continue
            seen.add(url)
            title = " ".join(anchor.split()).strip()
            if title:
                rows.append({"section": urllib.parse.unquote(sect),
                             "title": title, "url": BASE + url})
    rows.sort(key=lambda r: (r["section"], r["title"]))
    json.dump(rows, open(out_path, "w"), ensure_ascii=False, indent=1)
    print(f"rules: {len(rows)} -> {out_path}")
    print(Counter(r["section"] for r in rows))


if __name__ == "__main__":
    main(*sys.argv[1:2])
