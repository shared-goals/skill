---
name: shared-goals
description: >
  Shared Goals platform skill for AI agents. Use when a user wants to
  join a shared goal, set a personal contract, log a commit, check
  status of active goals, or manage personal life areas.
---

# Shared Goals

Shared Goals is an open platform for joining shared purposes, committing time,
and tracking progress together with others.

⛔ PITFALL: Never mention concrete skill names, area names, personal mappings,
or user-specific data in this file or any tracked file. All personal
configuration lives exclusively in references/ which is gitignored.

⛔ PITFALL (agent): the git repo lives at the category root:
`~/.hermes/skills/shared-goals/`.
Remote: git@github.com:shared-goals/skill.git
Work directly there — never clone to /tmp to edit.
To sync: cd ~/.hermes/skills/shared-goals && git pull / git push

## Local Skill Setup

This skill lives as a git repo tracked against `git@github.com:shared-goals/skill.git`:

```bash
# ~/.hermes/skills/shared-goals/ IS the git repo
cd ~/.hermes/skills/shared-goals
git status   # check sync
git push     # publish changes
```

`references/` is gitignored — personal area yaml files live there, never committed.
When adding files to SKILL.md schema, push to GitHub so the public skill stays current.

## Core Entities

- **Goal** — a shared purpose people join (public, invite-only, or personal)
- **Contract** — your personal time commitment to a goal (e.g. "1 hour/week")
- **Commit** — a logged unit of progress against your contract
- **Instruction** — expert-authored action plan for a goal

## Four Dimensions

Every Commit carries a `dimension_tag`:

| Tag | Meaning |
|-----|---------|
| `faith` | Acting in uncertainty toward a meaningful path |
| `will` | Obligations, contracts, routine |
| `feeling` | Creativity, hobbies, subjective experience |
| `mind` | Analysis, knowledge, cognitive work |

**Hunger-first:** show dimensions in order from least-fed to most-fed.
Order is personal — configured in `references/`. Platform will calculate automatically post-MVP.

## Dimensions order

faith, will, feeling, mind

## Key Workflows

See [Shared Goals PRD](https://github.com/shared-goals/prd) for full workflow details.

### Quick reference
- **Join a Goal** → find → review → set Contract → confirm
- **Log a Commit** → identify Contract → record time + done + next_step → tag `dimension_tag` → flag `is_happy_moment`
- **Check Status** → list contracts → show Social Capital

## Git Setup

This skill directory is the git repo:
```bash
cd ~/.hermes/skills/shared-goals
git remote -v  # → git@github.com:shared-goals/skill.git
```
`references/` is gitignored — never committed. Personal area yamls stay local only.

When publishing changes to SKILL.md:
```bash
git add SKILL.md
git commit -m "..."
git push
```

## API Reference (mockup)

These calls represent the future SG platform API. Currently return placeholder data.

```python
# [TBD] — not yet implemented
sg.contracts.list(user_id)            # → active contracts with dimension tags
sg.dimensions.hunger(user_id)         # → ordered list: least-fed dimension first
sg.checkin.daily(user_id)             # → daily projection across contracts
sg.commits.happy_moment_rate(user_id) # → joy index per dimension
```

> Platform API will replace mockup calls as the platform develops.
> Personal area files in references/ will be replaced by live contract data.

## Model vs Execution separation

This skill owns the **model** (what an area is). Execution logic (what to do with areas) lives in workflow skills like `sg-daily-compass`.

| What stays here | What moves to workflow skills |
|---|---|
| Area definitions (name, dimensions, skill, status, notes) | Prompts (what to ask each skill) |
| Entity schema (Goal, Contract, Commit) | Algorithm (how to run compass) |
| API mockup | Output template |
| Git setup, pitfalls (repo-specific) | Operational pitfalls (cron, fallback, etc.) |

## Daily Compass

The Daily Compass is the daily companion projection: *"What do my areas say about today?"*

It's implemented as daily-compass.py script in this skill.

## Area File Format

Each file in `references/` defines one area. Filename = area identity.
One file per area — DRY, no duplication across dimensions.

```yaml
# references/example-area.yaml
name: Example Area               # human-readable name
dimensions: [faith, will]        # one or more: faith | will | feeling | mind
skill: skill-name                # hermes skill to call for status, or null
status: active                   # active | TBD
notes: ""                        # human-readable description (for ls references/)
```

Files in `references/` are gitignored. Never commit them. Never reference
specific area names or skill names in this SKILL.md.

When SG platform API is ready, `references/*.yaml` files will be replaced by
live contract data from `sg.contracts.list(user_id)`.

## Compass signal

Write one short phrase about today's Shared Goals direction based on area summaries.
