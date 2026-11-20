"""python3 -m unittest discover -s tests   (standard library; LibreOffice/openpyxl tests skip when absent)"""
import http.client
import json
import shutil
import sys
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import server  # noqa: E402


class Live(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.folder = cls.tmp / "out"; cls.folder.mkdir()
        for f in (ROOT / "samples").iterdir():
            shutil.copy(f, cls.folder / f.name)
        (cls.folder / "evil.html").write_text("<script>parent.document.body.innerHTML='x'</script>")
        (cls.tmp / "secret.txt").write_text("outside")
        server.Handler.ws = server.Workspace(cls.folder, cls.tmp / "data")
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.httpd.demo = True
        cls.port = cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown(); shutil.rmtree(cls.tmp, ignore_errors=True)

    def req(self, method, path, body=None, headers=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=150)
        c.request(method, path, body=body, headers=headers or {})
        r = c.getresponse(); data = r.read(); c.close()
        return r, data

    def test_listing_groups_versions(self):
        r, data = self.req("GET", "/api/files")
        files = json.loads(data)["files"]
        v = [f for f in files if f["group"] == "output/india_space_briefing.html"]
        self.assertEqual(sorted(f["version"] for f in v), [1, 2])

    def test_model_html_is_sandboxed_even_when_opened_directly(self):
        for path in ("/api/raw/output/evil.html", "/api/download/output/evil.html"):
            r, _ = self.req("GET", path)
            csp = r.getheader("Content-Security-Policy")
            self.assertTrue(csp.startswith("sandbox allow-scripts;"), path)
            self.assertNotIn("allow-same-origin", csp)
            self.assertIn("default-src 'none'", csp)

    def test_app_pages_load_nothing_external(self):
        r, body = self.req("GET", "/")
        csp = r.getheader("Content-Security-Policy")
        self.assertIn("default-src 'self'", csp)
        self.assertNotRegex(body.decode(), r'(src|href)="https?://')
        for page in (ROOT / "static").rglob("*.html"):
            self.assertNotRegex(page.read_text("utf-8"), r'(src|href)="https?://', page.name)

    def test_path_traversal_refused(self):
        for path in ("/api/raw/output/../secret.txt", "/api/raw/output/%2e%2e%2fsecret.txt", "/api/raw/../secret.txt",
                     "/api/raw/output/", "/static/../server.py", "/api/raw/data/x", "/api/raw/output/.hidden"):
            r, _ = self.req("GET", path)
            self.assertEqual(r.status, 404, path)

    def test_sheet_csv_and_xlsx(self):
        r, data = self.req("GET", "/api/sheet/output/missions.csv")
        self.assertEqual(json.loads(data)["sheets"][0]["rows"][0][0], "Mission")
        try:
            import openpyxl  # noqa: F401
        except ImportError:
            self.skipTest("openpyxl not installed")
        r, data = self.req("GET", "/api/sheet/output/india_space_data.xlsx")
        book = json.loads(data)
        self.assertEqual([s["name"] for s in book["sheets"]], ["Missions", "Launch vehicles"])
        self.assertIn("=SUM(C2:C4)", json.dumps(book))  # formula never calculated: shown, not hidden
        self.assertEqual(len(book["sheets"][0]["rows"][0]), 5)  # no padded empty columns

    def test_office_to_pdf(self):
        if not (shutil.which("soffice") or shutil.which("libreoffice")):
            self.skipTest("LibreOffice not installed")
        for name in ("india_space_programme.pptx", "india_space_note.docx"):
            r, data = self.req("GET", f"/api/pdf/output/{name}")
            self.assertEqual(r.status, 200, name)
            self.assertTrue(data.startswith(b"%PDF"), name)

    H = {"X-Hermes": "1"}

    def test_upload_rules(self):
        r, data = self.req("POST", "/api/upload", b"# hi", {"X-Filename": "notes.md", "Sec-Fetch-Site": "same-origin", **self.H})
        self.assertEqual(r.status, 200); self.assertEqual(json.loads(data)["ref"], "uploads/notes.md")
        r, _ = self.req("POST", "/api/upload", b"MZ", {"X-Filename": "tool.exe", **self.H})
        self.assertEqual(r.status, 400)
        r, _ = self.req("POST", "/api/upload", b"x", {"X-Filename": "a.md", "Sec-Fetch-Site": "cross-site", **self.H})
        self.assertEqual(r.status, 403)
        r, _ = self.req("POST", "/api/upload", b"x", {"X-Filename": "a.md"})   # no custom header: refused
        self.assertEqual(r.status, 403)
        r, data = self.req("POST", "/api/upload", b"# again", {"X-Filename": "../../notes.md", **self.H})
        self.assertEqual(json.loads(data)["ref"], "uploads/notes (2).md")

    def save(self, ref, text, headers=None):
        body = json.dumps({"ref": ref, "text": text}).encode()
        return self.req("POST", "/api/save", body, {"Content-Type": "application/json", **(headers if headers is not None else self.H)})

    def test_save_creates_next_version_and_never_overwrites(self):
        before = (self.folder / "research_notes.md").read_bytes()
        r, data = self.save("output/research_notes.md", "# edited\n")
        self.assertEqual(r.status, 200)
        self.assertEqual(json.loads(data)["ref"], "output/research_notes-v2.md")
        r, data = self.save("output/research_notes.md", "# edited again\n")   # from v1 again -> v3, not v2
        self.assertEqual(json.loads(data)["ref"], "output/research_notes-v3.md")
        self.assertEqual((self.folder / "research_notes.md").read_bytes(), before)
        self.assertEqual((self.folder / "research_notes-v2.md").read_text(), "# edited\n")
        r, data = self.req("GET", "/api/files")
        group = [f for f in json.loads(data)["files"] if f["group"] == "output/research_notes.md"]
        self.assertEqual(sorted(f["version"] for f in group), [1, 2, 3])

    def test_save_rules(self):
        self.assertEqual(self.save("output/india_space_note.docx", "x")[0].status, 400)   # not a text file
        self.assertEqual(self.save("output/../secret.txt", "x")[0].status, 400)           # traversal
        self.assertEqual(self.save("output/missions.csv", "a,b\n", {})[0].status, 403)     # no custom header
        r, data = self.save("output/missions.csv", "Mission,Year\nX,2026\n")
        self.assertEqual(json.loads(data)["ref"], "output/missions-v2.csv")
        ws = server.Handler.ws; ws.writable = False
        try:
            self.assertEqual(self.save("output/missions.csv", "a\n")[0].status, 403)       # read-only workspace
        finally:
            ws.writable = True

    def test_simulated_hermes_writes_progressively(self):
        import time
        r, data = self.req("POST", "/api/simulate", b"", self.H)
        ref = json.loads(data)["ref"]
        self.assertTrue(ref.startswith("output/research"))
        listing = {f["ref"]: f for f in json.loads(self.req("GET", "/api/files")[1])["files"]}
        self.assertTrue(listing[ref]["writing"])
        deadline = time.time() + 20
        while time.time() < deadline and json.loads(self.req("GET", "/api/files")[1])["files"] and \
                {f["ref"]: f for f in json.loads(self.req("GET", "/api/files")[1])["files"]}[ref]["writing"]:
            time.sleep(0.5)
        r, body = self.req("GET", "/api/raw/" + ref)
        self.assertIn(b"## Open questions", body)


if __name__ == "__main__":
    unittest.main()
