---
name: html-briefing
description: Turn research findings into a polished, self-contained HTML briefing page (cover, key points, stats, timeline, map, comparison, charts, sources) that works offline. Use when the user asks for an HTML report, briefing, web page or explainer.
---

# HTML briefing

You write the content as JSON. `briefing.py` owns the design: fonts, colours, layout,
maps, icons and animation are built in and embedded. Never hand-write HTML or CSS.

## Steps

1. Gather the facts first (research, files, BIGDATA). Every fact keeps its source id.
2. Start from the example: `python3 briefing.py example --output work/brief.json`.
   It is illustrative only; replace every value with the task's own sourced content.
3. Plan the page as a story: cover → bluf → stats → chapters with mixed sections → sources.
4. Write `work/brief.json`, then render:
   `python3 briefing.py render work/brief.json --output output/<name>.html --theme <theme>`
5. Fix every `warnings` item the render reports, then render again.
6. If `check.py` and a browser are available: `python3 check.py output/<name>.html`.
   Fix anything it reports (overflow, empty section, blocked request, script error).

## Pick the section that matches the content

| Content you have | Section type |
|---|---|
| 2-4 sentences a busy reader must know | `bluf` (always first) |
| 2-4 headline numbers | `stats` |
| Dated events | `timeline` (status `planned`/`unconfirmed` when not confirmed) |
| Places or countries | `map` (`focus` countries, `markers` with lat/lon and a note) |
| 2-6 sides, actors or options | `compare` |
| Ranked or ordered points | `list` |
| Numbers to compare | `bars` |
| Explanation, background | `text` (optional `pullquote`) |
| A start of a new part | `chapter` |
| A judgement or warning | `callout` (`tone`: assessment, warning, note) |
| Many records | `table` |
| Parallel short items with icons | `cards` |
| A supplied photo | `image` (local file path, with caption and credit) |

Run `python3 briefing.py sections` for every field. `icons --query x` finds icon names;
`countries --query x` checks map names.

## Rules

- Content only from the gathered evidence. No invented numbers, dates, quotes or places.
- Cite with `sources: ["id"]` on the item; list each id once in root `sources`.
- Mix section types. Never three boxed sections (cards, table, callout) in a row,
  never the same type twice in a row (except text and chapter).
- Short headings (under 90 characters). Text blocks of 1-4 short paragraphs.
- Plain text everywhere: no HTML, no Markdown.
- Missing evidence goes in `limitations`, not hidden.
- Themes: `editorial` (default, reports), `briefing` (dark, security briefings),
  `ledger` (data-heavy). Use the one the user asks for.
- Output is a NEW file in output/. Never overwrite the user's files.
