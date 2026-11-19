#!/usr/bin/env python3
"""Open the demo in headless Chromium and capture the panel with every file type.

    python3 server.py &            # first
    python3 tools/screenshots.py [--url http://127.0.0.1:8765] [--out docs/screenshots]

Also reports console errors and any request that left the machine (there should be none).
"""
import argparse
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

SHOTS = [
    ("01-briefing-html", "india_space_briefing-v2.html", None),
    ("02-deck-pptx", "india_space_programme.pptx", None),
    ("03-note-docx", "india_space_note.docx", None),
    ("04-note-docx-exact", "india_space_note.docx", "Exact layout"),
    ("05-briefing-pdf", "india_space_briefing.pdf", None),
    ("06-data-xlsx", "india_space_data.xlsx", None),
    ("07-notes-md", "research_notes.md", None),
    ("08-map-png", "launch_centres_map.png", None),
    ("09-csv", "missions.csv", None),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8765")
    ap.add_argument("--out", default="docs/screenshots")
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    problems = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 1600, "height": 960}, device_scale_factor=1)
        external = []
        ctx.on("request", lambda r: external.append(r.url) if not r.url.startswith((a.url, "data:", "blob:", "about:")) else None)
        page = ctx.new_page()
        page.on("console", lambda m: problems.append(f"console {m.type}: {m.text}") if m.type == "error" else None)
        page.on("pageerror", lambda e: problems.append(f"page error: {e}"))
        page.goto(a.url + "/")
        page.wait_for_selector(".panel:not([hidden]) iframe")
        page.wait_for_timeout(2500)
        page.screenshot(path=str(out / "00-auto-open.png"))
        for name, fname, mode in SHOTS:
            page.locator(".frow", has_text=fname).first.click()
            if mode:
                page.locator("#modes button", has_text=mode).click()
            page.wait_for_timeout(3500)
            frame = page.frames[-1]
            err = frame.locator(".msg").all_inner_texts() if frame else []
            if any("can't be previewed" in t for t in err):
                problems.append(f"{fname}: {err}")
            page.screenshot(path=str(out / f"{name}.png"))
        # version switch + full screen
        page.locator(".frow", has_text="india_space_briefing.html").first.click()
        page.wait_for_timeout(2000)
        page.screenshot(path=str(out / "10-version-1.png"))
        page.locator(".frow", has_text="india_space_programme.pptx").first.click()
        page.wait_for_timeout(2500)
        page.keyboard.press("f"); page.wait_for_timeout(1200)
        page.screenshot(path=str(out / "11-fullscreen-deck.png"))
        page.keyboard.press("Escape")
        # phone width
        phone = b.new_context(viewport={"width": 400, "height": 860}, device_scale_factor=2).new_page()
        phone.goto(a.url + "/#phone"); phone.wait_for_timeout(600)
        phone.screenshot(path=str(out / "12-phone-chat.png"))
        phone.locator(".card", has_text="india_space_programme.pptx").click(); phone.wait_for_timeout(3000)
        phone.screenshot(path=str(out / "12-phone.png"))
        b.close()
    report = {"ok": not problems and not external, "problems": problems, "external_requests": external,
              "screenshots": sorted(x.name for x in out.glob("*.png"))}
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
