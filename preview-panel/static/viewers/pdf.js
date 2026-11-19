// PDF / slides viewer built on Mozilla pdf.js (vendored, offline).
import * as pdfjsLib from "../vendor/pdfjs/pdf.min.mjs";
import { params, message, spinner, fetchOk, failure } from "./common.js";

globalThis.pdfjsLib = pdfjsLib;
const { EventBus, PDFLinkService, PDFFindController, PDFViewer } = await import("../vendor/pdfjs/pdf_viewer.mjs");
pdfjsLib.GlobalWorkerOptions.workerSrc = new URL("../vendor/pdfjs/pdf.worker.min.mjs", import.meta.url).href;

const $ = (id) => document.getElementById(id);
const p = params();
const slides = p.mode === "slides";
const main = $("main");
document.body.classList.toggle("slides", slides);
document.body.classList.toggle("show-thumbs", slides && innerWidth > 700);
$("present").hidden = !slides;

const eventBus = new EventBus();
const linkService = new PDFLinkService({ eventBus, externalLinkTarget: 2 /* blank */ });
const findController = new PDFFindController({ eventBus, linkService });
const container = $("viewerContainer");
const viewer = new PDFViewer({ container, viewer: $("viewer"), eventBus, linkService, findController,
  removePageBorders: true, textLayerMode: 1, annotationMode: pdfjsLib.AnnotationMode.ENABLE });
linkService.setViewer(viewer);

eventBus.on("pagesinit", () => { viewer.currentScaleValue = slides ? "page-fit" : "page-width"; $("zoom").value = viewer.currentScaleValue; });
eventBus.on("pagechanging", (e) => { $("page").value = e.pageNumber; markThumb(e.pageNumber); });
eventBus.on("scalechanging", (e) => {
  const sel = $("zoom"); const v = e.presetValue || String(+e.scale.toFixed(2));
  if (![...sel.options].some((o) => o.value === v)) { const o = sel.querySelector("option[data-custom]") || sel.appendChild(Object.assign(document.createElement("option"), { dataset: { custom: 1 } })); o.dataset.custom = "1"; o.value = v; o.textContent = `${Math.round(e.scale * 100)}%`; }
  sel.value = v;
});

$("prev").onclick = () => viewer.previousPage();
$("next").onclick = () => viewer.nextPage();
$("page").onchange = (e) => { const n = parseInt(e.target.value, 10); if (n >= 1 && n <= viewer.pagesCount) viewer.currentPageNumber = n; };
$("zoom").onchange = (e) => { viewer.currentScaleValue = e.target.value; };
$("zin").onclick = () => viewer.increaseScale();
$("zout").onclick = () => viewer.decreaseScale();
$("thumbs-btn").onclick = () => document.body.classList.toggle("show-thumbs");
$("find").addEventListener("input", (e) => eventBus.dispatch("find", { source: null, type: "", query: e.target.value, caseSensitive: false,
  entireWord: false, highlightAll: true, findPrevious: false, matchDiacritics: false }));
$("find").addEventListener("keydown", (e) => { if (e.key === "Enter") eventBus.dispatch("find", { source: null, type: "again", query: e.target.value,
  caseSensitive: false, entireWord: false, highlightAll: true, findPrevious: e.shiftKey, matchDiacritics: false }); });
$("present").onclick = () => { document.querySelector(".docwrap").requestFullscreen?.(); };
addEventListener("resize", () => { const v = viewer.currentScaleValue; if (/^page-/.test(v)) viewer.currentScaleValue = v; if (innerWidth <= 700) document.body.classList.remove("show-thumbs"); });
document.addEventListener("fullscreenchange", () => setTimeout(() => { viewer.currentScaleValue = "page-fit"; }, 60));
document.addEventListener("keydown", (e) => {
  if (e.target.matches("input,select")) return;
  if (e.key === "ArrowRight" || e.key === "PageDown" || (slides && e.key === " ")) { viewer.nextPage(); e.preventDefault(); }
  if (e.key === "ArrowLeft" || e.key === "PageUp") { viewer.previousPage(); e.preventDefault(); }
});

// thumbnails, drawn lazily as they scroll into view
function buildThumbs(doc) {
  const box = $("thumbs"); box.replaceChildren();
  const io = new IntersectionObserver((entries) => entries.forEach(async (en) => {
    if (!en.isIntersecting) return; io.unobserve(en.target);
    const n = +en.target.dataset.page; const page = await doc.getPage(n);
    const vp1 = page.getViewport({ scale: 1 }); const scale = 300 / vp1.width; const vp = page.getViewport({ scale });
    const c = document.createElement("canvas"); c.width = vp.width; c.height = vp.height;
    await page.render({ canvasContext: c.getContext("2d"), viewport: vp }).promise;
    en.target.querySelector(".ph").replaceWith(c);
  }), { root: box, rootMargin: "300px" });
  for (let n = 1; n <= doc.numPages; n++) {
    const b = document.createElement("button"); b.className = "thumb"; b.dataset.page = n;
    const ph = document.createElement("div"); ph.className = "ph"; ph.style.aspectRatio = slides ? "16/9" : "1/1.414";
    b.append(ph, document.createTextNode(String(n)));
    b.onclick = () => { viewer.currentPageNumber = n; };
    box.append(b); io.observe(b);
  }
  markThumb(1);
}
function markThumb(n) {
  document.querySelectorAll(".thumb").forEach((t) => t.classList.toggle("on", +t.dataset.page === n));
  document.querySelector(`.thumb[data-page="${n}"]`)?.scrollIntoView({ block: "nearest" });
}

message(main, spinner(slides ? "Preparing slides…" : "Opening document…"));
try {
  if (!p.src) throw new Error("No file was given");
  const data = await (await fetchOk(p.src)).arrayBuffer();
  const base = new URL("../vendor/pdfjs/", import.meta.url).href;
  const doc = await pdfjsLib.getDocument({ data, cMapUrl: base + "cmaps/", cMapPacked: true,
    standardFontDataUrl: base + "standard_fonts/", wasmUrl: base + "wasm/", isEvalSupported: false }).promise;
  viewer.setDocument(doc); linkService.setDocument(doc);
  $("count").textContent = `/ ${doc.numPages}`;
  buildThumbs(doc);
  message(main, null);
} catch (err) {
  failure(main, err);
}
