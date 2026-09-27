# Daily Compass Refactoring Analysis

## Confirmed findings

- Daily Compass keeps useful domain logic: deterministic area boundary scripts, skill-owned prompts, platform next-step data, and four-dimension hunger ordering.
- It currently mixes deterministic collection, LLM orchestration, presentation-shaped JSON, custom YAML/template parsing, Hermes chat sessions, and memory behavior.
- Critical bug: `run_hermes_raw()` reconstructs the orchestration `HermesCallProfile` without carrying `skip_memory=True`; production calls therefore omit `--ignore-rules` and can auto-retain generated Compass conversations in Hindsight.
- Nested chat sessions also reuse named sessions across runs; empty toolsets do not explicitly restrict tools.
- The platform already computes `dimension_order`; Compass should not derive priority by parsing rendered `hunger:Nd` titles. Never-fed and contract-pressure semantics need explicit rules.
- Hindsight direct `reflect` is the correct read-only memory path. Generated recommendations are not facts and must not be retained.

## Proposed target

```text
Cron -> typed evidence collection -> scoped recall/reflect
     -> typed recommendations -> deterministic hunger/ranking
     -> validation -> render/deliver
```

Keep area skills and boundary scripts. Make platform/source evidence immutable; make LLM output recommendation-only with provenance and source IDs. Separate factual memory, temporary run artifacts, and user-confirmed commitments.

## Library direction

- Pydantic models plus `yaml.safe_load` for contracts/configuration (already in the Hermes venv).
- `hindsight-client` for recall/reflect only; no retain/write calls in Compass.
- `agent.auxiliary_client.call_llm` for model calls (stateless, uses configured auxiliary provider); Pydantic validation with one retry instead of PydanticAI.
- Jinja2 instead of the custom template interpreter.
- Keep Hermes script-only cron and bounded concurrency; no Prefect/LangGraph for this linear workflow.

## Cleanup (done 2026-09-21)

`runtime/hindsight-daily-compass-invalidation-manifest.json`: 8,617 raw memories under 38 Compass session tags invalidated, 0 remaining valid, 0 documents deleted. Re-run the tag audit after the first refactored live run (see T-MEM-3).

## Baseline (2026-09-27)

- Cron job `Daily Compass` is paused (`no_agent: true`, script `daily_compass_no_agent.py`, 08:00).
- Hindsight server `0.10.1`: reflect supports `response_schema`, `tags`/`tags_match`, `include.facts` (`based_on`), `fact_types`; mental models and directives exist.
- Cron interpreter (`hermes-agent/venv`, Python 3.11) already ships `pydantic 2.13`, `jinja2 3.1`, `PyYAML 6.0`, `hindsight-client 0.6.1`, `httpx`. The skill's uv dev env has none of them.
- Current work: Shared Goals uses direct `POST /reflect`; `run_hermes_raw()` now passes `skip_memory=True`, covered by a test asserting the production CLI invocation includes `--ignore-rules`.
- Any `hermes chat` / `--oneshot` call opens SessionDB and the memory provider; `--ignore-rules` suppresses injected context and persistent-memory reads, but does not prove that no memory writes occur. `agent.auxiliary_client.call_llm()` is stateless (no session, no memory provider).
- Reflect traces list a `learn` tool, so reflect write-freedom must be proven, not assumed.
- Size: `daily-compass.py` 1,345 lines, `daily_compass_shared.py` 972, tests 1,346 (script suite green).

## Success targets

| # | Target | Measured by |
|---|---|---|
| S1 | A full run creates **zero** Hindsight documents, memory units, or mental models and **zero** Hermes sessions. | T-MEM-1..3, T-E2E-1 |
| S2 | No Hermes agent subprocess: model calls go through a stateless client; memory access is recall/reflect only. | T-MEM-2, code search for `hermes chat`/`--oneshot` = 0 |
| S3 | Platform `dimension_order` is the only hunger source; never-fed dimensions rank first; ties are stable. | T-RANK-* |
| S4 | Evidence is immutable: LLM output can only add recommendation text/refs; titles, URLs, bodies, dimensions stay byte-equal. | T-CON-3, T-LLM-2 |
| S5 | Every recommendation carries `area`, `source_refs` (line ids and/or Hindsight memory ids from `based_on`). | T-CON-2, T-LLM-3 |
| S6 | One area failing (script error, timeout, LLM invalid twice, Hindsight down) degrades only that area; run still renders. | T-FAIL-* |
| S7 | Run finishes within cron limits: whole run ≤ 150 s, boundary scripts ≤ 45 s each, ≤ 1 LLM call per area + 1 synthesis. | T-E2E-2 |
| S8 | Custom YAML parser, template interpreter, session registry, CLI-output scraping, and `state/daily-compass-session.json` are deleted. | code review |
| S9 | Core code (models + pipeline + render, excluding area scripts) ≤ ~800 lines; boundary script contract unchanged so all 12 areas keep working without edits. | `wc -l`, T-CON-1 |
| S10 | Rendered Telegram output matches the current template structure (dimension order, area names, checklist lines) on fixtures. | T-REN-* |

## Target architecture

```text
no_agent cron -> daily_compass (hermes venv python)
  1 load areas      yaml.safe_load -> AreaConfig (pydantic)
  2 collect         boundary scripts in parallel -> Evidence (frozen)
  3 platform        GET /compass/shared-goals -> dimension_order + goals
  4 memory (read)   hindsight-client reflect(response_schema, tags, based_on)
  5 advise          call_llm(messages, response_format) -> AreaAdvice
  6 rank            deterministic: platform order, never-fed first, stable ties
  7 synthesize      one call_llm -> CompassSignal
  8 render          jinja2 template -> stdout (Telegram) + context snapshot
```

Modules: `compass/models.py`, `compass/collect.py`, `compass/memory.py`, `compass/advise.py`, `compass/rank.py`, `compass/render.py`, `daily-compass.py` (thin CLI).

## Tests

Unit tests run in the skill uv env (add `pydantic`, `jinja2`, `pyyaml`, `hindsight-client` as dev deps pinned to the Hermes venv majors). Live tests are marked `live` and skipped by default.

Contracts
- T-CON-1 Every `areas/*/scripts/daily-*-status.py` fixture output validates as `BoundaryPayload`; extra keys and bad status are rejected.
- T-CON-2 `AreaAdvice` rejects missing `source_refs`, refs not present in the area's evidence, and signals over `signal_max_chars`.
- T-CON-3 Merging advice into evidence never changes `title`/`url`/`body`/`dimension`.
- T-CON-4 Area YAML with unknown dimension or missing skill is skipped with a logged reason.

Ranking
- T-RANK-1 Output order equals platform `dimension_order`.
- T-RANK-2 Never-fed (`last_fed_at: null`) ranks before any fed dimension.
- T-RANK-3 Equal hunger keeps platform order (stable).
- T-RANK-4 Platform unavailable -> configured fallback order, flagged in output.

Memory safety
- T-MEM-1 Unit: memory adapter exposes only `recall`/`reflect`; no `retain`, no `learn`, no mental-model create; reflect sends `tags`/`tags_match` from area config.
- T-MEM-2 Unit: no code path spawns `hermes chat`/`--oneshot` (subprocess spy records zero Hermes argv).
- T-MEM-3 Live: snapshot bank stats (documents, memory units by type, mental models, operations) before/after one full run -> all deltas 0; SessionDB session count delta 0.

LLM boundary
- T-LLM-1 Valid structured response parses to `AreaAdvice`.
- T-LLM-2 Invalid JSON or schema error retries once with the validation error, then marks the area `advice_failed` with evidence intact.
- T-LLM-3 Reflect `structured_output` + `based_on` ids propagate into `source_refs`; `structured_output_error` falls back to text.

Failure isolation
- T-FAIL-1 Boundary script timeout/non-zero exit -> area `error`, others render.
- T-FAIL-2 Hindsight HTTP 500 / timeout -> Shared Goals advice omitted, evidence rendered.
- T-FAIL-3 LLM provider down -> run renders evidence-only Compass with exit 0.

Rendering
- T-REN-1 Golden fixture: fixed runtime -> byte-equal Markdown.
- T-REN-2 Signals are single-line, fence-safe, and truncated on word boundary.
- T-REN-3 Empty dimension still renders its heading.

End-to-end
- T-E2E-1 `daily-compass.py --dry-run` with fake collectors, fake Hindsight, fake LLM produces the golden output and zero writes.
- T-E2E-2 Live manual run (`make compass-run`) under 150 s; log shows per-phase timings.

## Tasks

0. **Freeze and commit baseline.** Commit current direct-reflect work and the `run_hermes_raw` `skip_memory` fix. This suppresses memory injection but does not establish zero-write safety; keep cron paused until the stateless cutover and live validation pass.
1. **Test harness.** Add dev deps; move fixtures (boundary outputs, platform payload, reflect responses) to `scripts/fixtures/`; write T-CON-1, T-RANK-*, T-REN-1 against the current output to lock behavior.
   - Done: `scripts/test_compass_harness.py` + `scripts/fixtures/`; `requires-python >=3.11` (cron venv); `live` marker skipped by default (`uv run pytest -m live`). Strict xfails pin the confirmed defects: never-fed goals rank last (`hunger:neverd` → -1), rendered order comes from `SKILL.md` instead of platform `dimension_order`, and platform outage reports `shared_goals_empty`.
2. **Models.** `compass/models.py`: `AreaConfig`, `BoundaryPayload`, `Line`, `Evidence` (frozen), `AreaAdvice`, `SourceRef`, `CompassRun`. Replace custom YAML parser with `yaml.safe_load`. Green: T-CON-*.
   - Done: `compass/models.py` + `compass/config.py` (area YAML + SKILL.md frontmatter via `yaml.safe_load`); custom parsers deleted; `make compass-run`/`area-test` now use the Hermes venv python. `CompassRun` deferred until the cut-over needs it. `daily_compass_shared.py` stays stdlib/3.9-safe because area scripts import it; legacy `validate_boundary_payload` stays until task 3 moves `run_boundary_script` onto `BoundaryPayload`.
3. **Collect.** `compass/collect.py`: run boundary scripts (keep `ThreadPoolExecutor`, timeouts, env vars) and platform fetch. Green: T-FAIL-1, T-RANK-4.
4. **Rank.** `compass/rank.py` from platform `dimension_order`; delete `hunger:Nd` title parsing. Green: T-RANK-*.
5. **Memory.** `compass/memory.py` with `hindsight-client` `reflect(response_schema, tags, include_facts)`; bank/url/key from `~/.hermes/hindsight/config.json`. Green: T-MEM-1, T-LLM-3, T-FAIL-2.
6. **Advise.** `compass/advise.py` via `agent.auxiliary_client.call_llm` with JSON schema output and one validation retry; area prompts still read from each skill's `## Area signal`. Green: T-LLM-*, T-MEM-2, T-FAIL-3.
7. **Render.** Port `templates/daily-output.md` to Jinja2; delete `tpl_*`. Green: T-REN-*.
8. **Cut over.** Thin `daily-compass.py` CLI (`--dry-run`, `--verbose`, area filter); delete session registry, `run_hermes_*`, `daily-compass-session.json`, prose-stripping validators. Green: T-E2E-1, S8, S9.
9. **Live validation.** Run T-MEM-3 + T-E2E-2 manually 3 times across 2 days; compare output with the last legacy run; re-run the cleanup tag audit.
10. **Re-enable cron** after S1–S10 pass; watch the first 3 scheduled runs (bank-stats delta, delivery, duration). Update `SKILL.md` and `sg-area-craft` for any contract change.

Rollback: the legacy script stays in git history; re-enable by reverting the cut-over commit. Cron stays paused until task 10.