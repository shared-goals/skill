# Shared Goals — AI Companion Skill

This skill is the AI companion interface to the [Shared Goals platform](https://github.com/shared-goals/prd).

Shared Goals is an open platform for social architects — people who commit time to shared purposes and multiply joy and Social Capital worldwide.

The platform design philosophy — why no comparison, no leaderboards, no pressure —
is explained in the [Shared Goals PRD](https://github.com/shared-goals/prd).

## What this skill does

An AI companion (Hermes Agent) uses this skill to interact with the platform on behalf of the user:
- Join a shared Goal
- Set a personal Contract (time commitment)
- Log a Commit (progress report)
- Run a **Morning Check-in** — a daily projection of active contracts across life dimensions

Morning Check-in is the seed of something larger: a companion that asks each morning *"What do my contracts say about today?"* and helps the user feel the right proportion of time across dimensions of life.

## Four Dimensions

Every Commit carries a `skill_tag` — one of four psychological dimensions:

| Tag | Meaning |
|-----|---------|
| 🙏 **faith** | Acting in uncertainty. Building because you believe in the path, not because you know the result. |
| ⚡ **will** | Obligations, contracts, routine. Exercising the commitment muscle. |
| ❤️ **feeling** | Creativity, hobbies, subjective experience. |
| 🧠 **mind** | Analysis, knowledge, cognitive work. |

**Hunger-first principle:** the dimension least fed recently gets attention first. The platform will calculate this automatically. Until then — you know yourself.

## Morning Check-in

Each morning the companion reads your active contracts and personal areas, then delivers a projection of the day across your four dimensions.

The **proportion of time recommendation** is an artifact of the SG platform — it will be calculated from your contract history, happy moment data, and dimension hunger. Until then: `[SG mockup]`.

See `SKILL.md` for implementation details and personal area configuration schema.

## Personal Configuration

Areas (your life domains mapped to dimensions) live in `references/` — **gitignored, never shared**. The schema is defined in `SKILL.md`. Fill it locally. The platform will eventually replace these files with live contract data.

## Related

- [Shared Goals PRD](https://github.com/shared-goals/prd) — product requirements and philosophy
- [Hermes Agent](https://hermes-agent.nousresearch.com) — the AI companion platform
