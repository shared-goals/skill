# Shared Goals — AI Companion Skills

This repository contains a small public skill set for Hermes Agent.
It is designed to keep reusable logic in git and keep personal data local.

## Shared Goals Platform

Shared Goals is an open platform for social architects: people who commit time
to shared purposes and multiply joy and Social Capital worldwide.

This repository includes skills that let an AI companion operate within that
platform model: define goals, contracts, commits, and daily direction.

The product philosophy, including no comparison pressure and no leaderboards,
is described in the [Shared Goals PRD](https://github.com/shared-goals/prd).

## What this skill will do

An AI companion (Hermes Agent) uses this skill to interact with the platform on behalf of the user:

- Join a shared Goal
- Set a personal Contract (time commitment)
- Log a Commit (progress report)

## What this skill does now

- Run a **Daily Compass** — a daily projection of active contracts across life dimensions
- Consume the platform `GET /api/v1/compass/next-steps` feed when configured,
  then merge those joined-contract next steps into the Daily Compass runtime

Daily Compass is the seed of something larger: a companion that asks each morning *"What do my contracts say about today?"* and helps the user feel the right proportion of time across dimensions of balanced life.

## Skills In This Repo

1. `shared-goals`
	- Shared Goals platform model and schema skill.
	- Owns entities, dimensions, area-file format, and API contract notes.
2. `sg-area-craft`
	- Area engineer skill for creating or modifying Daily Compass area skills.
	- Enforces deterministic, test-first workflows.

## Local-Only Area Skills

Personal area skills are intentionally outside this repo in:

`~/.hermes/skills/shared-goals/areas/`

They are referenced by pattern, not committed here.
This prevents accidental publication of private context such as paths, hostnames, or personal mappings.

### Current local area set

Current local areas cover 11 domains:

- calendar and scheduling
- finance and accounting
- health and wellbeing
- mail triage
- music discovery
- news monitoring
- photo and memory prompts
- Shared Goals PRD tracking
- Personal Assistant developing
- household/property management
- weather

## Four Dimensions

Every Commit carries a `dimension_tag`:

| Tag | Meaning |
|-----|---------|
| `faith` | Acting in uncertainty toward a meaningful path |
| `will` | Obligations, contracts, routine |
| `feeling` | Creativity, hobbies, subjective experience |
| `mind` | Analysis, knowledge, cognitive work |

Hunger-first principle: the dimension least fed recently gets attention first.

## Daily Compass

Daily Compass uses area status payloads to project the day across dimensions.
The long-term target is SG platform-backed calculation.
Until then, local skills can emit placeholders such as `[TBD]`.

## Area Skill Pattern

An area skill typically has:

1. `SKILL.md` with area instructions and `## Area signal`
2. `scripts/daily-<area>-status.py` boundary script that emits strict JSON
3. optional local config in `references/` files (gitignored)

## Personal Configuration Safety

Any personal area mapping/configuration belongs in `references/` files under local skills.
These files must stay out of git.

Example schema:

```yaml
name: Example Area
dimensions: [faith, will]
skill: example-area
status: active
notes: ""
```

## Related

- [Shared Goals PRD](https://github.com/shared-goals/prd)
- [Hermes Agent](https://hermes-agent.nousresearch.com)
