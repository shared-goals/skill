☀️ *{weekday}, {date}*

{if compass.signal}
*{compass.signal}*
{/if}

{foreach dimension in dimensions}
{dimension.emoji} **{dimension.NAME}**

{foreach area in dimension.areas}
[{area.name}]{if area.signal} *{area.signal}*{/if}

{if area.lines}

{foreach line in area.lines}
- {if line.url}[{line.title}]({line.url}){else}{line.title}{/if}{if line.body}: {line.body}{/if}{if line.signal} — *{line.signal}*{/if}
{/foreach}
{else}
- [GUARD] no lines returned for this area
{/if}

{/foreach}
{/foreach}

⚖️ PROPORTION OF THE DAY

[TBD] — будет рассчитано платформой на основе истории коммитов
