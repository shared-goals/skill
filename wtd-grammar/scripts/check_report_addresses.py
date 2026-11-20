#!/usr/bin/env python3
"""Проверить отчёт вычитки механически: адрес `файл:строка` и цитату против диска.

Usage: check_report_addresses.py REPORT.md [ROOT] [--strict]

Зачем: отчёт пишет модель, а находок десятки. Глазами проверяются две-три;
остальные уезжают к автору с выдуманными адресами, и он ищет строку вручную.
Один прогон этого скрипта отвечает на вопрос «все ли адреса настоящие».

Нормализация обязательна: отчёт по контракту печатает цитату БЕЗ целей ссылок
(`](...)`), а в файле они есть — наивное сравнение даёт ложное «не совпало»
почти на каждой находке. Снимаем `](...)`, `[`, `]`, `*`, `_`, backticks,
сжимаем пробелы, многоточие считаем границей фрагмента.

Выход: 0 — все находки сходятся, 1 — есть расхождения (они напечатаны).
"""
import re
import sys
from pathlib import Path

LINK = re.compile(r"\]\([^)]*\)")
NOISE = re.compile(r"[*_`\[\]]")
ADDRESS = re.compile(r"^`([^`:]+\.md):(\d+)`", re.M)
QUOTE = re.compile(r"^>\s?(.*)$", re.M)


def norm(text: str) -> str:
    text = LINK.sub("]", text)
    text = NOISE.sub("", text)
    text = text.replace("…", " ").replace("...", " ")
    return re.sub(r"\s+", " ", text).strip()


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 1
    report_path = Path(argv[0])
    strict = "--strict" in argv
    args = [a for a in argv[1:] if not a.startswith("--")]
    root = Path(args[0]) if args else Path.cwd()

    report = report_path.read_text(encoding="utf-8")
    blocks = re.split(r"\n(?=### )", report)

    ok = bad = noaddr = 0
    for block in blocks:
        if not block.startswith("### "):
            continue
        head = block.splitlines()[0][:90]
        match = ADDRESS.search(block)
        if not match:
            noaddr += 1
            print("NO ADDRESS:", head)
            continue
        rel, line = match.group(1).strip(), int(match.group(2))
        path = root / rel
        if not path.exists():
            bad += 1
            print(f"NO FILE    {rel}:{line} :: {head}")
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        if line > len(lines):
            bad += 1
            print(f"OUT OF RNG {rel}:{line} (len {len(lines)}) :: {head}")
            continue
        quote = QUOTE.search(block)
        if not quote:
            ok += 1  # находка без цитаты — адрес проверен, больше нечего
            continue
        actual = norm(lines[line - 1])
        wanted = norm(quote.group(1))
        hit = bool(wanted) and (wanted in actual or actual in wanted)
        if not hit:  # цитата может быть усечена: сверяем слова по порядку
            pos = 0
            hit = True
            for word in wanted.split():
                found = actual.find(word, pos)
                if found < 0:
                    hit = False
                    break
                pos = found + len(word)
        if hit:
            ok += 1
        else:
            bad += 1
            print(
                f"MISMATCH   {rel}:{line}\n"
                f"   report: {quote.group(1)[:110]}\n"
                f"   actual: {lines[line - 1][:110]}"
            )

    print(f"\nok={ok} mismatch={bad} no_address={noaddr}")
    if bad or (strict and noaddr):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
