---
name: wtd-prd-webhook
description: Decide whether WTD push events require Shared Goals PRD updates.
triggers:
  - "wtd webhook"
  - "whattodo push"
  - "prd update decision"
---

# wtd-prd-webhook

Webhook-first decision skill for Shared Goals PRD upkeep.

This skill is designed for Hermes webhook routes that receive GitHub push
payloads from `bongiozzo/whattodo` and must decide whether PRD updates are
needed.

## Scope

- Input: GitHub `push` event payload
- Decision: update PRD or not
- Output: concise report text for Telegram
- No direct PRD writes in default mode

## Memory-assisted decision policy

Before finalizing the decision, run memory reasoning with Hindsight tools:

1. `recall` using tags `project:sg`, `mvp`, `wtd`, `prd`
2. `reflect` using the same tags and current webhook evidence

Use the script result as `decision_hint`, then confirm or override with the
memory-informed result.

If memory tools are unavailable, fall back to script decision and report that
fallback explicitly.

## Script boundary

Use `scripts/wtd-prd-webhook.py` as the deterministic event triage layer.

The script reads JSON from stdin and prints JSON to stdout with:

- `should_update_prd`
- `decision_hint`
- `decision`
- `reason`
- `commit_count`
- `commit_range`
- `changed_paths`
- `relevant_paths`
- `suggested_targets`
- `memory_tags`
- `memory_query`
- `reflect_query`
- `requires_memory_review`
- `report`

## Suggested webhook wiring

Use a webhook route that:

1. accepts only `push` events,
2. runs `wtd-prd-webhook.py` as route script,
3. loads this skill for agent-side reasoning if needed,
4. delivers the final report to Telegram home channel.

## Decision policy (v1)

- `UPDATE_PRD` when push includes changes in core content paths (`text/`, `mkdocs.yml`, root README).
- `NO_UPDATE` when push changes only generated outputs or unrelated files.
- Telegram report should state how to realize the decision in one short line: either "core content paths changed, update PRD" or "not PRD-scoped, defer".
- When updating, include the PRD targets from the script output.
- Keep the message short and evidence-based.
