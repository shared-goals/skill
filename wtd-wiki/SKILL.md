---
name: wtd-wiki
description: "Maintain ~/wiki, the llm-wiki over the WTD text corpus."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [wiki, knowledge-base, wtd, shared-goals, research]
    category: shared-goals
    related_skills: [llm-wiki, obsidian, wtd-video-analyze]
---

# WTD Wiki

Maintain the knowledge wiki at `~/wiki`, built over Сергей Поляков's living
text corpus «Что мне делать? :-)» (WTD). The corpus source of truth is the git
repo `/Users/shag/Work/whattodo` (public: https://text.sharedgoals.ru).
The wiki is a map across the corpus: concept/entity/comparison pages with
wikilinks, exact quotations, and provenance markers — not a copy of the text.

## When to Use

- User asks to view, query, update, lint, or extend the WTD wiki (`~/wiki`)
- User asks to ingest new or changed WTD chapters into the wiki
- User asks a question about WTD concepts and the wiki is the fast path
  (alternative to Hindsight recall for the `wtd` tag)

## Wiki Layout

```
~/wiki/
├── SCHEMA.md        # domain, tag taxonomy, conventions (read first)
├── index.md         # catalog of every page, sectioned by type
├── log.md           # append-only action log (ingest/update/lint entries)
├── raw/text/        # SYMLINKS to /Users/shag/Work/whattodo/text/*.md
├── entities/        # people/orgs (authors, thinkers cited in corpus)
├── concepts/        # one page per concept (happiness, calling, faith, ...)
├── comparisons/     # side-by-side analyses
└── queries/         # filed query results (currently empty)
```

Pages: Russian body, Latin filenames (lowercase, hyphens). Every page has YAML
frontmatter (`title, created, updated, type, tags, sources`), ≥2 outbound
`[[wikilinks]]`, tags from the SCHEMA taxonomy. Provenance markers
`^[raw/text/<file>.md#anchor]` at the end of paragraphs synthesizing 3+
sources; single-source pages carry `sources:` frontmatter only.

## Key Deviation from Stock llm-wiki

- **`raw/text/` is symlinks to the source repo, NOT copies.** DRY: the corpus
  is a living git repo (~2.9 MB); copies would drift and bloat.
- **Never write sha256/frontmatter into raw files** — they are symlinked, an
  append would modify the source repo. Drift detection = git history of
  `/Users/shag/Work/whattodo`; record the commit hash in log.md on each ingest.
- This deviation is documented in `~/wiki/SCHEMA.md`; keep it in sync if the
  layout changes.

## Workflow

1. **Orient** (every session): read `SCHEMA.md`, `index.md`, last ~20 lines of
   `log.md`. Prevents duplicate pages and missed cross-references.
2. **Source layout**: `p1-*.md` observations, `p2-*.md` practice, `p3-*.md`
   summary/references. Every file has `{#anchor}` ids — use them in provenance
   (`p1-010-happiness.md#moments_of_happiness`).
3. **Read chapters in small batches** (1–3 at a time): files are 400–1300
   lines; reading everything at once floods context. Write pages per batch.
4. **Create/update pages**: new page only when a concept/entity appears in 2+
   chapters OR is central to one chapter. Pass on passing mentions.
5. **Update navigation**: every new page → `index.md` (alphabetical within
   section, bump "Total pages"), append `log.md` entry with source commit.
6. **Lint** (see below), fix broken links and orphans by adding backlinks to
   the "Связи" sections of related concept pages — entities and comparisons
   only get inbound links if you add them.

## Verification

```bash
python3 ~/.hermes/skills/shared-goals/wtd-wiki/scripts/lint.py   # default ~/wiki
WIKI_PATH=/path/to/wiki python3 .../lint.py
```

Checks: broken `[[wikilinks]]`, orphan pages (no inbound links), index.md
completeness, frontmatter required fields, raw/text symlink coverage vs the
source repo. Clean exit = healthy wiki.

## Pitfalls

- **Interrupted turns / provider errors**: after a turn dies mid-work, verify
  state on disk (run lint.py) before continuing — pending writes may or may not
  have landed; do not trust the conversation history alone.
- **Symlinked raw**: never edit files under `raw/text/`; the edit hits the
  source repo.
- **Orphans appear after every ingest** — new pages have no inbound links until
  you add backlinks from related pages. Lint surfaces them; fix in the same pass.
- **Index drift**: "Total pages" in index.md must match lint's page count.
- **Batch pages, don't drip**: create several pages per read batch, then update
  index.md once at the end of the batch.

## Related

- `llm-wiki` (generic Karpathy-wiki pattern; this skill documents the
  deviations applied for a living single-corpus source)
- `obsidian` (open `~/wiki` as a vault; graph view shows the link network)
- `wtd-video-analyze` (compare a video/sermon against the WTD corpus —
  complement to this wiki)
