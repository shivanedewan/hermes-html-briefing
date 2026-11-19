# Hermes HTML Briefing — proposal for review

**What it is:** a new way for Hermes to produce HTML reports. The model writes only the
content (a JSON file); this package turns it into a designed, self-contained briefing page.
It replaces the current single report template, which gives every answer the same look
(banner, metric cards, boxes).

**Status:** standalone prototype for approval. Not yet wired into Hermes.

## Look at these first

| File | What it shows |
|---|---|
| `demo/before-after.png` | Current Hermes HTML template next to the new design |
| `demo/three-themes.png` | The same briefing in the three themes |
| `demo/briefing-demo-editorial.html` | Open in any browser (works with the network off) |
| `demo/briefing-demo-briefing.html` | Dark "security briefing" theme |
| `demo/briefing-demo-ledger.html` | Clean, data-first theme |
| `demo/screenshots/` | Full-page desktop and phone captures |

The demo content (India's space programme) is compiled from widely published public facts
to show the design; it is not a BIGDATA output.

## What changes for the reader

- A **cover** with the subject's own map silhouette (or a supplied photo), title, summary and date.
- **Bottom line up front**: the three or four things a busy reader must know.
- **Headline numbers**, **timelines** (planned/unconfirmed events marked as such),
  **maps** with numbered places and a legend, **side-by-side comparisons** (2–6 sides),
  **bar charts**, **ranked lists**, **assessments**, **pull quotes**, **tables** (sortable),
  **chapters**, and numbered **source citations** on every item.
- Contents sidebar, reading-progress bar, gentle reveal animations (off for users who
  prefer reduced motion), proper phone layout, clean printing / save as PDF.
- Three themes: **editorial** (reports), **briefing** (dark, for security briefings),
  **ledger** (data-heavy).

## What stays the same (safety and offline rules)

- One `.html` file with everything embedded: fonts, icons, map, script. **No network
  requests** (enforced by a Content-Security-Policy; the checker blocks and reports any).
- All text is escaped; the model cannot inject HTML or script.
- Facts come only from the supplied content; every citation must match a listed source;
  unknown fields, sections or countries fail loudly instead of being dropped.
- Missing evidence is shown in "Scope and limits", not hidden.

## How it works

```
model writes brief.json  ->  briefing.py render  ->  one offline .html
                                  briefing.py lint  ->  design warnings (monotony, long blocks)
                                  check.py          ->  opens it headless (desktop + phone):
                                                        overflow, clipped text, empty sections,
                                                        blocked requests, script errors, screenshots
```

```
python3 briefing.py render examples/example-brief.json --output out/brief.html --theme briefing
python3 briefing.py sections        # all section types and fields
python3 check.py out/brief.html --shots out/shots
python3 -m unittest discover -s tests
```

`briefing.py` uses the Python standard library only. `check.py` uses Playwright/Chromium
when present (both already exist on the Hermes VM via the browser check); without them it
says the visual check was not run.

## Why the model can do this reliably

Gemma only chooses section types and fills plain-text fields. Layout, typography, colour,
spacing, map drawing and responsiveness are fixed in code, so the quality does not depend on
the model's design skill. The skill file (`SKILL.md`, ~500 words) tells it which section to
use for which kind of content, and the renderer warns when the page becomes monotonous
(for example three boxed sections in a row).

## If approved: integration into Hermes (next release)

1. Install as the `html-briefing` skill beside the existing `offline-html` skill.
2. Route "HTML report/briefing/page" requests to it; keep the old templates for
   dashboards and record registers.
3. Reuse the presentation toolkit's photo packs for cover and section photos.
4. Run `check.py` after every render, as the PPT pipeline already does.

## Contents

```
SKILL.md              instructions the model follows
briefing.py           renderer + lint + helper commands
check.py              headless visual/offline check
examples/             example-brief.json (shape to copy)
assets/fonts/         6 open-licensed font families (SIL OFL), subset to Latin
assets/geo/           world map, Natural Earth India point of view (public domain)
assets/icons/         Lucide icon set (ISC licence)
tests/                12 unit tests
demo/                 rendered demos, screenshots, comparison images
LICENSES.md           third-party notices
```
