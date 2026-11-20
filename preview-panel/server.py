#!/usr/bin/env python3
"""Hermes preview panel: standalone demo server (Python standard library).

    python3 server.py                       # serves ./samples on http://127.0.0.1:8765
    python3 server.py --folder /path/to/output --port 8765

Shows the files in a folder in a Claude-style side panel: HTML, PDF, Word, PowerPoint,
Excel/CSV, images, Markdown and text. Everything is served locally; nothing is fetched from
the internet. Word/PowerPoint "exact layout" and PowerPoint slides use LibreOffice when it is
installed (soffice); Excel uses openpyxl when it is installed.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

RELEASE = "hermes-preview-panel 1.1"
HERE = Path(__file__).resolve().parent
STATIC = HERE / "static"
MAX_UPLOAD = 50 * 1024 * 1024
MAX_TEXT_SAVE = 5 * 1024 * 1024
CONVERT_TIMEOUT = 120
SHEET_ROWS, SHEET_COLS, SHEET_MAX = 2000, 60, 30

KINDS = {
    ".html": "html", ".htm": "html", ".pdf": "pdf", ".docx": "docx", ".doc": "office", ".odt": "office",
    ".rtf": "office", ".pptx": "slides", ".ppt": "slides", ".odp": "slides", ".xlsx": "sheet",
    ".xlsm": "sheet", ".csv": "sheet", ".tsv": "sheet", ".png": "image", ".jpg": "image",
    ".jpeg": "image", ".gif": "image", ".webp": "image", ".svg": "image", ".md": "markdown",
    ".txt": "text", ".json": "text", ".log": "text", ".py": "text", ".xml": "text",
}
# files that can be edited in the panel (saved as a new version, never overwritten)
EDITABLE = {".md", ".txt", ".json", ".csv", ".tsv", ".log", ".xml", ".py"}
OFFICE_TO_PDF = {".docx", ".doc", ".odt", ".rtf", ".pptx", ".ppt", ".odp", ".xlsx", ".xlsm"}
mimetypes.add_type("text/javascript", ".mjs")
mimetypes.add_type("application/wasm", ".wasm")
mimetypes.add_type("text/markdown", ".md")

UI_CSP = ("default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; style-src 'self' 'unsafe-inline'; "
          "img-src 'self' data: blob:; font-src 'self' data: blob:; worker-src 'self' blob:; connect-src 'self'; "
          "frame-src 'self' blob:; object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'self'")
# Model-written HTML runs in its own sandbox (opaque origin): no access to this app, its storage or the network.
CONTENT_CSP = ("sandbox allow-scripts; default-src 'none'; img-src data: blob:; font-src data:; "
               "style-src 'unsafe-inline'; script-src 'unsafe-inline'; media-src data: blob:")

_convert_lock = threading.Lock()


class Workspace:
    def __init__(self, folder: Path, data: Path, writable: bool = True):
        self.folder = folder.resolve()
        self.writable = writable
        self.writing = set()          # refs Hermes is still writing (demo simulator)
        self._lock = threading.Lock()
        self.uploads = (data / "uploads").resolve()
        self.cache = (data / "cache").resolve()
        self.uploads.mkdir(parents=True, exist_ok=True)
        self.cache.mkdir(parents=True, exist_ok=True)

    def roots(self):
        return [("output", self.folder), ("uploads", self.uploads)]

    def resolve(self, ref: str) -> Path:
        """'output/name.ext' or 'uploads/name.ext' -> a real file inside that root, or ValueError."""
        root_name, _, name = ref.partition("/")
        roots = dict(self.roots())
        if root_name not in roots or not name or "/" in name or "\\" in name or name.startswith("."):
            raise ValueError("bad file reference")
        path = (roots[root_name] / name).resolve()
        if path.parent != roots[root_name] or not path.is_file() or path.suffix.lower() not in KINDS:
            raise ValueError("file not found")
        return path

    def listing(self):
        files = []
        for root_name, root in self.roots():
            for p in sorted(root.iterdir()) if root.is_dir() else []:
                if not p.is_file() or p.name.startswith(".") or p.suffix.lower() not in KINDS:
                    continue
                st = p.stat()
                stem = re.sub(r"[-_ ]v\d+$", "", p.stem, flags=re.I)
                m = re.search(r"[-_ ]v(\d+)$", p.stem, flags=re.I)
                ref = f"{root_name}/{p.name}"
                files.append({"ref": ref, "name": p.name, "root": root_name, "writing": ref in self.writing,
                              "editable": self.writable and p.suffix.lower() in EDITABLE,
                              "kind": KINDS[p.suffix.lower()], "ext": p.suffix.lower().lstrip("."),
                              "size": st.st_size, "mtime": st.st_mtime,
                              "group": f"{root_name}/{stem}{p.suffix.lower()}", "version": int(m.group(1)) if m else 1})
        return files

    def digest(self, path: Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()[:32]

    def to_pdf(self, path: Path) -> Path:
        """Office file -> PDF with LibreOffice, cached by content hash."""
        out = self.cache / f"{self.digest(path)}.pdf"
        if out.is_file():
            return out
        soffice = shutil.which("soffice") or shutil.which("libreoffice")
        if not soffice:
            raise RuntimeError("LibreOffice (soffice) is not installed, so this file cannot be converted for preview")
        with _convert_lock, tempfile.TemporaryDirectory(prefix="hpp-") as tmp:
            src = Path(tmp) / ("input" + path.suffix.lower())
            shutil.copyfile(path, src)
            profile = Path(tmp) / "profile"
            cmd = [soffice, f"-env:UserInstallation={profile.as_uri()}", "--headless", "--norestore",
                   "--convert-to", "pdf", "--outdir", tmp, str(src)]
            try:
                subprocess.run(cmd, capture_output=True, timeout=CONVERT_TIMEOUT, check=False)
            except subprocess.TimeoutExpired:
                raise RuntimeError(f"Conversion took longer than {CONVERT_TIMEOUT} s")
            made = Path(tmp) / "input.pdf"
            if not made.is_file() or made.stat().st_size == 0:
                raise RuntimeError("LibreOffice could not convert this file")
            shutil.move(str(made), out)
        return out

    def sheet(self, path: Path) -> dict:
        ext = path.suffix.lower()
        if ext in (".csv", ".tsv"):
            text = path.read_bytes().decode("utf-8-sig", errors="replace")
            rows = list(csv.reader(io.StringIO(text), delimiter="\t" if ext == ".tsv" else ","))
            return {"sheets": [_sheet_block(path.stem, rows)]}
        try:
            from openpyxl import load_workbook
        except ImportError:
            raise RuntimeError("openpyxl is not installed; use 'Exact layout' to view this workbook as PDF")
        values = load_workbook(path, read_only=True, data_only=True)
        formulas = load_workbook(path, read_only=True, data_only=False)
        sheets = []
        for ws, wf in list(zip(values.worksheets, formulas.worksheets))[:SHEET_MAX]:
            rows = []
            for r_val, r_f in zip(ws.iter_rows(max_col=SHEET_COLS, values_only=True),
                                  wf.iter_rows(max_col=SHEET_COLS, values_only=True)):
                rows.append([_cell(v, f) for v, f in zip(r_val, r_f)])
                if len(rows) > SHEET_ROWS:
                    break
            block = _sheet_block(ws.title, rows)
            block["total_rows"] = ws.max_row
            block["truncated"] = (ws.max_row or 0) > SHEET_ROWS or (ws.max_column or 0) > SHEET_COLS
            sheets.append(block)
        values.close(); formulas.close()
        return {"sheets": sheets, "more_sheets": len(values.sheetnames) > SHEET_MAX}

    def next_version(self, path: Path) -> Path:
        """report.md / report-v2.md -> the next free report-vN.md in the same folder."""
        stem = re.sub(r"[-_ ]v\d+$", "", path.stem, flags=re.I)
        top = 1
        for q in path.parent.iterdir():
            if q.suffix.lower() == path.suffix.lower():
                m = re.fullmatch(re.escape(stem) + r"(?:[-_ ]v(\d+))?", q.stem, flags=re.I)
                if m:
                    top = max(top, int(m.group(1) or 1))
        return path.parent / f"{stem}-v{top + 1}{path.suffix}"

    def save_text(self, ref: str, text: str) -> str:
        if not self.writable:
            raise PermissionError("This workspace is read-only")
        path = self.resolve(ref)
        if path.suffix.lower() not in EDITABLE:
            raise ValueError("This file type can't be edited in the panel; ask Hermes to change it")
        data = text.encode("utf-8")
        if len(data) > MAX_TEXT_SAVE:
            raise ValueError("Text larger than 5 MB can't be saved from the panel")
        with self._lock:
            target = self.next_version(path)
            with open(target, "xb") as f:        # never overwrite
                f.write(data)
        return f"{ref.split('/', 1)[0]}/{target.name}"

    def simulate(self) -> str:
        """Demo only: write research.md (or its next version) piece by piece, as Hermes would."""
        if not self.writable:
            raise PermissionError("This workspace is read-only")
        base = self.folder / "research.md"
        with self._lock:
            target = base if not base.exists() else self.next_version(base)
            target.write_text("", "utf-8")
        ref = f"output/{target.name}"
        version = 1 if target == base else int(re.search(r"v(\d+)$", target.stem).group(1))
        chunks = _research_chunks(version)
        self.writing.add(ref)

        def run():
            try:
                for chunk in chunks:
                    time.sleep(0.7)
                    with open(target, "a", encoding="utf-8") as f:
                        f.write(chunk)
            finally:
                self.writing.discard(ref)
        threading.Thread(target=run, daemon=True).start()
        return ref

    def save_upload(self, name: str, body: bytes) -> str:
        name = re.sub(r"[^\w.\- ()]+", "_", Path(name).name).strip(" .")[:120]
        if not name or Path(name).suffix.lower() not in KINDS:
            raise ValueError("This file type is not supported for preview")
        target = self.uploads / name
        stem, suffix, n = target.stem, target.suffix, 2
        while target.exists():
            target = self.uploads / f"{stem} ({n}){suffix}"; n += 1
        target.write_bytes(body)
        return f"uploads/{target.name}"


def _research_chunks(version):
    stamp = time.strftime("%d %b %Y, %H:%M")
    head = [f"# Research notes: launch infrastructure\n\n*Written by Hermes · {stamp} · version {version} · demo content*\n\n"]
    body = [
        "## Question\n\nWhere does India launch from today, and what is being added?\n\n",
        "## Findings\n\n",
        "- **Sriharikota** (Satish Dhawan Space Centre) is the main launch site, on the east coast.\n",
        "- It has two launch pads used by PSLV, GSLV and LVM3.\n",
        "- A second spaceport for small launchers is being built at **Kulasekarapattinam**, Tamil Nadu.\n\n",
        "## Why the east coast\n\nLaunching eastward over the sea adds the Earth's rotation to the rocket's speed "
        "and keeps spent stages away from people.\n\n",
        "## Open questions\n\n1. When will the second spaceport fly its first mission?\n"
        "2. How many launches a year can Sriharikota support?\n\n",
    ]
    if version > 1:
        body.insert(4, "- **New in this version:** a third launch pad has been approved for heavier vehicles.\n")
        body.append("> Revised after review: added the third launch pad.\n\n")
    body.append("| Site | Role |\n|---|---|\n| Sriharikota | All orbital launches today |\n| Kulasekarapattinam | Small launchers (planned) |\n")
    return head + body


def _cell(v, f):
    if v is None and isinstance(f, str) and f.startswith("="):
        return f  # formula never calculated (file not saved by a spreadsheet app): show the formula
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    if hasattr(v, "isoformat"):
        return v.isoformat(sep=" ") if hasattr(v, "hour") and (v.hour or v.minute) else v.isoformat()[:10]
    return str(v)


def _sheet_block(name, rows):
    rows = [list(map(str, r[:SHEET_COLS])) for r in rows[:SHEET_ROWS + 1]]
    while rows and not any(c.strip() for c in rows[-1]):
        rows.pop()
    width = max((max((i + 1 for i, c in enumerate(r) if c.strip()), default=0) for r in rows), default=0)
    rows = [r[:width] for r in rows]
    return {"name": str(name), "rows": rows[:SHEET_ROWS], "total_rows": len(rows),
            "truncated": len(rows) > SHEET_ROWS}


class Handler(BaseHTTPRequestHandler):
    server_version = "HermesPreview/1.0"
    ws: Workspace = None

    def log_message(self, fmt, *args):
        sys.stderr.write("%s %s\n" % (time.strftime("%H:%M:%S"), fmt % args))

    # -- helpers
    def _send(self, status, body: bytes, ctype: str, extra=None, csp=UI_CSP):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")
        if csp:
            self.send_header("Content-Security-Policy", csp)
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, obj, status=200):
        self._send(status, json.dumps(obj).encode(), "application/json; charset=utf-8")

    def _error(self, status, message):
        self._json({"error": message}, status)

    def _file(self, path: Path, *, attachment=False, ctype=None, csp=UI_CSP):
        ctype = ctype or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if ctype.startswith("text/") and "charset" not in ctype:
            ctype += "; charset=utf-8"
        disp = "attachment" if attachment else "inline"
        extra = {"Content-Disposition": f"{disp}; filename*=UTF-8''{quote(path.name)}"}
        self._send(200, path.read_bytes(), ctype, extra, csp)

    # -- routes
    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        url = urlparse(self.path)
        p = unquote(url.path)
        try:
            if p in ("/", "/index.html"):
                return self._file(STATIC / "index.html")
            if p.startswith("/static/"):
                target = (STATIC / p[len("/static/"):]).resolve()
                if STATIC not in target.parents or not target.is_file():
                    return self._error(404, "not found")
                return self._file(target)
            if p == "/api/files":
                return self._json({"files": self.ws.listing(), "release": RELEASE, "writable": self.ws.writable,
                                   "demo": getattr(self.server, "demo", False),
                                   "soffice": bool(shutil.which("soffice") or shutil.which("libreoffice"))})
            for prefix in ("/api/raw/", "/api/download/", "/api/pdf/", "/api/sheet/"):
                if p.startswith(prefix):
                    path = self.ws.resolve(p[len(prefix):])
                    kind = KINDS[path.suffix.lower()]
                    if prefix == "/api/raw/":
                        # active content (HTML, SVG) always carries the sandbox CSP, even when opened directly
                        risky = kind == "html" or path.suffix.lower() == ".svg"
                        ctype = "text/plain; charset=utf-8" if kind in ("text",) else None
                        return self._file(path, ctype=ctype, csp=CONTENT_CSP if risky else UI_CSP)
                    if prefix == "/api/download/":
                        return self._file(path, attachment=True, csp=CONTENT_CSP)
                    if prefix == "/api/pdf/":
                        if path.suffix.lower() == ".pdf":
                            return self._file(path)
                        if path.suffix.lower() not in OFFICE_TO_PDF:
                            return self._error(400, "This file type has no PDF view")
                        return self._file(self.ws.to_pdf(path), ctype="application/pdf")
                    if prefix == "/api/sheet/":
                        if kind != "sheet":
                            return self._error(400, "Not a spreadsheet")
                        return self._json(self.ws.sheet(path))
            return self._error(404, "not found")
        except ValueError as exc:
            return self._error(404, str(exc))
        except RuntimeError as exc:
            return self._error(503, str(exc))

    def _post_allowed(self):
        # same-origin only: browsers send Sec-Fetch-Site, and the custom header forces a CORS preflight
        if self.headers.get("Sec-Fetch-Site") not in (None, "same-origin") or self.headers.get("X-Hermes") != "1":
            self._error(403, "cross-site request refused")
            return False
        return True

    def _body(self, limit):
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = -1
        if length <= 0 or length > limit:
            self._error(413, f"Request must be between 1 byte and {limit // (1024 * 1024)} MB")
            return None
        return self.rfile.read(length)

    def do_POST(self):
        route = urlparse(self.path).path
        if route not in ("/api/upload", "/api/save", "/api/simulate"):
            return self._error(404, "not found")
        if not self._post_allowed():
            return
        try:
            if route == "/api/upload":
                body = self._body(MAX_UPLOAD)
                if body is None:
                    return
                return self._json({"ref": self.ws.save_upload(unquote(self.headers.get("X-Filename") or ""), body)})
            if route == "/api/save":
                body = self._body(MAX_TEXT_SAVE + 4096)
                if body is None:
                    return
                req = json.loads(body.decode("utf-8"))
                if not isinstance(req.get("ref"), str) or not isinstance(req.get("text"), str):
                    return self._error(400, "ref and text are required")
                return self._json({"ref": self.ws.save_text(req["ref"], req["text"])})
            if route == "/api/simulate":
                if not getattr(self.server, "demo", False):
                    return self._error(404, "not found")
                return self._json({"ref": self.ws.simulate()})
        except PermissionError as exc:
            return self._error(403, str(exc))
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            return self._error(400, str(exc))
        except FileExistsError:
            return self._error(409, "That version was just created; save again")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--folder", type=Path, help="folder whose files are shown (default: a fresh copy of samples/)")
    ap.add_argument("--data", type=Path, default=HERE / ".preview-data", help="uploads, demo copy and conversion cache")
    ap.add_argument("--read-only", action="store_true", help="view only: no edits saved into the folder")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    a = ap.parse_args(argv)
    demo = a.folder is None
    if demo:
        # the demo always starts from the pristine samples; edits and simulated files go to the copy
        folder = a.data / "workspace"
        shutil.rmtree(folder, ignore_errors=True)
        shutil.copytree(HERE / "samples", folder)
    else:
        folder = a.folder
        if not folder.is_dir():
            sys.exit(f"Folder not found: {folder}")
    Handler.ws = Workspace(folder, a.data, writable=not a.read_only)
    httpd = ThreadingHTTPServer((a.host, a.port), Handler)
    httpd.demo = demo
    mode = "demo copy of samples/" if demo else str(folder)
    print(f"{RELEASE}: http://{a.host}:{a.port}/  (showing {mode}{', read-only' if a.read_only else ''})", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
