#!/usr/bin/env python3
"""English practice log: append one record per English message, print stats.

Records are JSONL, one per message, including zero-error messages so that
"fixes per message" is a real rate rather than a survivor count.

Usage:
    english_log.py add --words 42 [--cat articles,tense] [--note "..."]
    english_log.py stats [--days 30]
    english_log.py recent [-n 10]
    english_log.py categories
"""

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

DEFAULT_LOG = Path(__file__).resolve().parent.parent / "references" / "errors.jsonl"

CATEGORIES = [
    "articles",
    "tense",
    "word-order",
    "prepositions",
    "agreement",
    "vocabulary",
    "punctuation",
    "spelling",
    "other",
]


def log_path(explicit=None):
    if explicit:
        return Path(explicit).expanduser()
    env = os.environ.get("ENGLISH_LOG")
    return Path(env).expanduser() if env else DEFAULT_LOG


def parse_cats(raw):
    if not raw:
        return []
    cats = [c.strip() for c in raw.split(",") if c.strip()]
    bad = [c for c in cats if c not in CATEGORIES]
    if bad:
        sys.exit(f"unknown categories: {', '.join(bad)}\nvalid: {', '.join(CATEGORIES)}")
    return cats


def read_records(path):
    if not path.exists():
        return []
    out = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def cmd_add(args):
    path = log_path(args.log)
    path.parent.mkdir(parents=True, exist_ok=True)
    cats = parse_cats(args.cat)
    rec = {
        "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
        "date": date.today().isoformat(),
        "words": max(0, args.words),
        "cats": cats,
        "note": args.note or "",
    }
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"logged {rec['date']}: {rec['words']}w, {len(cats)} fix(es){' [' + ','.join(cats) + ']' if cats else ''}")


def cmd_stats(args):
    path = log_path(args.log)
    records = read_records(path)
    if args.days:
        cutoff = date.today() - timedelta(days=args.days)
        records = [r for r in records if date.fromisoformat(r["date"]) >= cutoff]
    if not records:
        print("no records yet")
        return

    total_msgs = len(records)
    total_fixes = sum(len(r["cats"]) for r in records)
    total_words = sum(r["words"] for r in records)

    print(f"window: {args.days or 'all'} days | messages: {total_msgs} | words: {total_words}")
    print(f"fixes/message: {total_fixes / total_msgs:.2f} | clean messages: {sum(1 for r in records if not r['cats'])}")

    weeks = defaultdict(lambda: [0, 0])
    for r in records:
        d = date.fromisoformat(r["date"])
        key = d - timedelta(days=d.weekday())
        weeks[key.isoformat()][0] += 1
        weeks[key.isoformat()][1] += len(r["cats"])
    print("\nper week (week starting Mon):")
    for key in sorted(weeks):
        msgs, fixes = weeks[key]
        print(f"  {key}  msgs {msgs:>3}  fixes {fixes:>3}  per msg {fixes / msgs:.2f}")

    counts = Counter(c for r in records for c in r["cats"])
    print("\nby category:")
    for cat, n in counts.most_common():
        print(f"  {cat:<12} {n}")
    if not counts:
        print("  (none)")


def cmd_recent(args):
    path = log_path(args.log)
    records = read_records(path)
    if not records:
        print("no records yet")
        return
    for r in records[-args.n:]:
        cats = ",".join(r["cats"]) or "-"
        note = f"  {r['note']}" if r.get("note") else ""
        print(f"{r['date']}  {r['words']:>4}w  {cats}{note}")


def cmd_categories(_args):
    print("\n".join(CATEGORIES))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--log", help="override log path (default: data/errors.jsonl next to this skill)")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("add")
    a.add_argument("--words", type=int, required=True)
    a.add_argument("--cat", default="")
    a.add_argument("--note", default="")
    a.set_defaults(func=cmd_add)

    s = sub.add_parser("stats")
    s.add_argument("--days", type=int, default=0)
    s.set_defaults(func=cmd_stats)

    r = sub.add_parser("recent")
    r.add_argument("-n", type=int, default=10)
    r.set_defaults(func=cmd_recent)

    c = sub.add_parser("categories")
    c.set_defaults(func=cmd_categories)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
