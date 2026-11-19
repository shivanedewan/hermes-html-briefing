// Word (.docx) viewer: docx-preview (Apache-2.0) renders the document as HTML pages in the browser.
import { params, message, spinner, fetchOk, failure } from "./common.js";
const $ = (id) => document.getElementById(id);
const p = params(); const main = $("main"); const doc = $("doc");
let zoom = 1;
function apply() { doc.style.zoom = zoom; $("zl").textContent = `${Math.round(zoom * 100)}%`; }
function fitWidth() {
  const page = doc.querySelector("section.docx"); if (!page) return;
  const w = page.getBoundingClientRect().width / zoom;
  zoom = Math.min(1.6, Math.max(0.4, ($("scroll").clientWidth - 36) / w)); apply();
}
$("zin").onclick = () => { zoom = Math.min(3, zoom + 0.1); apply(); };
$("zout").onclick = () => { zoom = Math.max(0.3, zoom - 0.1); apply(); };
$("fit").onclick = fitWidth;
message(main, spinner("Opening document…"));
try {
  if (!p.src) throw new Error("No file was given");
  const blob = await (await fetchOk(p.src)).blob();
  await window.docx.renderAsync(blob, doc, null, { className: "docx", inWrapper: true, breakPages: true,
    ignoreLastRenderedPageBreak: true, renderHeaders: true, renderFooters: true, renderFootnotes: true,
    renderEndnotes: true, useBase64URL: true, experimental: true });
  // documents never run script; drop anything executable that a crafted file might smuggle in
  doc.querySelectorAll("script,iframe,object,embed").forEach((n) => n.remove());
  doc.querySelectorAll("a[href]").forEach((a) => { if (!/^(https?:|mailto:|#)/i.test(a.getAttribute("href"))) a.removeAttribute("href"); else { a.target = "_blank"; a.rel = "noopener noreferrer"; } });
  // Word bullets use the Symbol font's private-use glyphs, which browsers lack: show real bullets instead
  doc.parentElement.querySelectorAll("style").forEach((st) => {
    st.textContent = st.textContent.replace(/content:\s*"([^"]*)"/g, (m, c) => /[\uf000-\uf0ff]|\\f0[0-9a-f]{2}/i.test(c) ? 'content: "\u2022\t"' : m)
      .replace(/font-family:\s*"?Symbol"?/gi, "font-family: inherit");
  });
  const n = doc.querySelectorAll("section.docx").length;
  $("pages").textContent = `Word document · ${n} page${n === 1 ? "" : "s"} (layout approximate; use Exact layout for print fidelity)`;
  message(main, null);
  if ($("scroll").clientWidth < 900) fitWidth();
} catch (err) { failure(main, err); }
