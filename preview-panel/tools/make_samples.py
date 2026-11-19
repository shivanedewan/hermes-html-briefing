#!/usr/bin/env python3
"""Regenerate the demo files in samples/ (needs python-docx, openpyxl, node + pptxgenjs, Playwright).

The samples are illustrative: a small, consistent set of files about India's space programme,
written from widely published public facts, so the panel can be shown with every file type.
They are already included in the package; you only need this to rebuild them.
"""
import csv
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "samples"
BRIEFING = Path(os.environ.get("BRIEFING_DIR", ROOT.parent / "html-briefing"))
NODE_PATH = os.environ.get("NODE_PATH", "/opt/npm-tools/node_modules")

MISSIONS = [
    ("Aryabhata", 1975, "Earth orbit", "First Indian satellite", "Soviet launcher"),
    ("Rohini (SLV-3)", 1980, "Earth orbit", "First launch on an Indian rocket", "SLV-3"),
    ("Chandrayaan-1", 2008, "Moon (orbit)", "Orbiter and impact probe", "PSLV"),
    ("Mars Orbiter Mission", 2013, "Mars (orbit)", "Orbit achieved 2014", "PSLV"),
    ("PSLV-C37", 2017, "Earth orbit", "104 satellites on one launch", "PSLV"),
    ("Chandrayaan-2", 2019, "Moon", "Orbiter working; lander lost", "LVM3"),
    ("Chandrayaan-3", 2023, "Moon (surface)", "Soft landing near south pole", "LVM3"),
    ("Aditya-L1", 2023, "Sun-Earth L1", "Solar observatory", "PSLV"),
    ("SpaDeX", 2024, "Earth orbit", "Docking demonstrated 2025", "PSLV"),
]


def html_versions():
    sys.path.insert(0, str(BRIEFING))
    import briefing
    data = json.loads((BRIEFING / "examples/example-brief.json").read_text("utf-8"))
    full = briefing.render(data, theme="editorial", base=BRIEFING)
    v1 = dict(data, sections=data["sections"][:6])
    first = briefing.render(v1, theme="editorial", base=BRIEFING)
    (OUT / "india_space_briefing.html").write_text(first, "utf-8")
    (OUT / "india_space_briefing-v2.html").write_text(full, "utf-8")


def pdf_from_html():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page()
        page.goto((OUT / "india_space_briefing-v2.html").resolve().as_uri())
        page.emulate_media(media="print")
        page.pdf(path=str(OUT / "india_space_briefing.pdf"), format="A4", print_background=True,
                 margin={"top": "14mm", "bottom": "14mm", "left": "12mm", "right": "12mm"})
        b.close()


def docx():
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Pt, RGBColor
    d = Document()
    st = d.styles["Normal"]; st.font.name = "Calibri"; st.font.size = Pt(11)
    p = d.add_paragraph(); r = p.add_run("DEMO · NOT FOR OPERATIONAL USE"); r.bold = True
    r.font.size = Pt(9); r.font.color.rgb = RGBColor(0xB1, 0x3A, 0x2A); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    d.add_heading("Briefing note: India's space programme", 0)
    d.add_paragraph("Prepared with Hermes · November 2026").runs[0].italic = True
    d.add_heading("Bottom line", 1)
    for t in ["India has moved from sounding rockets (1963) to a soft landing near the lunar south pole (2023).",
              "Three domestic launch vehicles cover small, medium and heavy payloads.",
              "Next: human spaceflight (Gaganyaan), a national space station and lunar sample return."]:
        d.add_paragraph(t, style="List Bullet")
    d.add_heading("Background", 1)
    d.add_paragraph("India's first rocket launch lifted off from Thumba, near Thiruvananthapuram, in November 1963. "
                    "The first Indian satellite, Aryabhata, followed in 1975 on a Soviet launcher, and in 1980 the SLV-3 "
                    "rocket placed Rohini in orbit, making India able to launch its own satellites.")
    d.add_paragraph("Since then the programme has concentrated on reliable launchers and application satellites, then "
                    "turned outward: Chandrayaan-1 (2008), the Mars Orbiter Mission (orbit in 2014), Chandrayaan-3 (2023) "
                    "and the Aditya-L1 solar observatory (2023).")
    d.add_heading("Mission register", 1)
    t = d.add_table(rows=1, cols=4); t.style = "Light Grid Accent 1"
    for c, h in zip(t.rows[0].cells, ["Mission", "Year", "Destination", "Outcome"]):
        c.text = h
    for m in MISSIONS:
        cells = t.add_row().cells
        for c, v in zip(cells, m[:4]):
            c.text = str(v)
    d.add_heading("Assessment", 1)
    d.add_paragraph("Steady, low-cost progress: each mission reuses proven hardware and adds one new capability. "
                    "The main risk to the next phase is schedule, as human spaceflight carries far stricter safety demands.")
    d.add_heading("Scope and limits", 2)
    d.add_paragraph("Demonstration content from widely published public facts; verify before any operational use.")
    d.save(OUT / "india_space_note.docx")


def xlsx():
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    wb = Workbook(); ws = wb.active; ws.title = "Missions"
    ws.append(["Mission", "Year", "Destination", "Outcome", "Launcher"])
    for m in MISSIONS:
        ws.append(list(m))
    ws2 = wb.create_sheet("Launch vehicles")
    ws2.append(["Vehicle", "Role", "Approx. payload to GTO (kg)", "Notes"])
    ws2.append(["PSLV", "Workhorse", 1425, "Sub-GTO; polar and sun-synchronous orbits"])
    ws2.append(["GSLV Mk II", "Medium lift", 2250, "Indigenous cryogenic upper stage"])
    ws2.append(["LVM3", "Heavy lift", 4000, "Human-rated version planned for Gaganyaan"])
    ws2.append(["Total", "", "=SUM(C2:C4)", "Formula cell (shows the computed value)"])
    for sh in (ws, ws2):
        for c in sh[1]:
            c.font = Font(bold=True, color="FFFFFF"); c.fill = PatternFill("solid", fgColor="1E3A8A")
        for col in sh.columns:
            sh.column_dimensions[col[0].column_letter].width = max(12, max(len(str(c.value or "")) for c in col) + 2)
        sh.freeze_panes = "A2"
    wb.save(OUT / "india_space_data.xlsx")
    # LibreOffice recalculation is not needed for the demo: the viewer shows cached values when present,
    # and the formula text otherwise.


def csv_md_png():
    with open(OUT / "missions.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["Mission", "Year", "Destination", "Outcome", "Launcher"]); w.writerows(MISSIONS)
    (OUT / "research_notes.md").write_text("""# Research notes: India's space programme

*Demo notes written to show the Markdown viewer.*

## What we know
- **1963**: first sounding rocket from Thumba.
- **1975**: Aryabhata, the first Indian satellite.
- **2023**: Chandrayaan-3 soft landing near the lunar south pole.

## Open questions
1. When will the first crewed Gaganyaan flight take place?
2. How quickly will private launchers take over routine launches?

> Verify every figure against the cited source before operational use.

| Vehicle | Role |
|---|---|
| PSLV | Workhorse |
| LVM3 | Heavy lift |
""", "utf-8")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport={"width": 1440, "height": 900}, reduced_motion="reduce", device_scale_factor=1.5)
        page.goto((BRIEFING / "demo/briefing-demo-ledger.html").resolve().as_uri())
        page.locator(".map-wrap").screenshot(path=str(OUT / "launch_centres_map.png"))
        b.close()


def deck():
    env = dict(os.environ, NODE_PATH=NODE_PATH)
    subprocess.run(["node", str(ROOT / "tools/make_deck.cjs"), str(OUT / "india_space_programme.pptx")], check=True, env=env)


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    html_versions(); pdf_from_html(); docx(); xlsx(); csv_md_png(); deck()
    for f in sorted(OUT.iterdir()):
        print(f"{f.stat().st_size:>10}  {f.name}")
