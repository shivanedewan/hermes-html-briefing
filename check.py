#!/usr/bin/env python3
"""Look at a rendered briefing the way a reader would, offline.

    python3 check.py out/brief.html [--shots out/shots]

Opens the page in headless Chromium (Playwright) at desktop and phone widths with every
network request blocked, then reports: requests the page tried to make, script errors,
horizontal overflow, clipped text, empty sections, broken images, and three boxed
sections in a row. With --shots it saves full-page screenshots to look at.
Without Playwright it falls back to a plain Chrome screenshot and says the checks were not run.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

PROBE = r"""() => {
  const out = {overflow: document.documentElement.scrollWidth - innerWidth, clipped: [], empty: [], images: [], boxedRun: 0};
  document.querySelectorAll('h1,h2,h3,p,li,td,th,.stat-v,.bar-l,.bar-v').forEach(el => {
    if (el.scrollWidth > el.clientWidth + 2 && getComputedStyle(el).overflowX !== 'auto')
      out.clipped.push((el.className || el.tagName) + ': ' + el.textContent.trim().slice(0, 60));
  });
  let run = 0;
  document.querySelectorAll('section.sec').forEach(s => {
    if (!s.classList.contains('s-chapter') && (s.innerText || '').trim().length < 20 && !s.querySelector('svg,img')) out.empty.push(s.id);
    run = s.classList.contains('boxed') ? run + 1 : 0; out.boxedRun = Math.max(out.boxedRun, run);
  });
  document.querySelectorAll('img').forEach(i => { if (!i.complete || i.naturalWidth === 0) out.images.push(i.alt || 'image'); });
  return out;
}"""


def chrome():
    for name in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable"):
        if shutil.which(name):
            return shutil.which(name)
    return None


def run(path, shots=None):
    page_url = Path(path).resolve().as_uri()
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        report = {"ok": None, "checks": "not run: Playwright is not installed"}
        exe = chrome()
        if exe and shots:
            Path(shots).mkdir(parents=True, exist_ok=True)
            out = Path(shots) / (Path(path).stem + "-desktop.png")
            subprocess.run([exe, "--headless=new", "--no-sandbox", "--disable-gpu", "--hide-scrollbars",
                            "--force-prefers-reduced-motion", "--window-size=1440,2400",
                            f"--screenshot={out}", page_url], capture_output=True, timeout=90)
            report["screenshot"] = str(out)
        return report
    report = {"ok": True, "views": {}}
    with sync_playwright() as p:
        kw = {}
        if chrome() and not Path(p.chromium.executable_path).exists():
            kw["executable_path"] = chrome()
        browser = p.chromium.launch(**kw)
        for label, size in (("desktop", (1440, 900)), ("phone", (390, 844))):
            ctx = browser.new_context(viewport={"width": size[0], "height": size[1]}, reduced_motion="reduce",
                                      device_scale_factor=1)
            page = ctx.new_page()
            blocked, errors = [], []
            page.route("**/*", lambda r: r.continue_() if r.request.url.startswith(("file:", "data:"))
                       else (blocked.append(r.request.url), r.abort()))
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(page_url, wait_until="load")
            page.wait_for_timeout(300)
            res = page.evaluate(PROBE)
            res.update(blocked_requests=blocked, script_errors=errors)
            if shots:
                Path(shots).mkdir(parents=True, exist_ok=True)
                out = Path(shots) / f"{Path(path).stem}-{label}.png"
                page.screenshot(path=str(out), full_page=True)
                res["screenshot"] = str(out)
            problems = (res["overflow"] > 1 or res["clipped"] or res["empty"] or res["images"]
                        or blocked or errors or res["boxedRun"] >= 3)
            if problems:
                report["ok"] = False
            report["views"][label] = res
            ctx.close()
        browser.close()
    return report


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("html"); ap.add_argument("--shots")
    a = ap.parse_args(argv)
    report = run(a.html, a.shots)
    print(json.dumps(report, indent=2))
    return 0 if report.get("ok") is not False else 1


if __name__ == "__main__":
    sys.exit(main())
