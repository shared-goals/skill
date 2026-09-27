☀️ *{{ weekday }}, {{ date }}*

{% if ranking_fallback %}
_⚠️ Shared Goals platform unavailable — default dimension order_
{% endif %}

{% if compass.signal %}
*{{ compass.signal }}*
{% endif %}

{% for dimension in dimensions %}
{{ dimension.emoji }} **{{ dimension.NAME }}**

{% for area in dimension.areas %}
[{{ area.name }}]{% if area.signal %} *{{ area.signal }}*{% endif %}

{% if area.lines %}

{% for line in area.lines %}
- {% if line.url %}[{{ line.title }}]({{ line.url }}){% else %}{{ line.title }}{% endif %}{% if line.body %}: {{ line.body }}{% endif %}{% if line.display_signal %} — {{ line.display_signal }}{% else %}{% if line.signal %} — *{{ line.signal }}*{% endif %}{% endif %}
{% endfor %}
{% else %}
- [GUARD] no lines returned for this area
{% endif %}

{% endfor %}
{% endfor %}

⚖️ PROPORTION OF THE DAY

[TBD] — будет рассчитано платформой на основе истории коммитов
