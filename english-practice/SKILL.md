---
name: english-practice
description: "Use when the author writes English: fix and log errors."
version: 0.2.0
author: Shag
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [english, language, learning, corrections]
---
# English Practice Skill

Turns every English conversation with the author into practice: serious mistakes
get corrected at the bottom of the reply, and every message is logged so recurring
patterns are measured instead of guessed. Not a course, not a grammar reference —
a low-friction correction loop with a memory.

## When to Use
- Any message the author writes in English (whole sentences — not a lone term,
  path or identifier inside otherwise non-English text).
- The author asks "how's my English?" / "stats" / "review my English" → Progress
  review.
- The author says "practice" / "drill" → Drill mode.
- Don't use for: non-English messages; English the author asks the agent to *write*
  for them (that's production — a passing note is fine, a Fixes block is not);
  quoted logs, code, error messages, identifiers.

## Correction contract

1. **Place** — the very last thing in the reply, after a `---` line. Never before
   the answer, never inside it.
2. **Threshold — serious only.** Include an item when a native speaker would read
   it as *wrong*: articles, tense/aspect, word order, agreement, prepositions, a
   word that shifts meaning, a missing auxiliary. Skip fast-typing typos, style
   preferences, valid synonyms, chat-level capitalization — unless it has been
   promoted (rule 5).
3. **Form** — one line per item, fragment-level:
   `1. "how you could" → "how could you" — question word order after *how*.`
   Fragment, arrow, reason in ≤ 12 words. No full-message rewrite, no lectures,
   no praise.
4. **Cap 5.** More than five real errors → list the five that change meaning most,
   then `(+N minor left unlisted)`.
5. **Promotion.** If the log shows the same skipped-as-minor issue three times,
   start listing it.
6. **Silence is the positive signal.** Zero errors → no block at all; `✓ no errors`
   is noise. Report only a *retired pattern*: "Article errors: 0 in the last 10
   messages."
7. **Same reply, always.** Never batch corrections for later — the context has to
   be live for the fix to stick.
8. **Log every message**, zero-error ones included — otherwise the rate is a lie.

## Procedure
1. **Answer normally.** The correction never delays or replaces the content.
2. **Log the message** — one `terminal` call, every English message:
   ```
   python3 <skill-dir>/scripts/english_log.py add --words <n> [--cat articles,tense] [--note "…"]
   ```
   `<skill-dir>` is this skill's own directory, so the command stays portable
   across checkouts. `--words` = word count of the author's message; `--cat` = the
   categories you actually listed (omit when none). Completion: exit code 0.
3. **Append the Fixes block** only when `--cat` was non-empty. Completion: the
   reply ends with it and it holds ≤ 5 items.

## Progress review
1. `<skill-dir>/scripts/english_log.py stats --days 30` — messages, fixes per
   message, weekly trend, category counts, top 3.
2. Report in this order: fixes per message now vs earlier weeks; top 3 categories;
   a previously top category that disappeared; one drill target for the current
   #1.
3. Numbers only. No "great improvement" — adjectives are not evidence.

## Drill mode (on request)
Five short tasks on the #1 logged category, built from the author's own past
mistakes: the faulty fragment, then the correct form on the next line prefixed
with `>`. Nothing to grade, no points, no gamification.

## Categories (fixed vocabulary — the script validates)
`articles`, `tense`, `word-order`, `prepositions`, `agreement`, `vocabulary`,
`punctuation`, `spelling`, `other`.

## Pitfalls
- Correcting code, paths, command output, or non-English words inside an English
  sentence — not the author's prose, wastes a line of a five-line budget.
- Drifting into a style critique: unidiomatic is not wrong; only wrong goes in.
- Rewriting the whole message when one fragment was off — reads as a lecture, and
  then the block gets skipped entirely.
- Skipping the log step on a clean message: the log keeps only bad days and every
  trend inflates.
- The error log lives in `references/errors.jsonl`; `references/` is gitignored by
  repo convention. Never move the log into tracked files — it is personal data.
- The skill loader is cached per session — an edit to this file takes effect in
  the next session.

## Verification
- Every English reply either ends with a ≤ 5-item Fixes block or has a logged
  zero-error record for that message.
- `stats --days 7` returns a message count equal to the English messages exchanged.
- A progress review quotes script numbers, not impressions.
