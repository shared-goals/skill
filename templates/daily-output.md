# Morning Check-in — Output Template

Delivery: Telegram, 08:00 UTC+4
One message per run.

---

☀️ *{weekday}, {date}*

{foreach dimension in hunger_order}
{dimension.emoji} {dimension.NAME}
{foreach area in dimension.areas}
  [{area.name}] {area.status_line}
{/foreach}

{/foreach}
⚖️ PROPORTION OF THE DAY
[SG mockup] — будет рассчитано платформой на основе истории коммитов

---
