---
name: sg-area-craft
description: >
  Shared Goals area engineer for diagnose, enhancement, and creation workflows.
  Works from Hermes TUI and Makefile wrapper with strict area-test compliance.
---

# sg-area-craft

Shared Goals area engineer for deterministic, test-first editing.

This skill is for three jobs:
1. Diagnose failing area compatibility checks.
2. Enhance an existing area safely.
3. Craft a new area and verify it end-to-end.

Use this skill when working on Daily Compass areas under `.hermes/skills/areas`.

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

- Area reference YAML: `.hermes/skills/shared-goals/shared-goals/references/<area>.yaml`
- Area skill: `.hermes/skills/areas/<skill-name>/SKILL.md`
- Boundary script: `.hermes/skills/areas/<skill-name>/scripts/daily-<area>-status.py`
- Validator: `.hermes/skills/shared-goals/shared-goals/scripts/area-test.py`
- Runtime preview: `.hermes/skills/shared-goals/shared-goals/scripts/daily-compass.py`

Do not edit mirror paths in `~/my-hermes/my-skills` as primary source.

## Non-negotiable contract

`make area-test <area>` must pass.

Execution priority:
1. Pass `make area-test <area>`.
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
2. Run `make area-test <area>` once to get baseline.
3. Choose Mode A, B, or C from actual state (existing/failing/new).

### Mode A: Diagnose existing area

Use when user says "fix make area-test <area>" or shares failing output.

Steps:
1. Run `make area-test <area>`.
2. Read failing check names and details.
3. Map each failure to file-level fixes using the failure map below.
4. Apply minimal edits only.
5. Re-run `make area-test <area>` until all checks pass.
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
5. Run `make area-test <area>`.
6. Run `make compass-fast-run <area>`.

Enhancement scope rule:
- If direction is tone/style only, edit only `## Area signal`.
- If direction mentions schema/validation/boundary, edit script and/or YAML as needed.

### Mode C: Craft new area

Use when area does not exist yet.

Steps:
1. Create reference YAML at `.hermes/skills/shared-goals/shared-goals/references/<area>.yaml`.
2. Create skill directory `.hermes/skills/areas/<skill-name>/`.
3. Add SKILL.md with frontmatter `name` matching YAML `skill`.
4. Add boundary script at `scripts/daily-<area>-status.py`.
5. Ensure boundary script prints exactly one JSON object.
6. Ensure `## Area signal` is enumerated and scope-explicit.
7. Run `make area-test <area>`.
8. Run `make compass-fast-run <area>`.

Creation minimum:
- New area is not complete until both commands succeed.

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
  - Add/fix required top-level keys and string field types.
  - Ensure `status` is `ok|TBD|error`.

- `boundary_key_match`, `boundary_name_match`, `boundary_dimension_match` fail:
  - Align boundary output with YAML key/name/dimension.

- `boundary_line_context_schema` fail:
  - Ensure every line has string `title`, `url`, `body`, `signal`.

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
make area-test <area>
make compass-fast-run <area>
```

If tests fail, fix only the reported contract violations and re-run.

## LLM execution script

Use this exact command sequence:

```bash
make area-test <area>
# if fail: edit only files implied by failing checks
make area-test <area>
# repeat until pass
make compass-fast-run <area>
```

Allowed edit targets:
- `.hermes/skills/shared-goals/shared-goals/references/<area>.yaml`
- `.hermes/skills/areas/<skill-name>/SKILL.md`
- `.hermes/skills/areas/<skill-name>/scripts/daily-<area>-status.py`

Disallowed behavior:
- Do not invent extra files or compatibility wrappers.
- Do not edit unrelated areas.
- Do not stop after analysis without re-running `make area-test <area>`.

## Required report format

When done, output exactly these sections:
1. `Detected mode`: A/B/C.
2. `Files changed`: list of touched files.
3. `Checks fixed`: failing check names that became PASS.
4. `Validation`: final output summary of `make area-test <area>` and `make compass-fast-run <area>`.
5. `Residual risk`: one line, or `none`.

## Guardrails

1. Prefer smallest edit set that makes checks pass.
2. Never add compatibility shims for old formats.
3. Keep boundary scripts deterministic, compact, and data-focused.
4. Keep guidance concrete and operational, not philosophical.
5. Do not skip validation.

## Stop conditions

- Missing `area`: stop and request `area`.
- Missing `direction`: stop and request `direction`.
- Conflicting instructions: ask one short clarification question.

## Examples

```bash
make area-craft weather "fix make area-test weather"
make area-craft news "remove line signal section and normalize area signal steps"
make area-craft homelab "craft new area contract and pass area-test"
```
