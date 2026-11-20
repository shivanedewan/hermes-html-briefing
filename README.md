# Hermes — design prototypes for review

This repository holds **two separate, independent projects**. Each has its own folder,
README, tests and screenshots, and each can be approved, run and integrated on its own.

| Folder | Project | What it does | Start here |
|---|---|---|---|
| [`html-briefing/`](html-briefing/) | **Hermes HTML Briefing** | Turns research results into a designed, self-contained, offline HTML briefing page (cover, key points, stats, timeline, map, comparison, charts, sources). Replaces the single current report template. | [`html-briefing/README.md`](html-briefing/README.md) · `demo/before-after.png` |
| [`preview-panel/`](preview-panel/) | **Hermes Preview Panel** | A Claude-style side panel in the Hermes File Workspace that shows files beside the chat: HTML, PDF, Word, PowerPoint, Excel/CSV, images, Markdown. New files open by themselves as Hermes writes them; Markdown, text and CSV can be edited and saved as new versions. Replaces the Download-only file list. | [`preview-panel/README.md`](preview-panel/README.md) · `docs/screenshots/` |

They work well together (a briefing made by the first opens in the panel of the second) but
neither needs the other: the panel shows any file, and the briefing renderer produces a plain
`.html` file that opens in any browser.

Both are standalone prototypes, not yet wired into Hermes, and both follow the Hermes rules:
everything works offline, nothing is loaded from the internet, and model-written content is
escaped or sandboxed. Demo content is illustrative and marked "not for operational use".

## Quick start

```
# HTML briefing: render the example in any of three themes
cd html-briefing
python3 briefing.py render examples/example-brief.json --output out/brief.html --theme briefing
python3 -m unittest discover -s tests

# Preview panel: serve a folder of files and open http://127.0.0.1:8765
cd preview-panel
python3 server.py
python3 -m unittest discover -s tests
```
