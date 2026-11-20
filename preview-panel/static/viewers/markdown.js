// Markdown viewer: marked renders, DOMPurify removes anything executable before it reaches the page.
import { params, message, spinner, fetchOk, failure } from "./common.js";
const p = params(); const main = document.getElementById("main");
const scroller = document.querySelector(".scroll");
async function load() {
  const text = await (await fetchOk(p.src)).text();
  const html = window.marked.parse(text, { gfm: true, breaks: false });
  document.getElementById("out").innerHTML = window.DOMPurify.sanitize(html, { USE_PROFILES: { html: true } });
  document.querySelectorAll("#out a[href]").forEach((a) => { a.target = "_blank"; a.rel = "noopener noreferrer"; });
}
// the panel asks for a refresh when the file grows (Hermes still writing) or changes
window.addEventListener("message", async (e) => {
  if (e.origin !== location.origin || e.source !== window.parent || e.data?.type !== "refresh") return;
  const atEnd = scroller.scrollTop + scroller.clientHeight >= scroller.scrollHeight - 40;
  const keep = scroller.scrollTop;
  try { await load(); } catch (_) { return; }
  scroller.scrollTop = e.data.follow || atEnd ? scroller.scrollHeight : keep;
});
message(main, spinner("Opening…"));
try {
  if (!p.src) throw new Error("No file was given");
  await load(); message(main, null);
} catch (err) { failure(main, err); }
