---
name: sg-area-craft
description: Use when editing Daily Compass areas. Test-first contracts.
version: 1.1
author: shag
license: MIT
metadata:
  hermes:
    tags: [shared-goals, daily-compass, areas]
    related_skills: [shared-goals]
---

# sg-area-craft

Shared Goals area engineer for deterministic, test-first editing.

This skill is for three jobs:
1. Diagnose failing area compatibility checks.
2. Enhance an existing area safely.
3. Craft a new area and verify it end-to-end.

Use this skill when working on Daily Compass areas under `areas`.

## Entry points

This skill can be invoked from Hermes TUI or from Makefile.

Hermes TUI style:

```text
area: <area>
direction: <what to change>
```

Makefile wrapper:

```bash
make area-craft <area> <direction>
```

Wrapper behavior (current architecture):

```bash
hermes -s sg-area-craft -z "area: <area> direction: <direction>"
```

Input contract:
- `area` is required.
- `direction` is required.
- If either is missing, stop and return usage.

## Architecture map (source of truth)

Paths below are relative to the root of the `shared-goals/skill` checkout.

- Area reference YAML: `shared-goals/references/<area>.yaml`
- Area skill: `areas/<skill-name>/SKILL.md`
- Boundary script: `areas/<skill-name>/scripts/daily-<area>-status.py`
- Validator: `shared-goals/scripts/area-test.py`
- Boundary conformance suite: `shared-goals/scripts/test_boundary_conformance.py`
- Runtime preview: `shared-goals/scripts/daily-compass.py`

Edit the checkout, not a separately installed copy.

## Non-negotiable contract

From the repository root, validate the public contract with the locked project dependencies:

```bash
(cd shared-goals/scripts && uv run --locked python -m pytest test_boundary_conformance.py -q)
```

The default tests use synthetic areas. To check a real area, add `--boundary-script /path/to/daily-example-status.py` to the same command. Review that script first: it runs more than once and can access configured services. The separate `--live` flag enables tests marked `live`. If your installation supplies the `make area-test` and `make compass-fast-run` wrappers used below, run them from the directory owning that Makefile.

Execution priority:
1. Pass `make area-test AREA=<area>`.
2. Keep edits minimal and local.
3. Run `make compass-fast-run <area>` for behavior preview.

Validator-sensitive rules:
1. `## Area signal` section must exist.
2. Area guidance must be enumerated sequentially (`1.`, `2.`, ...).
3. Each enumerated step should start with an allowed action verb.
4. Guidance must explicitly reference `AreaContext `signal`` and `LineContext `signal``.
5. Do not include `## Line signal` section.
6. Boundary payload must be strict and script-executable.

Boundary payload shape (operational):
- Top-level: `key`, `name`, `dimension`, `status`, `reason`, `signal`, `lines`.
- `status` is one of `ok`, `TBD`, `error`.
- `lines` is a list of objects with string fields: `title`, `url`, `body`, `signal`.

## Operating modes

Before choosing mode, do this:
1. Resolve `<area>` from input.
2. Run `make area-test AREA=<area>` once to get baseline.
3. Choose Mode A, B, or C from actual state (existing/failing/new).

### Mode A: Diagnose existing area

Use when user says "fix make area-test AREA=<area>" or shares failing output.

Steps:
1. Run `make area-test AREA=<area>`.
2. Read failing check names and details.
3. Map each failure to file-level fixes using the failure map below.
4. Apply minimal edits only.
5. Re-run `make area-test AREA=<area>` until all checks pass.
6. Run `make compass-fast-run <area>` to preview runtime output.

Loop rule:
- Fix only checks that are currently failing.
- Do not rewrite unrelated sections.

### Mode B: Enhance existing area

Use when area already exists and user asks for behavior/tone/schema change.

Steps:
1. Locate YAML, SKILL.md, and boundary script for the area.
2. Decide if change is guidance-only or boundary-data change.
3. For guidance changes, edit only `## Area signal` with strict numbered steps.
4. For data changes, keep boundary script deterministic and JSON-only.
5. Run `make area-test AREA=<area>`.
6. Run `make compass-fast-run <area>`.

Enhancement scope rule:
- If direction is tone/style only, edit only `## Area signal`.
- If direction mentions schema/validation/boundary, edit script and/or YAML as needed.

### Mode C: Craft new area

Use when area does not exist yet.

Steps:
1. Create reference YAML at `shared-goals/references/<area>.yaml`.
2. Create skill directory `areas/<skill-name>/`.
3. Add SKILL.md with frontmatter `name` matching YAML `skill`.
4. Add boundary script at `scripts/daily-<area>-status.py`.
5. Ensure boundary script prints exactly one JSON object.
6. Ensure `## Area signal` is enumerated and scope-explicit.
7. Run `make area-test AREA=<area>`.
8. Run `make compass-fast-run <area>`.

Creation minimum:
- New area is not complete until both commands succeed AND the boundary
  conformance suite passes (see Non-negotiable contract).
- Not-yet-implemented areas get a stub boundary script: payload
  `status="TBD"`, `reason="not_implemented"`, one line with
  `body="Not implemented yet"`. It keeps the area visible in the compass as a
  reminder and passes the conformance suite from day one.

## Failure-to-fix map

Use this map directly from area-test output.

- `yaml_exists` fail:
  - Create missing reference YAML in `shared-goals/references`.

- `yaml_name`, `yaml_dimensions`, `yaml_dimensions_valid`, `yaml_status`, `yaml_skill` fail:
  - Fix YAML fields and allowed values.

- `skill_found` fail:
  - Ensure skill frontmatter `name` exactly matches YAML `skill`.

- `boundary_exists` fail:
  - Add `scripts/daily-<area>-status.py` in area skill.

- `boundary_exec` fail:
  - Ensure script exits 0 and prints valid JSON object.

- `boundary_area_context_validated` fail:
  - Add/fix required top-level keys and string field types; no extra keys (only `status`, `reason`, `lines`, optional `signal`/`ts`).
  - Ensure `status` is `ok|TBD|error` and every line has a non-blank `title`.

- `boundary_key_match`, `boundary_name_match`, `boundary_dimension_match` fail:
  - Align boundary output with YAML key/name/dimension.

- `boundary_line_context_schema` fail:
  - Ensure every line has string `title`, `url`, `body`, `signal`.

- `boundary_line_signals_empty` fail:
  - Boundary scripts must emit `signal=""` on every LineContext. The LLM signal step fills signals, never the script. If `hermes -z` or any internal call returns a `signal` field, discard it and use empty string.

- `area_signal_guidance_enumerated` fail:
  - Rewrite `## Area signal` into sequential `1..N` lines.

- `area_signal_directive_verbs` fail:
  - Start each step with action verbs like `Analyze`, `Add`, `Delete`, `Set`, `Keep`, `Update`.

- `area_signal_scope_addresses` fail:
  - Add explicit text for `AreaContext `signal`` and `LineContext `signal``.

- `line_signal_section_removed` fail:
  - Remove `## Line signal` section completely.

- `area_signal_guidance_no_duplication` fail:
  - Remove generic JSON-contract prose from area guidance; keep area-specific instructions only.

## Area signal template (safe default)

Use this when guidance needs reset:

```markdown
## Area signal

1. Analyze all lines and identify the most relevant facts for this area.
2. Add one concise phrase to AreaContext `signal` describing today's practical direction.
3. Add short line-level notes to LineContext `signal` for only the most actionable lines, and keep non-actionable lines empty.
```

## Boundary script template (safe default)

Import the semantic timeout constant for the request type from `daily_compass_shared`. Never hardcode seconds.

```python
payload = {
    "key": "<area>",
    "name": "<Area Name>",
    "dimension": "<faith|will|feeling|mind>",
    "status": "ok",
    "reason": "",
    "signal": "",
    "lines": [
        {
            "title": "...",
            "url": "",
            "body": "",
            "signal": "",
        }
    ],
}
```

## Validation protocol (always)

Run in this order after every edit:

```bash
make area-test AREA=<area>
make compass-fast-run <area>
```

If tests fail, fix only the reported contract violations and re-run.

## LLM execution script

Use this exact command sequence:

```bash
make area-test AREA=<area>
# if fail: edit only files implied by failing checks
make area-test AREA=<area>
# repeat until pass
make compass-fast-run <area>
```

Allowed edit targets:
- `shared-goals/references/<area>.yaml`
- `areas/<skill-name>/SKILL.md`
- `areas/<skill-name>/scripts/daily-<area>-status.py`

Disallowed behavior:
- Do not invent extra files or compatibility wrappers.
- Do not edit unrelated areas.
- Do not stop after analysis without re-running `make area-test AREA=<area>`.

## Required report format

When done, output exactly these sections:
1. `Detected mode`: A/B/C.
2. `Files changed`: list of touched files.
3. `Checks fixed`: failing check names that became PASS.
4. `Validation`: final output summary of `make area-test AREA=<area>` and `make compass-fast-run <area>`.
5. `Residual risk`: one line, or `none`.

## Debugging technique: PATH shim for secret shell-outs

When an interactive prompt (password, passphrase) appears mid-pipeline but no
obvious script issues that command, wrap the suspect binary with a logging
shim early in PATH — record argv, exit non-zero — and rerun. The shim's log
identifies the caller without grep-guessing across skills. Applies to any
child process that only misbehaves with a TTY (under `</dev/null` it fails
fast and graceful degradation hides it, which is exactly why tests pass while
interactive runs prompt).

## Boundary script error output

When a boundary script cannot fetch data (IMAP timeout, missing credentials, API error), put the **raw error message** in LineContext `body`. Do not wrap it in "Error is Ok: ..." or similar softening — the LLM signal step and the user need to see what actually failed.

## LLM calls from Daily Compass

Compass model calls are stateless chat completions in `compass/llm.py` against the
configured provider; they open no Hermes session and no memory provider, so a run
cannot write memory as a side effect. Only `model` and `provider` are resolved
(`resolve_model()` in `daily-compass.py`) and carried on `CompassCallState`.

- Use `BOUNDARY_SCRIPT_TIMEOUT_SECONDS` for boundary processes.
- Use `HERMES_SIGNAL_TIMEOUT_SECONDS` for ordinary area and compass synthesis.
- Parse the response for JSON via `parse_json_object` when the call contract requires JSON.
- On timeout or error, return a LineContext with the raw error message in `body` and empty `signal`.
- **Never build a client, argv, or provider lookup in an area.** Provider resolution
  lives in `compass/llm.py`; a second reader of the config schema breaks on the next
  Hermes migration while the first one keeps working.
- Memory access is recall-only (`compass/memory.py`); a recommendation is not a fact
  and must never be retained.
- Delivery is the one place a Hermes CLI subprocess is legitimate (`compass/deliver.py`
  calls `hermes send`). Do not conclude "no Hermes subprocess anywhere" from the
  stateless model path — check both.

## Guardrails

1. Prefer smallest edit set that makes checks pass.
2. Never add compatibility shims for old formats.
3. Keep boundary scripts deterministic, compact, and data-focused.
4. Keep guidance concrete and operational, not philosophical.
5. Do not skip validation.
6. Use semantic timeout constants from `daily_compass_shared` — never hardcode timeout values in area scripts, daily-compass, or area-test.

## Pitfall: `status: debug` in area YAML fails area-test

AGENTS.md mentions `status: debug` as a debug-mode convention, but `area-test.py` only accepts `active` or `TBD` for the `yaml_status` check. Use `status: TBD` for areas under development — it passes the validator while signalling "not yet active". The debug-mode convention from AGENTS.md applies to which areas the Daily Compass runtime includes, not to the area-test validator.

## Pitfall: stdlib-only boundary scripts

Boundary scripts run in the Hermes venv where external packages may not be installed. Prefer stdlib modules (`urllib.request`, `imaplib`, `xml.etree.ElementTree`, `email`, `json`, `re`) over third-party libraries (`caldav`, `icalendar`, `requests`). This avoids `ModuleNotFoundError` crashes and keeps boundary scripts self-contained. If a protocol requires complex parsing (e.g. iCal, MIME), regex + stdlib parsing is usually sufficient for a read-only daily status fetch.

## Pitfall: `hermes -z` in boundary scripts

When a boundary script calls `hermes -z` (e.g. for hindsight recall or SOUL reflection):

- **Semantic timeout constants.** `daily_compass_shared.py` is the single source of truth for boundary, signal, reflection, and session-command timeouts.
- **Outer timeout ordering.** A wrapper timeout must exceed any inner client timeout so the wrapper can report the real operation failure instead of killing it first.
- **Signals must be empty.** Boundary scripts must always emit `signal=""` on every LineContext. The LLM signal step (Area signal guidance) fills signals — never the script. If `hermes -z` returns a `signal` field, discard it.
- **Graceful degradation is mandatory.** On timeout or error, return a valid LineContext with `body` set to the raw error message (not wrapped in "Error is Ok") and empty `signal`. The script must always exit 0 with valid JSON.
- **Parse JSON from stdout.** `hermes -z` output may contain prose around the JSON. Use `parse_json_object()` from `daily_compass_shared` to extract the JSON payload.
- **Cost and latency.** Each `hermes -z` call starts a full Hermes session. In Daily Compass, boundary scripts run in parallel (max 4 workers), so multiple `hermes -z` calls can run concurrently.

## Pitfall: nested-uv env leak breaks make subprocesses

`uv run` exports `UV=<path-to-uv-binary>` into the child environment. A nested `make`
target with a `UV ?=` default then expands to the bare uv binary, turning
`uv run <cli> args` into `uv <cli> args` and failing with an unrecognized-subcommand
error — while the same command works from a plain shell, which hides the cause.
When a boundary script shells out to `make`/another build tool, strip inherited make
override variables (`UV`) from the child env before `subprocess.run(..., env=...)`.

## Pitfall: never ssh to the local host from a boundary script

Shelling out via SSH to the same host can prompt for a
password when `authorized_keys` drifts from the current key — the run hangs
interactively or degrades to a cached/failed body. Run local commands with
`subprocess.run` directly; reserve ssh for genuinely remote hosts.

To find a hidden ssh caller when a run prompts for a password: put a logging
shim first on PATH (`#!/bin/bash` script that appends `"$@"` to a file and
exits 255), rerun the pipeline, and read the log — the offending argv names
its file. Boundary scripts may also call scripts from other skills
transitively (e.g. devops helpers); the conformance suite only discovers
`areas/*/scripts/daily-*-status.py`, so grep any transitive helper for
`"ssh"` and give it the same local-execution/BatchMode treatment.

## Pitfall: hermes-agent is a uv project, not a venv

Boundary scripts that need `hermes_cli` / `hermes_state` run under the compass
venv where those packages are absent, and `~/.hermes/hermes-agent/venv/` does
not exist. Resolve the interpreter as
`uv --directory ~/.hermes/hermes-agent run python` (`shutil.which("uv")`,
fallback glob `~/.hermes/tools/uv-*/uv`), pass the call as a single command
string split with `shlex.split`, and import inside the child script. A resolver
that checks for a `venv/bin/python` path silently returns None — the caller then
fails with a misleading "not available"/empty result. The single owner of this
resolution is `get_hermes_python()` / `run_hermes_python()` in
`daily_compass_shared.py` — use them, never re-implement the resolver.

## Keep local areas private

The public repository ignores `areas/`. Never force-add private area files here.

## Removing a provider/billing line from an area

A subscription that was turned off removes the line in THREE places, or a stale
error line keeps shipping: (1) the boundary script — fetch function, line builder,
and the call in `main()`; (2) the area SKILL.md — output format, `## Area signal`
steps, and frontmatter triggers; (3) any per-line signal guidance numbering must be
re-enumerated after deletion.

## Pitfall: public-repo hygiene in scripts and tests

The shared-goals skill repo is public on GitHub.
Never commit real internal hostnames (`*.lan`), LAN ports tied to them, private env-var
names, or home paths in test fixtures or fallback defaults — use neutral placeholders
(`tf.test`, `TEST_PROVIDER_KEY`, `http://localhost:8889`). Runtime values come from
env/config; a hardcoded internal default in committed code leaks topology. Before
committing, `grep -rn '<lan-host>\|<PRIVATE_ENV>' scripts/` including pre-existing lines.

## Pitfall: Daily Compass LLM calls bypass Hermes middleware

Compass signal calls are stateless `openai`-client chat completions built in
`compass/llm.py::open_client`, not Hermes sessions — Hermes `llm_request`
middleware plugins never see them. Do not install or configure a Hermes plugin
expecting it to affect Compass LLM traffic. Provider-specific request behavior belongs in the client that actually sends the request.

## Pitfall: Telegram delivery is slow by design — measure before 'fixing'

Delivery sends one `hermes send` per area message; the Telegram adapter serializes
per chat (~1 msg/s envelope, inline sleeps on flood-control `RetryAfter`), so a
12-message run finishing minutes after `render complete` is expected pacing,
not a bug. `SEND_INTERVAL_SECONDS` must stay at/above the per-chat flood
envelope (~3s) and `SEND_TIMEOUT_SECONDS` large enough for a residual flood
wait plus one send — otherwise the tail message ships as a timeout error.

## Pitfall: MCP clients in boundary scripts must match the configured transport

A boundary script with its own MCP client drifts from Hermes `mcp_servers` config
the same way config-key readers do: the client was written for one transport
(streamable-HTTP `url`) while the gateway later switched the server to another
(stdio `command`/`args`/`env`). Always read the transport keys from the config
entry, never hardcode the spawn target or expect a `url`.

## Pitfall: skill scripts reading Hermes config schema

Skill scripts (`compass/llm.py` and friends) read `~/.hermes/config.yaml` directly. After
a Hermes update migrates the config schema (key renames like `custom_providers` →
`providers`), every reader of the old key fails instantly with a lookup error — and
because callers catch exceptions, the failure can stay silent while degraded output
ships. After any Hermes update: grep scripts for `config.get(...)` keys and verify each
against the live schema; and a pipeline that produced zero LLM results must exit
non-zero (fail loud), never render raw boundary output as if it were a normal run.

Prevention beats the grep: keep ONE reader of `~/.hermes/config.yaml`
(`load_hermes_config()` in `daily_compass_shared.py`) and import it everywhere
(area boundary scripts included) — never hand-roll a second
`yaml.safe_load(config_path)` reader. Every scattered reader breaks at once on the
next schema migration; one reader is fixed in one place.

## Manual Compass runs

Use `uv run --project shared-goals/scripts python shared-goals/scripts/daily-compass.py` from the repository root. Omit `--send` for a preview. A SOCKS proxy requires the `httpx[socks]` dependency already declared in that project.

Grep hygiene for the success signature: a GREEN log may still contain the
string `[ERR:hermes_unavailable]` inside a line `body` — Hindsight
observation text echoes old incident notes into boundary output. Judge by
`Stateless auxiliary call failed` count (must be 0) and the surrounding
context of the grep hit, not the hit itself.

## Pitfall: Cron delivery truncates output at 4000 chars

Hermes cron auto-delivery has a hardcoded `MAX_PLATFORM_OUTPUT = 4000` in `gateway/delivery.py` that truncates output **before** it reaches Telegram's own 4096 limit. Full output is saved to `~/.hermes/cron/output/<job_id>_<timestamp>.txt`. The `send_message` tool has proper chunking (splits into multiple messages) but cron auto-delivery does not use it.

When compass output appears truncated in Telegram: check the log file first (`shared-goals/logs/<date>-<time>.log`) — if full content is there, the truncation is in cron delivery, not in the compass script.

## Refactoring the compass core (KISS/DRY/YAGNI/TDD)

When asked to explore or refactor `daily-compass.py`, `daily_compass_shared.py`,
or `compass/*`:

1. Read the target files whole first (`grep -n '^def \|^class '` for the map),
   then rank findings by principle (dead code / vestigial params / DRY / TDD
   gaps) and present options — the user decides the scope before edits.
2. Grep `del <param>` to find vestigial parameters — a `del x` first line in a
   function body marks a dead argument kept for an old call shape; after any
   architecture migration these are the cheapest, safest deletions.
3. Add tests for untested pure functions (date parsing with odd fractional
   digits, boundary-age splits, sort orders) BEFORE refactoring them — the
   edge cases are the regression traps.
4. Commit pending fixes before starting the refactor pass — never mix a bug
   fix and a refactor in one commit or one diff review.
5. Do not unify parallel validation layers without a trigger: the pydantic
   `compass.models` layer and the hand-rolled `is_valid_*`/`serialize_*` in
   `daily_compass_shared` express the same contract, but `area-test.py` and the
   conformance suite bind to the hand-rolled one — unification is churn until
   one of them actually fails.
6. A fallback branch that passes a failed dependency into the success path is
   dead code, not resilience: if the dependency is known-broken, the first call
   inside re-raises and the outer handler wins. Delete the branch instead of
   shipping an unreachable payload (and its off-contract `status` value).
7. Do not trust an automated dead-symbol scan. `from __future__ import
   annotations` turns annotation-only references into strings, so an AST scan that
   counts `Name` nodes reports live functions as dead; hand-written types and
   `getattr` dispatch hide others. Confirm each candidate by occurrence count over
   the tree (`grep -rho "\bNAME\b" scripts/ areas/ | wc -l`): a count equal to the
   number of definitions means no caller, anything higher means live. Deleting on
   a scanner's verdict removes working code.
8. After deleting a layer, grep for the symbols it owned and run a lint pass
   filtered to `F` (unused imports, unused locals). The residue of a deletion is
   not only the deleted code: it is the import, the fixture field, and the test
   local that existed only to feed it.

## Stop conditions

- Missing `area`: stop and request `area`.
- Missing `direction`: stop and request `direction`.
- Conflicting instructions: ask one short clarification question.

## Examples

```bash
make area-craft weather "fix make area-test AREA=weather"
make area-craft news "remove line signal section and normalize area signal steps"
make area-craft homelab "craft new area contract and pass area-test"
```
