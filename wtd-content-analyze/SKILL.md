---
name: wtd-content-analyze
description: Compare outside content with WTD.
triggers:
  - "сравни видео с WTD"
  - "сравни текст с WTD"
  - "сравни статью с Что мне делать"
  - "analyze this video against WTD"
  - "analyze this article against WTD"
  - "compare this content with WTD"
  - "compare this sermon with WTD"
---

# WTD Content Analyze

Analyze an outside source — article, text page, YouTube video, sermon,
interview, transcript, or pasted excerpt — and compare it with the WTD corpus
(`Что мне делать? :-)`). The default deliverable is a concise chat report. Do
not create files unless the user explicitly asks for a lesson or another saved
artifact.

## Scope

This skill owns research and comparison:

1. retrieve and validate source text or transcript;
2. identify main ideas and source evidence;
3. recall WTD context from Hindsight using the `wtd` tag;
   synthesis is performed by the agent model, not by reflect;
4. verify exact WTD quotations against the local source repository;
5. compare common ground, different foundations, accents, and tensions;
6. formulate questions for discussion;
7. offer the user a lesson, but do not create one automatically.

`lesson-maker` owns HTML lesson generation and file delivery. If the user
accepts the offer to create a lesson, pass the completed analysis to
`lesson-maker` in `comparative-analysis` mode. Do not repeat the research.

## Sources and freshness

The authoritative WTD source is a local checkout of the public WTD repository.
Configure it with `WTD_REPO_PATH` or pass `--wtd-repo` to helper scripts. A
typical laptop layout is:

```text
~/Work/whattodo
```

Before searching it:

1. inspect the repository state;
2. run `git pull --ff-only` when the working tree permits it;
3. record the resulting commit and whether the pull succeeded;
4. use the local files for exact quotations and surrounding context.

Do not discard local changes, reset, rebase, or resolve conflicts automatically.
If a pull is blocked by local changes or fails, report that source freshness is
uncertain and continue only if the user has not required a fresh checkout.

**No checkout on this host? Use the published site.** Some hosts have no
checkout of the corpus at all — do not spend a step searching for one; go
straight to the published-site route. The corpus is a separate
content repo (`whattodo`), so grepping the skill/hermes tree for a person or
term finds only references and memory notes, never chapter text — don't conclude
the text is missing. The live corpus is the user's published WTD site — a
whattodo fork serves its own site via its CI `publish.yml` (the reference
deployment is https://text.sharedgoals.ru): one route
per chapter (`/p2-155-photo/`) with `#anchor` sections, plus a people index
(`/p2-100-authors/`) and cross-chapter links of the form
`<site>/<chapter>/#<anchor>`. Fast path for "search the WTD text for
X": grep `~/.hermes/cache/web/<site-host>-*.md` (e.g.
`text.sharedgoals.ru-*.md`; web_extract leaves
snapshots there) to locate the chapter, then `web_extract` that chapter page and
read the anchored section. Those cache files are stale snapshots — quote from
the live page, and report the source as the site rather than a pinned commit.
Cache snapshot filenames are hashes: identify which chapter a file holds by
grepping its head for the `https://<site>/<chapter>/` URL.

**One live fetch serves all quotes of a chapter.** `web_extract` saves the full
chapter text to a cache file (path in the result footer). Grep that saved file
for every quote candidate and its line numbers first; run additional live
fetches only for chapters not yet fetched. Do not re-fetch the live page once
per quote.

The WTD corpus is also loaded into Hindsight with tag `wtd`. Use Hindsight for
semantic recall and synthesis, not for unverifiable literal quotations.

## Workflow

### 1. Prepare the source

For web pages and articles, use extraction tools to retrieve title, author/date
when available, URL, and readable body text. For video or audio links, retrieve
metadata and a transcript. Validate that the source text is non-empty and
identify:

- title, author, date, duration;
- language;
- source type: article, page, manual transcript, automatic transcript,
  translated transcript, or unavailable;
- confidence: high, medium, or low.

**Retrieval order:**

1. **`web_extract` on the URL** — preferred for articles, pages, and video pages
  that expose transcript text.
2. **Browser transcript panel** — fallback for YouTube: open the watch page with
   `browser_navigate`, expand the description (`...more`), click
   «Show transcript», then read the panel text (segments appear as
   `N seconds <text>` rows). Works when `web_extract` returns an empty
   transcript.
3. **`youtube-content` helper / `prepare_content_comparison.py`** — only when
   the local network can reach YouTube without cloud-IP blocking. Known
  pitfall: some network/proxy paths expose a cloud IP that YouTube blocks for
  transcript APIs, so the helper may fail while `web_extract` still succeeds.

Do not claim to have visually watched the video unless visual analysis was
actually performed. For a sermon, transcript analysis is normally sufficient;
use video analysis only when the transcript is missing or materially inadequate.

### 2. Extract main ideas

Group the source text or transcript into coherent blocks. Each block needs:

- stable id such as `S1`;
- start and end timestamp when available;
- concise claim;
- one or two short supporting quotations;
- concepts/tags;
- confidence.

Keep claims traceable to the transcript. Do not turn a broad impression into a
claim about the speaker's intentions.

### 3. Recall WTD context

For every important source idea, create a small concept bundle containing:

- literal terms;
- synonyms and related concepts;
- contrasts and questions implied by the idea.

Use `hindsight_recall` with the `wtd` tag only as a coarse candidate search:
it returns fragmented facts, often mixed with unrelated history, so treat it
as raw material, never as the final synthesis.

Use **`hindsight_recall`** as the only Hindsight retrieval layer. **Do not call
reflect** — use recall for retrieval. Synthesis is the job of the **agent model**: it reasons
over recall bundles plus verified repository quotes and produces the comparison
itself.

Because recall is fragmented and noisy, compensate with coverage, not with a
single magic query: run several targeted recall queries (one per important
source idea), plus a broad one, and treat the union as raw material. The
quality of the comparison then rests on step 4 — verifying exact quotations
in the local WTD checkout — and on the agent's own synthesis, which must
connect the corpus concepts into a coherent picture (e.g. surface that
«молитва = малая регулярная инвестиция времени в разговор с Богом» and
resolve apparent tensions such as «мгновенно vs постепенно» into one
mechanism).

Do not silently substitute recall for reflect and present it as the same
layer — the report's limitations section must state that synthesis is
agent-side over recall.

In particular preserve these distinctions:


- happiness is an emergent result, not a deterministic target;
- vocation and shared goals remain human and changeable;
- Shared Goals proposes possibilities rather than commands;
- an AI assistant must not replace human will or assign a calling;
- probability and serendipity are features, not bureaucratic defects.

Recall previous Hermes discussions when they clarify an established user
correction or the history of a similar sermon, but label that material as
`previous discussion`, not as WTD source text.

### 4. Verify quotations

Treat Hindsight output as semantic context or paraphrase. For every quotation
presented as WTD text, verify it in the local WTD checkout and retain:

- file path;
- heading or section;
- line range when available;
- quote plus enough surrounding context.

Never silently turn a Hindsight paraphrase into a quotation.

### 5. Compare at three levels

For each meaningful correspondence, compare:

1. **Experience** — what human experience is being described?
2. **Explanation** — what account is given for it?
3. **Practice** — what should a person do?

Classify each comparison as one of:

- `shared-core` — substantially the same idea;
- `shared-direction-different-foundation` — same direction, different basis;
- `analogy-only` — useful metaphor, not conceptual identity;
- `real-tension` — the positions pull in different directions;
- `no-meaningful-match` — do not force a correspondence.

Do not use superficial vocabulary matches as evidence of identity.

## Default chat report

Use concise Markdown compatible with Telegram:

1. **Источник** — title, author/date, URL, source text or transcript quality,
  WTD source freshness.
2. **Краткий тезис источника** — two or three sentences before comparison.
3. **Основные смысловые моменты** — timestamped list with short quotations.
4. **Контекст WTD** — relevant concepts and verified source passages.
5. **Сравнение** — a compact table with these columns:
  `Источник | WTD | Общее | Различие акцента | Тип связи`.
6. **Главные пересечения** — only defensible common ground.
7. **Расхождения и напряжения** — do not harmonize them prematurely.
8. **Вопросы для живого разговора** — usually five to eight questions derived
   from actual differences.
9. **Ограничения** — transcript quality, unverified points, and whether visual
   analysis was performed.

Keep the report readable on a phone. Prefer a small table over a huge one; put
details in bullets below it. Preserve timestamps, URLs, and source references.

End with a non-invasive offer:

> Если хочешь, я могу превратить этот анализ в отдельный урок через
> `lesson-maker`.

Do not create the lesson until the user explicitly accepts.

## Lesson handoff

When the user accepts, invoke `lesson-maker` with the existing analysis and
request mode `comparative-analysis`. Pass structured context conceptually as:

```yaml
mode: comparative-analysis
title:
source:
analysis:
  thesis:
  main_ideas: []
  wtd_contexts: []
  comparison_rows: []
  convergences: []
  differences: []
  tensions: []
  discussion_questions: []
provenance:
  source_quality:
  wtd_git_commit:
  quotation_verification:
```

`lesson-maker` must preserve provenance, distinguish source quotations from WTD
quotations and Hindsight paraphrases, and use its existing lesson storage and
delivery rules.

## Guardrails

- Do not invent transcript content, timestamps, or WTD quotations.
- Do not present assistant interpretations as the speaker's claims.
- Do not reduce Shared Goals to a deterministic contract/reporting machine.
- Do not imply that AI assigns vocation, guarantees joy, or replaces faith,
  discernment, or human will.
- Do not create Markdown or HTML files by default.
- Do not publish, commit, or push skill changes without explicit approval.
- Keep the report focused on the supplied source and relevant WTD context.

## Deterministic preparation helper

Use `scripts/prepare_content_comparison.py` when a repeatable preparation step is useful. It refreshes the WTD checkout with `git pull --ff-only` only when the working tree is clean, records `git_state.json` and the current commit, inventories Markdown sources, and writes transcript metadata and text for video URLs. It is preparation only: it does not interpret the source or call Hindsight.

The helper invokes the Hermes-managed Python environment for the existing `youtube-content` transcript helper. A successful preparation packet must report both `git_pull_ok` and `transcript.ok`; do not infer either from the presence of output files alone.

## Dependencies

- extraction tools for pages and `youtube-content` for transcript extraction;
- Hindsight `recall` with tag `wtd` (reflect is retired — agent-side
  synthesis over recall instead);
- local WTD source checkout for exact quotations;
- `session_search` for prior sermons and user corrections;
- `lesson-maker` only after explicit user acceptance.

## Failure handling

- If source extraction or transcript retrieval fails, report the exact
  limitation and ask for source text or subtitles rather than inventing a
  summary.
- If WTD Hindsight retrieval fails, provide the transcript analysis only and
  clearly say that the comparison layer could not be completed. Do not retry
  reflect: it is retired for this workflow (see step 3).
- If the local WTD repository cannot be refreshed, state the commit used and
  mark quotation freshness as uncertain.
- If the sources genuinely do not correspond, say so explicitly.
