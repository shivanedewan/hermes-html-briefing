"""python3 -m unittest discover -s tests  (standard library only)"""
import copy
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import briefing  # noqa: E402

EXAMPLE = json.loads((ROOT / "examples/example-brief.json").read_text("utf-8"))


def page(data=None, theme=None):
    return briefing.render(copy.deepcopy(data or EXAMPLE), theme=theme, base=ROOT)


class Offline(unittest.TestCase):
    def test_every_theme_renders_without_network_references(self):
        for theme in briefing.THEMES:
            html = page(theme=theme)
            self.assertNotRegex(html, r'(src|href)="(?!#|data:|https?://(www\.isro\.gov\.in|nssdc\.gsfc\.nasa\.gov))')
            self.assertNotIn("@import", html)
            self.assertIn("Content-Security-Policy", html)
            self.assertIn("default-src 'none'", html)

    def test_fonts_are_embedded(self):
        self.assertEqual(page().count("@font-face"), 5)


class Safety(unittest.TestCase):
    def test_text_is_escaped(self):
        d = copy.deepcopy(EXAMPLE)
        d["title"] = "<script>alert(1)</script>"
        d["sections"][0]["points"][0] = '"><img src=x onerror=alert(1)>'
        html = page(d)
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertNotIn("<img src=x", html)

    def test_unknown_source_id_fails(self):
        d = copy.deepcopy(EXAMPLE)
        d["sections"][0]["sources"] = ["missing"]
        with self.assertRaises(briefing.BriefError):
            page(d)

    def test_unknown_field_and_type_fail(self):
        d = copy.deepcopy(EXAMPLE); d["sections"][0]["colour"] = "red"
        with self.assertRaises(briefing.BriefError):
            page(d)
        d = copy.deepcopy(EXAMPLE); d["sections"][0]["type"] = "carousel"
        with self.assertRaises(briefing.BriefError):
            page(d)

    def test_non_http_source_url_fails(self):
        d = copy.deepcopy(EXAMPLE); d["sources"][0]["url"] = "javascript:alert(1)"
        with self.assertRaises(briefing.BriefError):
            page(d)


class Content(unittest.TestCase):
    def test_every_supplied_item_reaches_the_page(self):
        html = page()
        for sec in EXAMPLE["sections"]:
            for ev in sec.get("events", []):
                self.assertIn(briefing.esc(ev["title"]), html)
            for row in sec.get("rows", []):
                self.assertIn(briefing.esc(row[0]), html)
            for side in sec.get("sides", []):
                self.assertIn(briefing.esc(side["name"]), html)

    def test_four_sided_comparison_is_a_two_by_two_grid(self):
        d = {"title": "T", "sections": [{"type": "compare", "sides": [
            {"name": n, "points": ["p"]} for n in ("UN", "US", "Arab states", "ICC/ICJ")]}]}
        html = page(d)
        self.assertIn('class="compare g2"', html)
        self.assertEqual(html.count('class="side"'), 4)

    def test_map_has_markers_labels_and_country(self):
        d = {"title": "T", "sections": [{"type": "map", "focus": ["Greece"], "markers": [
            {"name": "Piraeus", "lat": 37.94, "lon": 23.65}]}]}
        html = page(d)
        self.assertIn("Piraeus", html)
        self.assertIn('class="m-focus"', html)
        self.assertEqual(briefing.country("Grecia")["name"], "Greece")

    def test_unknown_country_fails(self):
        with self.assertRaises(briefing.BriefError):
            briefing.country("Atlantis")


class Lint(unittest.TestCase):
    def test_example_is_clean(self):
        self.assertEqual(briefing.lint(EXAMPLE), [])

    def test_monotony_is_reported(self):
        cards = {"type": "cards", "items": [{"title": "a"}]}
        d = {"title": "T", "sections": [dict(cards), {"type": "callout", "body": "b"}, {"type": "table",
             "columns": ["a"], "rows": [["1"]]}]}
        msgs = " ".join(w["message"] for w in briefing.lint(d))
        self.assertIn("three boxed sections", msgs)


if __name__ == "__main__":
    unittest.main()
