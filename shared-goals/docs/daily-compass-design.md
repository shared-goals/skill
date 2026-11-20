# Daily Compass design

Daily Compass answers one question each morning: *what do my areas say about
today?* This note records the invariants the implementation keeps, so a change
can be judged against them instead of against a past task list.

## Pipeline

```text
cron -> typed evidence collection -> scoped recall -> stateless synthesis
     -> recommendations -> deterministic hunger ranking -> render -> deliver
```

## Invariants

**Evidence is immutable.** Boundary scripts produce a `BoundaryPayload`
(`compass/models.py`); the collected `Evidence` is frozen. A model may add
recommendation text and source references, never change a title, URL, body, or
dimension.

**Memory is read-only.** `compass/memory.py` exposes `recall` and nothing else:
no `retain`, no `reflect`, no mental-model writes. Generated recommendations are
not facts, so they must never reach memory.

**Model calls are stateless.** `compass/llm.py` talks to the configured provider
over plain chat completions. No chat session and no memory provider is opened, so
a run cannot write memory as a side effect. The Hermes CLI is used only to send
the finished messages (`compass/deliver.py`).

**The platform owns hunger.** `compass/rank.py` takes `dimension_order` from the
platform. Never-fed dimensions come first and ties keep platform order. The
order in `SKILL.md` is a fallback, and output is flagged when it is used.

**One failure degrades one area.** A boundary timeout, an invalid payload, a
recall error, or a dead provider leaves the other areas intact and still renders
a run. Silence is not an acceptable outcome.

**Delivery is counted.** `compass/deliver.py` sends every area message; an
oversized body is clamped, not dropped, and a failed send never blocks the rest.
The final status message reports what went wrong.

## Modules

| File | Owns |
|---|---|
| `compass/models.py` | Typed area config, boundary payload, evidence, recommendations |
| `compass/config.py` | Area YAML and skill index loading |
| `compass/collect.py` | Parallel boundary runs and platform fetch |
| `compass/memory.py` | Scoped read-only recall |
| `compass/llm.py` | Stateless completions and retries |
| `compass/rank.py` | Deterministic hunger order |
| `compass/deliver.py` | Telegram delivery via the Hermes CLI |
| `daily-compass.py` | Thin CLI: collect, advise, rank, render, deliver |
| `daily_compass_shared.py` | Stdlib-only helpers imported by area scripts |

Area scripts and their contract are described in the `sg-area-craft` skill.

## Tests

```bash
uv run --project shared-goals/scripts python -m pytest -q           # unit + contract
uv run --project shared-goals/scripts python -m pytest -q --live    # needs local config
```

A run that writes to memory, mutates evidence, invents a hunger order, or loses
an area message is a regression, not a preference.
