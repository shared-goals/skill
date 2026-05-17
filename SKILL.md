---
name: shared-goals
description: >
  Shared Goals platform skill for AI agents. Use when a user wants to
  join a shared goal, set a personal contract, log a commit, check
  status of active goals, or run a Morning Check-in across life dimensions.
---

# Shared Goals

Shared Goals is an open platform for joining shared purposes, committing time,
and tracking progress together with others.

⛔ PITFALL: Never mention concrete skill names, area names, personal mappings,
or user-specific data in this file or any tracked file. All personal
configuration lives exclusively in references/ which is gitignored.

## Core Entities

- **Goal** — a shared purpose people join (public, invite-only, or personal)
- **Contract** — your personal time commitment to a goal (e.g. "1 hour/week")
- **Commit** — a logged unit of progress against your contract
- **Instruction** — expert-authored action plan for a goal

## Four Dimensions

Every Commit carries a `skill_tag`:

| Tag | Meaning |
|-----|---------|
| `faith` | Acting in uncertainty toward a meaningful path |
| `will` | Obligations, contracts, routine |
| `feeling` | Creativity, hobbies, subjective experience |
| `mind` | Analysis, knowledge, cognitive work |

**Hunger-first:** show dimensions in order from least-fed to most-fed.
Order is personal — configured in `references/`. Platform will calculate automatically post-MVP.

## Key Workflows

See [Shared Goals PRD](https://github.com/shared-goals/prd) for full workflow details.

### Quick reference
- **Join a Goal** → find → review → set Contract → confirm
- **Log a Commit** → identify Contract → record time + done + next_step → tag `skill_tag` → flag `is_happy_moment`
- **Check Status** → list contracts → show Social Capital

## Morning Check-in

Morning Check-in is the daily companion projection: *"What do my contracts say about today?"*

**Algorithm:**
1. Read personal areas from `references/*.yaml` (or SG platform API when available)
2. For each area: get status via its skill or return `[not yet]`
3. Group areas by dimension, order by hunger-first
4. Append proportion recommendation `[SG mockup]`
5. Deliver via template from `templates/daily-output.md`

**Area status values:**
- `enabled` — skill exists, fetch live status
- `not_yet` — output `[not yet]`
- `mockup` — output `[SG mockup]` with placeholder data

## Personal Areas Schema

Each file in `references/` defines one area. Filename = area identity.

```yaml
# references/example-area.yaml
name: Example Area               # human-readable name
dimensions: [faith, will]        # one or more: faith | will | feeling | mind
skill: skill-name                # hermes skill to call for status, or null
status: enabled                  # enabled | not_yet | mockup
notes: ""                        # optional personal notes
```

Files in `references/` are gitignored. Never commit them. Never reference
specific area names or skill names in this SKILL.md.

## API Reference (mockup)

These calls represent the future SG platform API. Currently return placeholder data.

```python
# [SG mockup] — not yet implemented
sg.contracts.list(user_id)            # → active contracts with dimension tags
sg.dimensions.hunger(user_id)         # → ordered list: least-fed dimension first
sg.checkin.morning(user_id)           # → daily projection across contracts
sg.commits.happy_moment_rate(user_id) # → joy index per dimension
```

> Platform API will replace mockup calls as the platform develops.
> Personal area files in references/ will be replaced by live contract data.
