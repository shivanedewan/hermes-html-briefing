# Third-party notices

All viewers are bundled in `static/vendor/` and load nothing from the internet.

| Component | Version | Files | Licence |
|---|---|---|---|
| pdf.js (Mozilla) | 6.2.108 (pdfjs-dist) | `static/vendor/pdfjs/` | Apache-2.0 — `static/vendor/pdfjs/LICENSE` |
| docx-preview (docxjs, V. Baydalka) | 0.4.1 | `static/vendor/docx-preview/` | Apache-2.0 — `static/vendor/docx-preview/LICENSE` |
| JSZip | 3.10.1 | `static/vendor/jszip/` | MIT or GPLv3 (dual); used under MIT — `static/vendor/jszip/LICENSE.md` |
| marked | 18.0.10 | `static/vendor/marked/` | MIT — `static/vendor/marked/LICENSE` |
| DOMPurify | 3.4.14 | `static/vendor/dompurify/` | Apache-2.0 or MPL-2.0 (dual); used under Apache-2.0 — `static/vendor/dompurify/LICENSE` |

Optional runtime tools, not included: LibreOffice (MPL-2.0) for Office → PDF conversion,
openpyxl (MIT) for reading Excel files. Both are already part of the Hermes VM.

The sample files in `samples/` were produced for this demo (python-docx, openpyxl, PptxGenJS,
and the hermes-html-briefing prototype). The map is derived from Natural Earth (public domain).
The rest of the code (`server.py`, `static/*.js|css|html`, `tools/`, `tests/`) was written for Hermes.
