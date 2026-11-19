// Markdown viewer: marked renders, DOMPurify removes anything executable before it reaches the page.
import { params, message, spinner, fetchOk, failure } from "./common.js";
const p = params(); const main = document.getElementById("main");
message(main, spinner("Opening…"));
try {
  if (!p.src) throw new Error("No file was given");
  const text = await (await fetchOk(p.src)).text();
  const html = window.marked.parse(text, { gfm: true, breaks: false });
  document.getElementById("out").innerHTML = window.DOMPurify.sanitize(html, { USE_PROFILES: { html: true } });
  document.querySelectorAll("#out a[href]").forEach((a) => { a.target = "_blank"; a.rel = "noopener noreferrer"; });
  message(main, null);
} catch (err) { failure(main, err); }
