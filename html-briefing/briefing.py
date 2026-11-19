#!/usr/bin/env python3
"""Hermes HTML briefing renderer: briefing JSON -> one self-contained, offline HTML page.

The model writes content (JSON); this program owns the design. Every page embeds its own
fonts, icons, maps and script, loads nothing from the network, and escapes all text.

    python3 briefing.py render brief.json --output out/brief.html [--theme editorial|briefing|ledger]
    python3 briefing.py lint brief.json            # content/layout problems before rendering
    python3 briefing.py sections                   # section types and their fields
    python3 briefing.py example --output demo.json # a complete example to copy the shape from
    python3 briefing.py icons --query shield       # find icon names
    python3 briefing.py countries --query korea    # map country names

Standard library only (Python 3.8+).
"""
from __future__ import annotations

import argparse
import base64
import html
import json
import math
import mimetypes
import re
import sys
from functools import lru_cache
from pathlib import Path

RELEASE = "hermes-html-briefing 1.0"
HERE = Path(__file__).resolve().parent
ASSETS = HERE / "assets"
MAX_INPUT = 8 * 1024 * 1024
MAX_IMAGE = 6 * 1024 * 1024

THEMES = {
    "editorial": {"label": "Editorial (light paper, serif headlines)",
                  "fonts": [("Display", "InstrumentSerif-Regular", 400, "normal"),
                            ("Display", "InstrumentSerif-Italic", 400, "italic"),
                            ("Body", "InstrumentSans-Regular", 400, "normal"),
                            ("Body", "InstrumentSans-Bold", 700, "normal"),
                            ("Mono", "IBMPlexMono-Regular", 400, "normal")]},
    "briefing": {"label": "Briefing (dark, high contrast)",
                 "fonts": [("Display", "BricolageGrotesque-Bold", 700, "normal"),
                           ("Display", "BricolageGrotesque-Regular", 400, "normal"),
                           ("Body", "WorkSans-Regular", 400, "normal"),
                           ("Body", "WorkSans-Bold", 700, "normal"),
                           ("Mono", "IBMPlexMono-Regular", 400, "normal")]},
    "ledger": {"label": "Ledger (clean white, data-first)",
               "fonts": [("Display", "Outfit-Bold", 700, "normal"),
                         ("Display", "Outfit-Regular", 400, "normal"),
                         ("Body", "InstrumentSans-Regular", 400, "normal"),
                         ("Body", "InstrumentSans-Bold", 700, "normal"),
                         ("Mono", "IBMPlexMono-Regular", 400, "normal")]},
}

# section type -> (required fields, optional fields, boxed?)
SECTIONS = {
    "bluf":     ({"points"}, {"title", "sources"}, False),
    "stats":    ({"items"}, {"title", "intro"}, False),
    "text":     ({"body"}, {"title", "kicker", "pullquote", "sources"}, False),
    "chapter":  ({"title"}, {"number", "lede"}, False),
    "quote":    ({"text"}, {"by", "role", "sources"}, False),
    "timeline": ({"events"}, {"title", "intro"}, False),
    "map":      ({"focus"}, {"title", "intro", "view", "markers", "links", "caption"}, False),
    "compare":  ({"sides"}, {"title", "intro", "sources"}, False),
    "list":     ({"items"}, {"title", "intro"}, False),
    "cards":    ({"items"}, {"title", "intro"}, True),
    "bars":     ({"items"}, {"title", "intro", "unit", "sources"}, False),
    "table":    ({"columns", "rows"}, {"title", "caption", "row_sources"}, True),
    "callout":  ({"body"}, {"title", "tone", "sources"}, True),
    "image":    ({"path"}, {"title", "caption", "credit", "alt"}, False),
}
ROOT_FIELDS = {"title", "subtitle", "eyebrow", "date", "classification", "author", "theme",
               "cover", "sections", "sources", "limitations", "summary"}
ICON_ALIASES = {"security": "shield", "defence": "shield", "defense": "shield", "military": "swords",
                "warning": "triangle-alert", "alert": "triangle-alert", "risk": "triangle-alert",
                "economy": "banknote", "money": "banknote", "law": "scale", "legal": "scale",
                "government": "landmark", "diplomacy": "handshake", "people": "users", "space": "rocket",
                "location": "map-pin", "place": "map-pin", "date": "calendar", "growth": "trending-up",
                "decline": "trending-down", "intelligence": "eye", "document": "file-text",
                "energy": "zap", "industry": "factory", "navy": "ship", "air": "plane", "target": "target"}


class BriefError(ValueError):
    pass


# ----------------------------------------------------------------------------- helpers
def esc(value) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def slug(text, used):
    base = re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")[:48] or "section"
    name, i = base, 2
    while name in used:
        name, i = f"{base}-{i}", i + 1
    used.add(name)
    return name


def paragraphs(text):
    parts = [p.strip() for p in re.split(r"\n\s*\n", str(text or "")) if p.strip()]
    return "".join(f"<p>{esc(p)}</p>" for p in parts)


@lru_cache(maxsize=1)
def _icons():
    return json.loads((ASSETS / "icons/lucide.json").read_text("utf-8"))["icons"]


def icon(name, cls="ic"):
    if not name:
        return ""
    name = ICON_ALIASES.get(str(name).lower(), str(name).lower())
    body = _icons().get(name)
    if not body:
        return ""
    return (f'<svg class="{cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" '
            f'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{body}</svg>')


@lru_cache(maxsize=1)
def _world():
    return json.loads((ASSETS / "geo/world.json").read_text("utf-8"))


def _norm(s):
    return re.sub(r"[^a-z]", "", str(s).lower())


COUNTRY_ALIASES = {"usa": "United States of America", "us": "United States of America",
                   "unitedstates": "United States of America", "uk": "United Kingdom",
                   "uae": "United Arab Emirates", "burma": "Myanmar", "southkorea": "South Korea",
                   "northkorea": "North Korea", "russia": "Russia", "czechrepublic": "Czechia",
                   "grecia": "Greece", "ivorycoast": "Côte d'Ivoire"}


def country(name):
    key = _norm(COUNTRY_ALIASES.get(_norm(name), name))
    for c in _world():
        if _norm(c["name"]) == key or _norm(c.get("iso3", "")) == key or \
                any(_norm(a) == key for a in c.get("aliases", [])):
            return c
    raise BriefError(f"Unknown country for map: {name!r} (try: briefing.py countries --query ...)")


def citations(ids, srcmap):
    ids = [i for i in (ids or []) if i]
    if not ids:
        return ""
    out = []
    for i in ids:
        if i not in srcmap:
            raise BriefError(f"Source id {i!r} is cited but not listed in sources")
        n = srcmap[i]
        out.append(f'<a class="cite" href="#src-{esc(i)}" title="Source {n}">{n}</a>')
    return '<span class="cites">' + "".join(out) + "</span>"


def data_uri(path, base):
    p = Path(path)
    if not p.is_absolute():
        p = (base / p).resolve()
    if not p.is_file():
        raise BriefError(f"Image not found: {path}")
    if p.stat().st_size > MAX_IMAGE:
        raise BriefError(f"Image larger than 6 MiB, resize it first: {path}")
    mime = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
    if mime not in {"image/jpeg", "image/png", "image/webp", "image/gif", "image/svg+xml"}:
        raise BriefError(f"Unsupported image type {mime}: {path}")
    return f"data:{mime};base64," + base64.b64encode(p.read_bytes()).decode()


# ----------------------------------------------------------------------------- maps (SVG)
def _bbox_of(c):
    xs = [x for poly in c["polys"] for x, _ in poly[0]]
    ys = [y for poly in c["polys"] for _, y in poly[0]]
    # big countries spanning the dateline / far territories: use the polygon holding the label
    lab = c.get("label")
    if (max(xs) - min(xs) > 60) and lab:
        best = None
        for poly in c["polys"]:
            px = [x for x, _ in poly[0]]; py = [y for _, y in poly[0]]
            box = (min(px), max(px), min(py), max(py))
            area = (box[1] - box[0]) * (box[3] - box[2])
            if best is None or area > best[0]:
                best = (area, box)
        return best[1]
    return min(xs), max(xs), min(ys), max(ys)


def map_svg(spec, *, width=1000, height=None, art=False):
    focus = [country(n) for n in spec.get("focus", [])]
    view = [country(n) for n in spec.get("view", [])]
    markers = spec.get("markers", []) or []
    boxes = [_bbox_of(c) for c in focus + view]
    for m in markers:
        lat, lon = float(m["lat"]), float(m["lon"])
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise BriefError(f"Marker {m.get('name')!r} has invalid coordinates")
        boxes.append((lon, lon, lat, lat))
    if not boxes:
        raise BriefError("A map needs focus countries or markers")
    w = min(b[0] for b in boxes); e = max(b[1] for b in boxes)
    s = min(b[2] for b in boxes); n = max(b[3] for b in boxes)
    pad = 0.08 if art else 0.16
    dx, dy = max(1.5, (e - w) * pad), max(1.5, (n - s) * pad)
    w, e, s, n = w - dx, e + dx, max(-85, s - dy), min(85, n + dy)
    k = max(0.3, math.cos(math.radians((s + n) / 2)))
    span_x, span_y = (e - w) * k, (n - s)
    if height is None:  # tall subjects (India, Chile) get a taller frame instead of empty sides
        height = int(min(1000, max(560, width * span_y / span_x)))
    # fit the frame to the requested aspect ratio
    want = width / height
    if span_x / span_y < want:
        extra = (span_y * want - span_x) / k / 2; w, e = w - extra, e + extra
    else:
        extra = (span_x / want - span_y) / 2; s, n = s - extra, n + extra
    scale = width / ((e - w) * k)
    cx = (w + e) / 2

    def pr(lon, lat):
        return (width / 2 + (lon - cx) * k * scale, height / 2 - (lat - (s + n) / 2) * scale)

    focus_names = {c["name"] for c in focus}
    paths_land, paths_focus = [], []
    for c in _world():
        for poly in c["polys"]:
            ring0 = poly[0]
            px = [x for x, _ in ring0]; py = [y for _, y in ring0]
            if max(px) < w or min(px) > e or max(py) < s or min(py) > n:
                continue
            d = []
            for ri, ring in enumerate(poly):
                pts = [pr(x, y) for x, y in ring]
                d.append("M" + "L".join(f"{x:.1f},{y:.1f}" for x, y in pts) + "Z")
            (paths_focus if c["name"] in focus_names else paths_land).append("".join(d))
    out = [f'<svg class="{"map-art" if art else "map-svg"}" viewBox="0 0 {width} {height}" role="img" '
           f'aria-label="{esc("Map of " + ", ".join(spec.get("focus", [])))}" preserveAspectRatio="xMidYMid slice">']
    if not art:
        out.append(f'<rect width="{width}" height="{height}" class="m-sea"/>')
        # graticule
        step = 5 if (e - w) < 40 else 10 if (e - w) < 90 else 20
        for lon in range(int(math.floor(w / step) * step), int(e) + 1, step):
            x, _ = pr(lon, 0)
            out.append(f'<line x1="{x:.1f}" y1="0" x2="{x:.1f}" y2="{height}" class="m-grid"/>')
        for lat in range(int(math.floor(s / step) * step), int(n) + 1, step):
            _, y = pr(0, lat)
            out.append(f'<line x1="0" y1="{y:.1f}" x2="{width}" y2="{y:.1f}" class="m-grid"/>')
        out.append('<path class="m-land" fill-rule="evenodd" d="' + "".join(paths_land) + '"/>')
    out.append('<path class="m-focus" fill-rule="evenodd" d="' + "".join(paths_focus) + '"/>')
    if art:
        out.append("</svg>")
        return "".join(out)
    pins = [pr(float(m["lon"]), float(m["lat"])) for m in markers]
    for link in spec.get("links", []) or []:
        a, b = markers[int(link["from"])], markers[int(link["to"])]
        x1, y1 = pr(float(a["lon"]), float(a["lat"])); x2, y2 = pr(float(b["lon"]), float(b["lat"]))
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2 - abs(x2 - x1) * 0.18
        out.append(f'<path class="m-link" d="M{x1:.1f},{y1:.1f} Q{mx:.1f},{my:.1f} {x2:.1f},{y2:.1f}"/>')
    # boxes already taken: every pin, then each label as it is placed
    taken = [(x - 19, y - 19, x + 19, y + 19) for x, y in pins]

    def free(box):
        return (box[0] >= 4 and box[2] <= width - 4 and box[1] >= 4 and box[3] <= height - 4 and
                not any(box[0] < t[2] and box[2] > t[0] and box[1] < t[3] and box[3] > t[1] for t in taken))

    labels = []
    for i, ((x, y), m) in enumerate(zip(pins, markers), 1):
        tw = len(str(m["name"])) * 12.5 + 6
        options = [("start", x + 24, y + 8), ("end", x - 24, y + 8), ("start", x + 20, y + 34),
                   ("start", x + 20, y - 20), ("end", x - 20, y + 34), ("end", x - 20, y - 20),
                   ("middle", x, y + 44), ("middle", x, y - 30)]
        for anchor, lx, ly in options:
            x0 = lx if anchor == "start" else lx - tw if anchor == "end" else lx - tw / 2
            box = (x0, ly - 20, x0 + tw, ly + 6)
            if free(box):
                break
        else:
            anchor, lx, ly = options[0]; x0 = lx; box = (x0, ly - 20, x0 + tw, ly + 6)
        taken.append(box)
        labels.append(f'<text x="{lx:.1f}" y="{ly:.1f}" text-anchor="{anchor}" class="m-label">{esc(m["name"])}</text>')
    for c in focus:  # country names go where nothing else is
        lab = c.get("label")
        if not lab:
            continue
        x, y = pr(*lab)
        tw = len(c["name"]) * 18 + 10
        for dx, dy in ((0, 0), (0, 60), (0, -60), (0, 120), (80, 30), (-80, 30), (0, 180)):
            box = (x + dx - tw / 2, y + dy - 20, x + dx + tw / 2, y + dy + 6)
            if free(box):
                taken.append(box)
                out.append(f'<text x="{x + dx:.1f}" y="{y + dy:.1f}" class="m-country">{esc(c["name"].upper())}</text>')
                break
    for i, (x, y) in enumerate(pins, 1):
        out.append(f'<g class="m-pin"><circle cx="{x:.1f}" cy="{y:.1f}" r="17"/>'
                   f'<text x="{x:.1f}" y="{y + 6:.1f}">{i}</text></g>')
    out.extend(labels)
    out.append("</svg>")
    return "".join(out)


# ----------------------------------------------------------------------------- section renderers
def h2(sec, sid, default=""):
    t = sec.get("title") or default
    return f'<h2 class="sec-title">{esc(t)}</h2>' if t else ""


def intro(sec):
    return f'<p class="sec-intro">{esc(sec["intro"])}</p>' if sec.get("intro") else ""


def r_bluf(sec, ctx):
    items = "".join(f'<li><span class="n">{i:02d}</span><p>{esc(p)}</p></li>'
                    for i, p in enumerate(sec["points"], 1))
    return (f'<div class="eyebrow">{esc(sec.get("title") or "Bottom line up front")}</div>'
            f'<ol class="bluf">{items}</ol>{citations(sec.get("sources"), ctx["src"])}')


def r_stats(sec, ctx):
    cells = []
    for it in sec["items"]:
        cells.append(f'<div class="stat"><div class="stat-v">{esc(it["value"])}</div>'
                     f'<div class="stat-l">{esc(it.get("label", ""))}</div>'
                     + (f'<div class="stat-n">{esc(it["note"])}</div>' if it.get("note") else "")
                     + citations(it.get("sources"), ctx["src"]) + "</div>")
    return h2(sec, "") + intro(sec) + f'<div class="stats n{min(len(cells), 4)}">{"".join(cells)}</div>'


def r_text(sec, ctx):
    kicker = f'<div class="eyebrow">{esc(sec["kicker"])}</div>' if sec.get("kicker") else ""
    pq = f'<aside class="pullquote">{esc(sec["pullquote"])}</aside>' if sec.get("pullquote") else ""
    return (kicker + h2(sec, "") + f'<div class="prose{" has-pq" if pq else ""}">{pq}{paragraphs(sec["body"])}'
            f'{citations(sec.get("sources"), ctx["src"])}</div>')


def r_chapter(sec, ctx):
    num = f'<div class="ch-num">{esc(sec["number"])}</div>' if sec.get("number") else ""
    lede = f'<p class="ch-lede">{esc(sec["lede"])}</p>' if sec.get("lede") else ""
    return f'{num}<h2 class="ch-title">{esc(sec["title"])}</h2>{lede}'


def r_quote(sec, ctx):
    by = ""
    if sec.get("by"):
        by = f'<figcaption>{esc(sec["by"])}' + (f'<span>{esc(sec["role"])}</span>' if sec.get("role") else "") + "</figcaption>"
    return (f'<figure class="quote"><blockquote>{esc(sec["text"])}</blockquote>{by}'
            f'{citations(sec.get("sources"), ctx["src"])}</figure>')


def r_timeline(sec, ctx):
    rows = []
    for ev in sec["events"]:
        status = str(ev.get("status") or "").lower()
        chip = f'<span class="chip {esc(status)}">{esc(ev.get("tag") or status)}</span>' if (ev.get("tag") or status) else ""
        rows.append(f'<li class="ev {esc(status)}"><div class="ev-date">{esc(ev["date"])}</div>'
                    f'<div class="ev-dot">{icon(ev.get("icon"), "ic ev-ic")}</div>'
                    f'<div class="ev-body">{chip}<h3>{esc(ev["title"])}</h3>'
                    + (f'<p>{esc(ev["body"])}</p>' if ev.get("body") else "")
                    + citations(ev.get("sources"), ctx["src"]) + "</div></li>")
    return h2(sec, "") + intro(sec) + f'<ol class="timeline">{"".join(rows)}</ol>'


def r_map(sec, ctx):
    legend = ""
    if sec.get("markers"):
        items = "".join(f'<li><span class="pin">{i}</span><div><strong>{esc(m["name"])}</strong>'
                        + (f'<p>{esc(m["note"])}</p>' if m.get("note") else "")
                        + citations(m.get("sources"), ctx["src"]) + "</div></li>"
                        for i, m in enumerate(sec["markers"], 1))
        legend = f'<ol class="map-legend">{items}</ol>'
    cap = sec.get("caption") or "Natural Earth (India point of view) · schematic, not an official boundary depiction"
    return (h2(sec, "") + intro(sec) + f'<div class="map-wrap{" with-legend" if legend else ""}">'
            f'<figure class="map-fig">{map_svg(sec)}<figcaption>{esc(cap)}</figcaption></figure>{legend}</div>')


def r_compare(sec, ctx):
    sides = sec["sides"]
    cols = []
    for sd in sides:
        pts = "".join(f"<li>{esc(p)}</li>" for p in sd.get("points", []))
        stance = f'<p class="stance">{esc(sd["stance"])}</p>' if sd.get("stance") else ""
        cols.append(f'<div class="side"><div class="side-h">{icon(sd.get("icon"))}<h3>{esc(sd["name"])}</h3></div>'
                    f'{stance}<ul>{pts}</ul>{citations(sd.get("sources"), ctx["src"])}</div>')
    n = len(sides)
    grid = "g2" if n in (2, 4) else "g3"
    return (h2(sec, "") + intro(sec) + f'<div class="compare {grid}">{"".join(cols)}</div>'
            + citations(sec.get("sources"), ctx["src"]))


def r_list(sec, ctx):
    rows = "".join(f'<li><span class="n">{i}</span><div><h3>{esc(it["title"])}</h3>'
                   + (f'<p>{esc(it["body"])}</p>' if it.get("body") else "")
                   + citations(it.get("sources"), ctx["src"]) + "</div></li>"
                   for i, it in enumerate(sec["items"], 1))
    return h2(sec, "") + intro(sec) + f'<ol class="biglist">{rows}</ol>'


def r_cards(sec, ctx):
    cards = "".join(f'<div class="card">{icon(it.get("icon"), "ic card-ic")}<h3>{esc(it["title"])}</h3>'
                    + (f'<p>{esc(it["body"])}</p>' if it.get("body") else "")
                    + citations(it.get("sources"), ctx["src"]) + "</div>" for it in sec["items"])
    return h2(sec, "") + intro(sec) + f'<div class="cards">{cards}</div>'


def r_bars(sec, ctx):
    vals = []
    for it in sec["items"]:
        v = float(it["value"])
        if not math.isfinite(v) or v < 0:
            raise BriefError(f"Bar value must be a finite non-negative number: {it}")
        vals.append(v)
    top = max(vals) or 1
    unit = sec.get("unit", "")
    rows = []
    for it, v in zip(sec["items"], vals):
        shown = it.get("display") or (f"{v:,.0f}" if v == int(v) else f"{v:,.2f}") + (f" {unit}" if unit else "")
        rows.append(f'<div class="bar"><div class="bar-l">{esc(it["label"])}'
                    + (f'<span>{esc(it["note"])}</span>' if it.get("note") else "")
                    + f'</div><div class="bar-t"><div class="bar-f" style="--w:{v / top * 100:.1f}%"></div></div>'
                    f'<div class="bar-v">{esc(shown)}</div></div>')
    return (h2(sec, "") + intro(sec) + f'<div class="bars">{"".join(rows)}</div>'
            + citations(sec.get("sources"), ctx["src"]))


def r_table(sec, ctx):
    cols = sec["columns"]
    if len(set(cols)) != len(cols):
        raise BriefError("Table has duplicate column names")
    rs = sec.get("row_sources")
    if rs is not None and len(rs) != len(sec["rows"]):
        raise BriefError("row_sources must have one entry per row")
    head = "".join(f'<th scope="col"><button type="button" data-sort="{i}">{esc(c)}</button></th>'
                   for i, c in enumerate(cols))
    body = []
    for ri, row in enumerate(sec["rows"]):
        if len(row) != len(cols):
            raise BriefError(f"Table row {ri + 1} has {len(row)} cells, expected {len(cols)}")
        cells = "".join(f"<td>{esc(c)}</td>" for c in row)
        if rs:
            cells = cells[:-5] + citations(rs[ri], ctx["src"]) + "</td>"
        body.append(f"<tr>{cells}</tr>")
    cap = f'<caption>{esc(sec["caption"])}</caption>' if sec.get("caption") else ""
    return (h2(sec, "") + f'<div class="table-wrap"><table>{cap}<thead><tr>{head}</tr></thead>'
            f'<tbody>{"".join(body)}</tbody></table></div>')


def r_callout(sec, ctx):
    tone = sec.get("tone", "assessment")
    ic = {"warning": "triangle-alert", "assessment": "target", "note": "info"}.get(tone, "info")
    title = f'<h3>{esc(sec["title"])}</h3>' if sec.get("title") else ""
    return (f'<div class="callout {esc(tone)}">{icon(ic, "ic co-ic")}<div>{title}{paragraphs(sec["body"])}'
            f'{citations(sec.get("sources"), ctx["src"])}</div></div>')


def r_image(sec, ctx):
    uri = data_uri(sec["path"], ctx["base"])
    cap = " · ".join(esc(x) for x in (sec.get("caption"), sec.get("credit")) if x)
    return (h2(sec, "") + f'<figure class="photo"><img src="{uri}" alt="{esc(sec.get("alt") or sec.get("caption") or "")}">'
            + (f"<figcaption>{cap}</figcaption>" if cap else "") + "</figure>")


RENDER = {k: globals()["r_" + k] for k in SECTIONS}


# ----------------------------------------------------------------------------- validation + lint
def validate(data):
    if not isinstance(data, dict) or not data.get("title"):
        raise BriefError("Root must be an object with a title")
    extra = set(data) - ROOT_FIELDS
    if extra:
        raise BriefError(f"Unknown root fields: {sorted(extra)}")
    if data.get("theme") and data["theme"] not in THEMES:
        raise BriefError(f"Unknown theme {data['theme']!r}; choose {sorted(THEMES)}")
    ids = [s.get("id") for s in data.get("sources", [])]
    if len(ids) != len(set(ids)) or not all(ids):
        raise BriefError("Every source needs a unique id")
    for s in data.get("sources", []):
        if s.get("url") and not re.match(r"^https?://", s["url"]):
            raise BriefError(f"Source url must be http(s): {s['url']}")
    secs = data.get("sections")
    if not isinstance(secs, list) or not secs:
        raise BriefError("sections must be a non-empty list")
    for i, sec in enumerate(secs, 1):
        t = sec.get("type")
        if t not in SECTIONS:
            raise BriefError(f"Section {i}: unknown type {t!r}; choose {sorted(SECTIONS)}")
        req, opt, _ = SECTIONS[t]
        missing = [f for f in req if not sec.get(f)]
        if missing:
            raise BriefError(f"Section {i} ({t}): missing {missing}")
        unknown = set(sec) - req - opt - {"type", "id"}
        if unknown:
            raise BriefError(f"Section {i} ({t}): unknown fields {sorted(unknown)}")
        if t == "compare" and not 2 <= len(sec["sides"]) <= 6:
            raise BriefError(f"Section {i}: compare needs 2-6 sides (use a table for more)")


def lint(data):
    """Design problems worth fixing. Returns a list of {level, where, message}."""
    out = []
    secs = data["sections"]
    run = 0
    for i, sec in enumerate(secs, 1):
        boxed = SECTIONS[sec["type"]][2]
        run = run + 1 if boxed else 0
        if run == 3:
            out.append({"level": "warning", "where": f"section {i}",
                        "message": "three boxed sections in a row (cards/table/callout); use list, stats, text, compare or timeline between them"})
        if i > 1 and sec["type"] == secs[i - 2]["type"] and sec["type"] not in ("text", "chapter"):
            out.append({"level": "warning", "where": f"section {i}",
                        "message": f"two {sec['type']} sections in a row; merge them or vary the layout"})
        t = sec.get("title") or ""
        if len(t) > 90:
            out.append({"level": "warning", "where": f"section {i}", "message": "title over 90 characters"})
        if sec["type"] == "text" and len(str(sec["body"])) > 2600:
            out.append({"level": "warning", "where": f"section {i}",
                        "message": "very long text block; split it with a chapter, stats, quote or list"})
        if sec["type"] in ("cards", "list") and len(sec["items"]) > 9:
            out.append({"level": "warning", "where": f"section {i}", "message": "more than 9 items; use a table"})
        if sec["type"] == "stats" and len(sec["items"]) > 6:
            out.append({"level": "warning", "where": f"section {i}", "message": "more than 6 stats; pick the most telling"})
    kinds = {s["type"] for s in secs}
    if len(secs) >= 6 and len(kinds) < 4:
        out.append({"level": "warning", "where": "document",
                    "message": f"only {len(kinds)} section types in {len(secs)} sections; the page will look monotonous"})
    if not data.get("sources"):
        out.append({"level": "warning", "where": "document", "message": "no sources listed"})
    return out


# ----------------------------------------------------------------------------- page assembly
@lru_cache(maxsize=None)
def _font(name):
    return base64.b64encode((ASSETS / "fonts" / f"{name}.woff").read_bytes()).decode()


def fonts_css(theme):
    rules = []
    for fam, name, weight, style in THEMES[theme]["fonts"]:
        rules.append(f'@font-face{{font-family:"HB {fam}";src:url(data:font/woff;base64,{_font(name)}) format("woff");'
                     f"font-weight:{weight};font-style:{style};font-display:swap}}")
    return "".join(rules)


def render(data, *, theme=None, base=Path(".")):
    validate(data)
    theme = theme or data.get("theme") or "editorial"
    if theme not in THEMES:
        raise BriefError(f"Unknown theme {theme!r}")
    srcmap = {s["id"]: n for n, s in enumerate(data.get("sources", []), 1)}
    ctx = {"src": srcmap, "base": base}
    used, toc, body = set(), [], []
    for sec in data["sections"]:
        t = sec["type"]
        inner = RENDER[t](sec, ctx)
        title = sec.get("title") if t not in ("bluf", "quote", "callout") else None
        sid = slug(sec.get("id") or title or t, used)
        if title and t != "image":
            toc.append((sid, title, t == "chapter"))
        boxed = " boxed" if SECTIONS[t][2] else ""
        body.append(f'<section id="{sid}" class="sec s-{t}{boxed}" data-type="{t}"><div class="sec-in">{inner}</div></section>')

    cover = data.get("cover") or {}
    art = ""
    if cover.get("image"):
        art = f'<div class="cover-img" style="background-image:url({data_uri(cover["image"], base)})"></div>'
    elif cover.get("map"):
        art = f'<div class="cover-art">{map_svg(cover["map"], width=900, height=900, art=True)}</div>'
    cls = esc(data.get("classification") or "")
    banner = f'<div class="classif">{cls}</div>' if cls else ""
    meta = " · ".join(esc(x) for x in (data.get("date"), data.get("author")) if x)
    summary = f'<p class="cover-sum">{esc(data["summary"])}</p>' if data.get("summary") else ""
    head = (f'<header class="cover{" has-img" if cover.get("image") else ""}">{art}<div class="cover-in">'
            f'<div class="eyebrow">{esc(data.get("eyebrow", ""))}</div><h1>{esc(data["title"])}</h1>'
            + (f'<p class="cover-sub">{esc(data["subtitle"])}</p>' if data.get("subtitle") else "")
            + summary + (f'<div class="cover-meta">{meta}</div>' if meta else "") + "</div></header>")

    nav = "".join(f'<a href="#{sid}" class="{"ch" if ch else ""}">{esc(t)}</a>' for sid, t, ch in toc)
    src = ""
    if data.get("sources"):
        items = "".join(f'<li id="src-{esc(s["id"])}"><span class="src-n">{srcmap[s["id"]]}</span><div>'
                        + (f'<a href="{esc(s["url"])}" rel="noopener noreferrer">{esc(s["label"])}</a>' if s.get("url")
                           else f'<strong>{esc(s["label"])}</strong>')
                        + (f'<p>{esc(s["detail"])}</p>' if s.get("detail") else "") + "</div></li>"
                        for s in data["sources"])
        src = f'<section id="sources" class="sec s-sources"><div class="sec-in"><h2 class="sec-title">Sources</h2><ol class="sources">{items}</ol></div></section>'
        nav += '<a href="#sources">Sources</a>'
    lim = ""
    if data.get("limitations"):
        lim = ('<section id="limits" class="sec s-limits"><div class="sec-in"><h2 class="sec-title">Scope and limits</h2><ul>'
               + "".join(f"<li>{esc(x)}</li>" for x in data["limitations"]) + "</ul></div></section>")
        nav += '<a href="#limits">Scope and limits</a>'

    csp = ("default-src 'none'; img-src data:; font-src data:; style-src 'unsafe-inline'; "
           "script-src 'unsafe-inline'; base-uri 'none'; form-action 'none'")
    return f"""<!doctype html>
<html lang="en" data-theme="{theme}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="{csp}">
<meta name="generator" content="{RELEASE}">
<title>{esc(data["title"])}</title>
<style>{fonts_css(theme)}{CSS}</style></head>
<body>{banner}<div class="progress" aria-hidden="true"><span></span></div>
{head}
<div class="layout"><nav class="toc" aria-label="Contents"><div class="toc-h">Contents</div>{nav}</nav>
<main id="content">{"".join(body)}{lim}{src}</main></div>
<footer class="foot"><span>{esc(data["title"])}</span><span>Self-contained · works offline · {esc(RELEASE)}</span></footer>{banner}
<script>{JS}</script></body></html>"""


# ----------------------------------------------------------------------------- CSS + JS
CSS = r"""
:root{--maxw:1180px;--col:720px;--r:14px}
html[data-theme=editorial]{--bg:#f5f1e8;--paper:#fffdf7;--ink:#1c1a15;--muted:#6a6356;--rule:#d9d0bd;--soft:#ece5d6;
 --accent:#b13a2a;--accent2:#1e5a6e;--focus:#e3b8a8;--land:#e6dfcf;--sea:#f5f1e8;--grid:#e0d7c4;--on:#fff;
 --fd:"HB Display",Georgia,serif;--fb:"HB Body","Segoe UI",Arial,sans-serif;--fm:"HB Mono",Consolas,monospace;--hw:400;--hs:-.01em}
html[data-theme=briefing]{--bg:#0a1120;--paper:#0f1a2e;--ink:#e9eef6;--muted:#93a2b8;--rule:#22324d;--soft:#152340;
 --accent:#f0b43c;--accent2:#4fd1c5;--focus:#2d5a6a;--land:#1a2840;--sea:#0b1426;--grid:#14223a;--on:#0a1120;
 --fd:"HB Display","Segoe UI",Arial,sans-serif;--fb:"HB Body","Segoe UI",Arial,sans-serif;--fm:"HB Mono",Consolas,monospace;--hw:700;--hs:-.02em}
html[data-theme=ledger]{--bg:#f6f7f9;--paper:#fff;--ink:#0f172a;--muted:#5b6474;--rule:#dfe3ea;--soft:#eef1f6;
 --accent:#2443c9;--accent2:#0f8a6c;--focus:#b9c6f5;--land:#e7eaf0;--sea:#f6f7f9;--grid:#eceff4;--on:#fff;
 --fd:"HB Display","Segoe UI",Arial,sans-serif;--fb:"HB Body","Segoe UI",Arial,sans-serif;--fm:"HB Mono",Consolas,monospace;--hw:700;--hs:-.025em}
*{box-sizing:border-box}html{scroll-behavior:smooth;scroll-padding-top:24px}
body{margin:0;background:var(--bg);color:var(--ink);font:17px/1.65 var(--fb);-webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility}
a{color:var(--accent)}p{margin:0 0 1em}h1,h2,h3{font-family:var(--fd);font-weight:var(--hw);letter-spacing:var(--hs);line-height:1.12;margin:0;overflow-wrap:anywhere}
h3{font-family:var(--fb);font-weight:700;font-size:1.05rem;letter-spacing:0;line-height:1.35}
.eyebrow{font:500 .74rem/1.4 var(--fm);letter-spacing:.14em;text-transform:uppercase;color:var(--accent);margin-bottom:14px}
.classif{text-align:center;font:600 .72rem/1 var(--fm);letter-spacing:.2em;padding:7px;background:var(--ink);color:var(--bg);text-transform:uppercase}
.progress{position:fixed;top:0;left:0;right:0;height:3px;z-index:9}.progress span{display:block;height:100%;width:0;background:var(--accent)}
/* cover */
.cover{position:relative;overflow:hidden;min-height:78vh;display:flex;align-items:flex-end;padding:96px 6vw 72px;border-bottom:1px solid var(--rule)}
.cover-in{position:relative;max-width:900px;z-index:1}
.cover h1{font-size:clamp(2.6rem,6.4vw,5.6rem);margin-bottom:22px}
html[data-theme=editorial] .cover h1{font-size:clamp(3rem,7.4vw,6.6rem);line-height:1.02}
.cover-sub{font-size:clamp(1.1rem,1.9vw,1.45rem);color:var(--muted);max-width:740px;margin-bottom:22px}
.cover-sum{max-width:680px;border-left:3px solid var(--accent);padding-left:18px;font-size:1.02rem}
.cover-meta{font:.8rem var(--fm);color:var(--muted);letter-spacing:.06em;margin-top:28px}
.cover-art{position:absolute;right:2vw;top:50%;transform:translateY(-50%);width:min(46vw,760px);aspect-ratio:1;opacity:.9;pointer-events:none}
.cover:has(.cover-art) .cover-in{max-width:min(900px,56vw)}
.map-art{width:100%;height:100%}.map-art .m-focus{fill:var(--focus);stroke:var(--accent);stroke-width:1.2;opacity:.55}
html[data-theme=briefing] .map-art .m-focus{fill:#173a4a;stroke:var(--accent2);opacity:.75;filter:drop-shadow(0 0 22px #4fd1c540)}
html[data-theme=briefing] .cover{background:radial-gradient(1200px 600px at 85% 30%,#13304a 0,transparent 60%),var(--bg)}
.cover.has-img{color:#fff;min-height:88vh}.cover.has-img .cover-sub,.cover.has-img .cover-meta{color:#e6e9ef}
.cover-img{position:absolute;inset:0;background-size:cover;background-position:center}
.cover-img:after{content:"";position:absolute;inset:0;background:linear-gradient(180deg,#0000 20%,#000c 100%)}
/* layout */
.layout{max-width:calc(var(--maxw) + 260px);margin:0 auto;display:grid;grid-template-columns:220px minmax(0,1fr);gap:40px;padding:0 4vw}
.toc{position:sticky;top:28px;align-self:start;padding:56px 0 24px;display:flex;flex-direction:column;gap:2px;max-height:calc(100vh - 40px);overflow:auto}
.toc-h{font:.7rem var(--fm);letter-spacing:.16em;text-transform:uppercase;color:var(--muted);margin-bottom:10px}
.toc a{color:var(--muted);text-decoration:none;font-size:.86rem;line-height:1.35;padding:6px 0 6px 12px;border-left:2px solid var(--rule)}
.toc a.ch{color:var(--ink);font-weight:700;margin-top:8px}.toc a.on{color:var(--accent);border-left-color:var(--accent)}
main{min-width:0}
.sec{padding:64px 0;border-bottom:1px solid var(--rule)}.sec:last-child{border-bottom:0}
.sec-title{font-size:clamp(1.8rem,3vw,2.6rem);margin-bottom:14px;max-width:820px}
html[data-theme=editorial] .sec-title{font-size:clamp(2rem,3.4vw,3rem)}
.sec-intro{color:var(--muted);font-size:1.08rem;max-width:var(--col);margin-bottom:30px}
.cites{display:inline-flex;gap:3px;margin-left:4px;vertical-align:super;line-height:1}
.cite{font:600 .62rem var(--fm);text-decoration:none;color:var(--accent);background:var(--soft);border-radius:4px;padding:2px 4px}
/* bluf */
.s-bluf{padding-top:72px}.bluf{list-style:none;margin:0;padding:0;display:grid;gap:4px}
.bluf li{display:grid;grid-template-columns:72px 1fr;gap:12px;padding:20px 0;border-top:1px solid var(--rule)}
.bluf .n{font:var(--hw) 2.2rem/1 var(--fd);color:var(--accent)}.bluf p{font-size:clamp(1.12rem,1.6vw,1.35rem);line-height:1.5;margin:0;max-width:820px}
/* stats */
.stats{display:grid;grid-template-columns:repeat(var(--c,3),minmax(0,1fr));border-top:2px solid var(--ink)}
.stats.n1{--c:1}.stats.n2{--c:2}.stats.n3{--c:3}.stats.n4{--c:4}
.stat{padding:26px 22px 8px 0;border-right:1px solid var(--rule);margin-right:22px}.stat:last-child{border-right:0}
.stat-v{font:var(--hw) clamp(2.4rem,4.6vw,4rem)/1 var(--fd);letter-spacing:-.02em;color:var(--accent)}
html[data-theme=briefing] .stat-v{color:var(--ink)}
.stat-l{font-weight:700;margin-top:12px}.stat-n{color:var(--muted);font-size:.9rem;margin-top:4px}
/* text */
.prose{max-width:var(--col);font-size:1.06rem}.prose p:first-of-type:first-letter{}
html[data-theme=editorial] .s-text .prose>p:first-of-type::first-letter{float:left;font:400 4.4rem/.8 var(--fd);color:var(--accent);margin:6px 10px 0 0}
.prose.has-pq{max-width:none;display:grid;grid-template-columns:minmax(0,var(--col)) 1fr;column-gap:48px}
.prose.has-pq>*{grid-column:1}.pullquote{grid-column:2!important;grid-row:1/span 3;align-self:start;font:400 1.55rem/1.3 var(--fd);color:var(--accent);border-top:3px solid var(--accent);padding-top:16px;font-style:italic}
html[data-theme=briefing] .pullquote,html[data-theme=ledger] .pullquote{font-style:normal}
/* chapter */
.s-chapter{padding:110px 0 70px;border-bottom:0}.ch-num{font:var(--hw) 6rem/1 var(--fd);color:transparent;-webkit-text-stroke:1.5px var(--accent);margin-bottom:10px}
.ch-title{font-size:clamp(2.4rem,5vw,4.2rem);max-width:900px}.ch-lede{font-size:1.25rem;color:var(--muted);max-width:760px;margin-top:20px}
/* quote */
.quote{margin:0;max-width:900px}.quote blockquote{margin:0;font:400 clamp(1.6rem,3vw,2.5rem)/1.25 var(--fd);position:relative;padding-left:56px}
.quote blockquote:before{content:"\201C";position:absolute;left:0;top:-14px;font:400 6rem/1 var(--fd);color:var(--accent)}
.quote figcaption{margin:22px 0 0 56px;font-weight:700}.quote figcaption span{display:block;font-weight:400;color:var(--muted);font-size:.9rem}
/* timeline */
.timeline{list-style:none;margin:0;padding:0;position:relative}
.timeline:before{content:"";position:absolute;left:170px;top:8px;bottom:8px;width:2px;background:var(--rule)}
.ev{display:grid;grid-template-columns:150px 42px minmax(0,1fr);gap:0 0;padding:0 0 34px}
.ev-date{font:600 .82rem/1.4 var(--fm);color:var(--accent);padding-top:6px;text-align:right;padding-right:6px}
.ev-dot{display:flex;justify-content:center;padding-top:4px;position:relative}
.ev-dot:before{content:"";width:16px;height:16px;border-radius:50%;background:var(--paper);border:3px solid var(--accent);margin-top:2px;position:relative;z-index:1}
.ev-dot .ev-ic{display:none}
.ev.planned .ev-dot:before,.ev.unconfirmed .ev-dot:before{border-style:dashed;background:var(--bg)}
.ev-body{padding-left:14px;max-width:680px}.ev-body h3{font-size:1.15rem;margin:2px 0 6px}.ev-body p{color:var(--muted);margin:0}
.chip{display:inline-block;font:600 .66rem var(--fm);letter-spacing:.1em;text-transform:uppercase;padding:3px 8px;border-radius:99px;background:var(--soft);color:var(--ink);margin-bottom:6px}
.chip.planned,.chip.unconfirmed{background:transparent;border:1px dashed var(--muted);color:var(--muted)}
.chip.confirmed{background:var(--accent);color:var(--on)}
/* map */
.map-wrap{display:grid;gap:28px}.map-wrap.with-legend{grid-template-columns:minmax(0,1.7fr) minmax(220px,1fr);align-items:start}
.map-fig{margin:0}.map-svg{width:100%;height:auto;display:block;border-radius:var(--r);border:1px solid var(--rule)}
.map-fig figcaption{font:.72rem var(--fm);color:var(--muted);margin-top:8px}
.m-sea{fill:var(--sea)}.m-grid{stroke:var(--grid);stroke-width:1}.m-land{fill:var(--land);stroke:var(--paper);stroke-width:.8}
.m-focus{fill:var(--focus);stroke:var(--accent);stroke-width:1.6}
.m-country{font:600 22px var(--fm);letter-spacing:.24em;fill:var(--ink);opacity:.55;text-anchor:middle}
.m-pin circle{fill:var(--accent);stroke:var(--paper);stroke-width:3}.m-pin text{font:700 17px var(--fb);fill:var(--on);text-anchor:middle}
.m-label{font:700 23px var(--fb);fill:var(--ink);paint-order:stroke;stroke:var(--paper);stroke-width:6px;stroke-linejoin:round}
.m-link{fill:none;stroke:var(--accent2);stroke-width:2.4;stroke-dasharray:7 6}
.map-legend{list-style:none;margin:0;padding:0}.map-legend li{display:grid;grid-template-columns:34px 1fr;gap:10px;padding:12px 0;border-top:1px solid var(--rule)}
.map-legend p{color:var(--muted);font-size:.92rem;margin:2px 0 0}
.pin{display:grid;place-items:center;width:26px;height:26px;border-radius:50%;background:var(--accent);color:var(--on);font:700 .78rem var(--fb)}
/* compare */
.compare{display:grid;gap:0 36px}.compare.g2{grid-template-columns:repeat(2,minmax(0,1fr))}.compare.g3{grid-template-columns:repeat(3,minmax(0,1fr))}
.side{border-top:3px solid var(--ink);padding:18px 0 26px}.side:nth-child(3n+2){border-top-color:var(--accent)}.side:nth-child(3n){border-top-color:var(--accent2)}
.side-h{display:flex;align-items:center;gap:10px;margin-bottom:10px}.side-h h3{font:var(--hw) 1.45rem/1.15 var(--fd);letter-spacing:var(--hs)}
.side-h .ic{width:24px;height:24px;color:var(--accent);flex:none}.stance{font-style:italic;color:var(--muted)}
.side ul{margin:0;padding-left:1.1em}.side li{margin:0 0 .5em}
/* big list */
.biglist{list-style:none;margin:0;padding:0;counter-reset:x}.biglist li{display:grid;grid-template-columns:90px minmax(0,1fr);gap:16px;padding:22px 0;border-top:1px solid var(--rule)}
.biglist .n{font:var(--hw) 3.4rem/.9 var(--fd);color:var(--accent)}.biglist h3{font:var(--hw) 1.5rem/1.2 var(--fd);letter-spacing:var(--hs);margin-bottom:6px}
.biglist p{color:var(--muted);margin:0;max-width:var(--col)}
/* cards (boxed) */
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:18px}
.card{background:var(--paper);border:1px solid var(--rule);border-radius:var(--r);padding:24px}.card p{color:var(--muted);margin:6px 0 0;font-size:.95rem}
.card-ic{width:30px;height:30px;color:var(--accent);margin-bottom:12px;display:block}
/* bars */
.bars{display:grid;gap:14px;max-width:960px}.bar{display:grid;grid-template-columns:minmax(140px,240px) minmax(0,1fr) 110px;gap:18px;align-items:center}
.bar-l{font-weight:700;line-height:1.3}.bar-l span{display:block;font-weight:400;color:var(--muted);font-size:.85rem}
.bar-t{height:14px;background:var(--soft);border-radius:99px;overflow:hidden}.bar-f{height:100%;width:var(--w);background:var(--accent);border-radius:99px;transition:width 1.1s cubic-bezier(.2,.8,.2,1)}
.bar-v{font:600 .95rem var(--fm);text-align:right}
/* table */
.table-wrap{overflow:auto;border:1px solid var(--rule);border-radius:var(--r);background:var(--paper)}
table{border-collapse:collapse;width:100%;font-size:.93rem}caption{text-align:left;padding:14px 16px;color:var(--muted);font-size:.85rem}
th{position:sticky;top:0;background:var(--soft);text-align:left}th button{all:unset;cursor:pointer;display:block;padding:12px 16px;font-weight:700}
th button:after{content:" \2195";color:var(--muted);font-size:.8em}td{padding:12px 16px;border-top:1px solid var(--rule);vertical-align:top}
/* callout */
.callout{display:grid;grid-template-columns:40px 1fr;gap:16px;background:var(--paper);border:1px solid var(--rule);border-left:5px solid var(--accent);border-radius:var(--r);padding:26px 28px;max-width:900px}
.callout.warning{border-left-color:#c2410c}.callout.note{border-left-color:var(--accent2)}.co-ic{width:30px;height:30px;color:var(--accent)}
.callout h3{font:var(--hw) 1.4rem/1.2 var(--fd);letter-spacing:var(--hs);margin-bottom:8px}.callout p:last-of-type{margin-bottom:0}
/* photo */
.photo{margin:0}.photo img{width:100%;height:auto;max-height:78vh;object-fit:cover;border-radius:var(--r);display:block}
.photo figcaption{font-size:.85rem;color:var(--muted);margin-top:10px}
/* sources + limits */
.sources{list-style:none;margin:0;padding:0;columns:2;column-gap:40px}.sources li{break-inside:avoid;display:grid;grid-template-columns:32px 1fr;gap:8px;padding:10px 0;border-top:1px solid var(--rule)}
.src-n{font:600 .8rem var(--fm);color:var(--accent)}.sources p{color:var(--muted);font-size:.86rem;margin:2px 0 0}
.s-limits ul{color:var(--muted);max-width:var(--col)}
.foot{display:flex;justify-content:space-between;gap:20px;flex-wrap:wrap;padding:28px 6vw 40px;font:.74rem var(--fm);color:var(--muted);border-top:1px solid var(--rule)}
/* reveal (only when JS runs; content is visible without it) */
.js .sec .sec-in{opacity:0;transform:translateY(22px);transition:opacity .7s ease,transform .7s cubic-bezier(.2,.8,.2,1)}
.js .sec.in .sec-in{opacity:1;transform:none}.js .sec:not(.in) .bar-f{width:0}
@media (prefers-reduced-motion:reduce){.js .sec .sec-in{opacity:1;transform:none;transition:none}.bar-f{transition:none}html{scroll-behavior:auto}}
html[data-theme=editorial] .biglist h3,html[data-theme=editorial] .side-h h3,html[data-theme=editorial] .callout h3{font-size:1.85rem}
html[data-theme=editorial] .card h3{font:400 1.5rem/1.15 var(--fd)}
/* responsive */
@media (max-width:1100px){.layout{grid-template-columns:1fr}.toc{display:none}.prose.has-pq{display:block}.pullquote{margin:0 0 24px}}
@media (max-width:760px){body{font-size:16px}.cover:has(.cover-art) .cover-in{max-width:none}.cover{min-height:70vh;padding:72px 22px 48px}.cover-art{width:120vw;right:-40vw;opacity:.5}
 .layout{padding:0 20px}.sec{padding:44px 0}.stats{grid-template-columns:1fr 1fr}.stat{border-right:0;margin-right:0;border-bottom:1px solid var(--rule);padding-right:12px}
 .compare.g2,.compare.g3{grid-template-columns:1fr}.map-wrap.with-legend{grid-template-columns:1fr}.bar{grid-template-columns:1fr 70px}.bar-t{grid-column:1/-1;grid-row:2}
 .timeline:before{left:7px}.ev{grid-template-columns:16px minmax(0,1fr);gap:0 14px}.ev-date{grid-column:2;text-align:left;padding:0}.ev-dot{grid-row:1/span 2;grid-column:1}
 .ev-body{grid-column:2;padding-left:0}.bluf li{grid-template-columns:48px 1fr}.biglist li{grid-template-columns:56px 1fr}.biglist .n{font-size:2.4rem}
 .sources{columns:1}.ch-num{font-size:4rem}.quote blockquote{padding-left:36px}.quote figcaption{margin-left:36px}}
@media print{.progress,.toc{display:none}.layout{display:block;padding:0}.cover{min-height:auto;padding:40px 0;break-after:page}
 .js .sec .sec-in{opacity:1;transform:none}.sec{break-inside:avoid-page;padding:28px 0}body{background:#fff}.bar-f{width:var(--w)!important}}
"""

JS = r"""
(function(){var d=document.documentElement;
 if(!matchMedia('(prefers-reduced-motion: reduce)').matches&&'IntersectionObserver' in window){d.classList.add('js');
  var io=new IntersectionObserver(function(es){es.forEach(function(e){if(e.isIntersecting){e.target.classList.add('in');io.unobserve(e.target)}})},{rootMargin:'0px 0px -8% 0px'});
  document.querySelectorAll('.sec').forEach(function(s){io.observe(s)});
  setTimeout(function(){document.querySelectorAll('.sec').forEach(function(s){var r=s.getBoundingClientRect();if(r.top<innerHeight)s.classList.add('in')})},60);
  addEventListener('beforeprint',function(){document.querySelectorAll('.sec').forEach(function(s){s.classList.add('in')})});}
 var bar=document.querySelector('.progress span'),links=[].slice.call(document.querySelectorAll('.toc a'));
 function onScroll(){var h=d.scrollHeight-innerHeight;if(bar)bar.style.width=(h>0?scrollY/h*100:0)+'%';
  var cur=null;links.forEach(function(a){var t=document.getElementById(a.getAttribute('href').slice(1));if(t&&t.getBoundingClientRect().top<innerHeight*.3)cur=a});
  links.forEach(function(a){a.classList.toggle('on',a===cur)})}
 addEventListener('scroll',onScroll,{passive:true});onScroll();
 document.querySelectorAll('table').forEach(function(tb){tb.querySelectorAll('th button').forEach(function(b){b.addEventListener('click',function(){
  var i=+b.dataset.sort,body=tb.tBodies[0],rows=[].slice.call(body.rows),asc=b.dataset.dir!=='asc';b.dataset.dir=asc?'asc':'desc';
  rows.sort(function(x,y){var a=x.cells[i].textContent.trim(),c=y.cells[i].textContent.trim(),na=parseFloat(a.replace(/[^0-9.\-]/g,'')),nc=parseFloat(c.replace(/[^0-9.\-]/g,''));
   var r=(!isNaN(na)&&!isNaN(nc))?na-nc:a.localeCompare(c);return asc?r:-r});rows.forEach(function(r){body.appendChild(r)})})})});
})();
"""


# ----------------------------------------------------------------------------- CLI
def load(path):
    p = Path(path)
    if p.stat().st_size > MAX_INPUT:
        raise BriefError("Input JSON larger than 8 MiB")
    return json.loads(p.read_text("utf-8"))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("render"); r.add_argument("source"); r.add_argument("--output", required=True)
    r.add_argument("--theme", choices=sorted(THEMES))
    l = sub.add_parser("lint"); l.add_argument("source")
    sub.add_parser("sections"); sub.add_parser("themes")
    e = sub.add_parser("example"); e.add_argument("--output", required=True)
    i = sub.add_parser("icons"); i.add_argument("--query", default="")
    c = sub.add_parser("countries"); c.add_argument("--query", default="")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "render":
            src = Path(a.source); out = Path(a.output)
            if out.resolve() == src.resolve():
                raise BriefError("Output must be a new .html path")
            data = load(src)
            page = render(data, theme=a.theme, base=src.resolve().parent)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(page, "utf-8")
            report = {"ok": True, "output": str(out), "bytes": out.stat().st_size,
                      "theme": a.theme or data.get("theme") or "editorial",
                      "sections": len(data["sections"]), "warnings": lint(data)}
        elif a.cmd == "lint":
            data = load(a.source); validate(data); report = {"ok": True, "warnings": lint(data)}
        elif a.cmd == "sections":
            report = {k: {"required": sorted(v[0]), "optional": sorted(v[1]), "boxed": v[2]} for k, v in SECTIONS.items()}
        elif a.cmd == "themes":
            report = {k: v["label"] for k, v in THEMES.items()}
        elif a.cmd == "example":
            Path(a.output).write_text((HERE / "examples/example-brief.json").read_text("utf-8"), "utf-8")
            report = {"ok": True, "output": a.output, "note": "Illustrative content: replace every value with the task's own sourced content."}
        elif a.cmd == "icons":
            q = a.query.lower()
            report = sorted(k for k in _icons() if q in k)[:60]
        elif a.cmd == "countries":
            q = _norm(a.query)
            report = sorted(c["name"] for c in _world() if q in _norm(c["name"]))[:60]
    except (BriefError, json.JSONDecodeError, OSError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 2
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
