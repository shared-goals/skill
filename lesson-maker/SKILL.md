---
name: lesson-maker
description: Build HTML lessons from a topic or analysis.
triggers:
  - "сделай урок по"
  - "создай урок"
  - "урок по теме"
  - "make a lesson about"
  - "create a lesson on"
---

# Lesson Maker

## When to use

Use when the user wants a reusable structured lesson with knowledge verification,
or explicitly asks to turn an existing analysis into a lesson. The input may be
an ordinary topic or a completed `comparative-analysis` from another skill.

## Input

- Topic name or completed analysis
- Optional: specific angle, examples, depth level
- Optional mode:
  - `standard` — explanatory lesson with practice
  - `comparative-analysis` — evidence-based comparison report as a lesson

If an upstream skill supplies a completed analysis, preserve it as the source
material and do not repeat its research, transcript retrieval, or memory calls.

## Output

One self-contained HTML file at:

```text
~/.hermes/projects/lessons/<slug>.html
```

Always send the completed file to the user. By default, deliver it through
Telegram. Use another channel or format only when the user explicitly asks.

## Mode selection

### Standard mode

Use the standard structure below for a topic that needs teaching from scratch.

### Comparative-analysis mode

Use this mode for a supplied analysis comparing a source item with a reference
corpus, framework, previous research, or another source item. Do not force the
content into a generic quiz lesson. Keep distinctions, evidence, uncertainty,
and open questions visible.

Required sections:

1. **Title and context**
   - source title, author/speaker when available, date, and URL;
   - a short synopsis of the supplied source — what it is about and what its
     key message is;
   - introduce the comparison reference only from the upstream analysis. Do not
     assume a specific corpus, website, or philosophical frame unless the
     upstream analysis supplied it;
   - frame the lesson as a reusable tool for understanding the comparison:
     where meanings meet, where they differ, what remains uncertain, and what
     questions deserve live discussion;
2. **Central question and thesis**
   - the question guiding the analysis;
   - a short, non-inflated thesis.
3. **Source digest**
   - main ideas;
   - short source quotations with timestamps or URLs when available;
   - timestamp ranges should be clickable when the source supports stable time
     links;
   - source quality and limitations.
4. **Corpus context**
   - relevant concepts;
   - exact reference quotations with stable hyperlinks or file/source labels
     when available;
   - semantic paraphrases clearly labelled as such.
5. **Comparison table**
   - section heading: use a non-commercial name — avoid "feature comparison"
     or "product matrix" connotations. Acceptable alternatives:
     «Созвучия и расхождения», «Смысловые параллели», «Общее и различное»,
     «Перекличка смыслов». Prefer «Созвучия и расхождения» as the default.
   - common ground;
   - different foundations or accents;
   - type of relation;
   - evidence/provenance.
6. **Strongest convergences**
7. **Differences and unresolved tensions**
8. **Questions for live discussion**
9. **Reflection practice**
   - open-ended prompts, not mandatory multiple-choice questions;
   - use quizzes only when they genuinely test understanding.
   - visual element: key concepts as a card grid — use a neutral heading
     without a hard-coded number (not «Четыре ключевых понятия»); prefer
     «Ключевые понятия».
10. **Sources and method notes**
  - source extraction method and quality;
  - reference/corpus provenance;
   - memory-derived synthesis;
   - whether visual analysis was performed.

Preserve the distinction between:

- a quotation and a paraphrase;
- source claim and assistant interpretation;
- shared experience and shared explanation;
- shared direction and conceptual identity;
- a suggestion and a command;
- human will and automated assistance.

## Standard lesson structure

Every standard lesson follows this template:

### 1. Заголовок + контекст
- Badge с уровнем (Начинающий / Средний / Продвинутый)
- Название темы
- Подзаголовок: зачем это нужно

### 2. Суть (3-5 абзацев)
- Что это такое простыми словами
- Почему важно
- Аналогия или метафора для запоминания

### 3. Ключевые понятия (карточки)
- Термин + определение на карточке
- Минимум 4, максимум 8 карточек
- Клик по карточке раскрывает пример

### 4. Как это работает (пошагово)
- Нумерованные шаги
- Каждый шаг — блок с иконкой, заголовком и пояснением
- Визуальная схема (ASCII или CSS-based flowchart)

### 5. Примеры из практики
- Реальные кейсы, не абстрактные
- Код/запросы/данные — если применимо
- До/после или проблема/решение

### 6. Практика (3-5 заданий)
- Кликабельные варианты ответа
- Мгновенная подсветка правильного/неправильного
- Кнопка «Показать объяснение»
- Разная сложность: от простого к сложному

### 7. Памятка (шпаргалка)
- Компактный cheat sheet
- Ключевые команды/формулы/паттерны
- Готовая к копированию

## Design System

### Colors (dark theme)
```css
--bg: #0f0f1a;
--surface: #1a1a2e;
--surface2: #252540;
--border: #333355;
--accent: #7c3aed;
--accent2: #06b6d4;
--gold: #f59e0b;
--danger: #ef4444;
--success: #10b981;
--text: #e2e8f0;
--muted: #64748b;
```

### Typography
- Headings: `'Inter', sans-serif` (700)
- Body: `'Inter', sans-serif` (400)
- Code: `'JetBrains Mono', monospace`
- Use `clamp` for responsive sizing.

### Layout
- max-width: 860px, centered
- padding: 24px on mobile, 40px on desktop
- cards: 2 columns → 1 on mobile
- exercises: one column

### Interactive behavior

For standard lessons:
- exercises use click → highlight, and lock after answering;
- concept cards reveal examples on click;
- the cheat sheet remains visible.

For comparative-analysis lessons:
- comparison rows may be expandable;
- source quotations may be collapsible;
- timestamps and source references remain visible;
- reflection prompts are open by default;
- do not add interaction merely for decoration.

## Workflow

### Standard mode

1. Get the topic.
2. Gather information using appropriate tools and skills.
3. Determine structure, concepts, examples, and exercises.
4. Write content.
5. Generate self-contained HTML.
6. Save to `~/.hermes/projects/lessons/<slug>.html`.
7. Send the completed file to the user.

### Comparative-analysis mode

1. Receive the completed upstream analysis.
2. Check that provenance and limitations are present.
3. Select the comparative-analysis structure.
4. Preserve quotations, timestamps, references, and uncertainty.
5. Add reflective exercises only where useful.
6. Generate self-contained HTML.
7. Save to `~/.hermes/projects/lessons/<slug>.html`.
8. Send the completed file to the user.

Do not silently redo upstream research or replace the upstream comparison with
a generic summary.

## Pitfalls

- Do not overload the lesson with theory; in standard mode balance explanation
  and practice approximately 60/40.
- Exercises must test understanding, not memorization.
- Analogies must be accurate, not merely attractive.
- Comparative analysis must not flatten genuine differences into agreement.
- Never turn a Hindsight paraphrase into an exact quotation.
- HTML must be self-contained except for optional external fonts.
- Dark theme is mandatory.
- Send the generated file; do not merely describe where it was saved.
- Do not commit or publish generated lessons unless explicitly requested.
- When refactoring: update the skill first, THEN regenerate the HTML by
  following the updated skill. Never hand-patch the HTML alongside skill
  changes — the skill is the single source of truth and the HTML must be
  regenerated from it.
