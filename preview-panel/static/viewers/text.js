// Plain text / source viewer: text only (textContent), never interpreted.
import { params, message, spinner, fetchOk, failure } from "./common.js";
const $ = (id) => document.getElementById(id);
const p = params(); const main = $("main"); const LIMIT = 2_000_000;
$("wrap").onclick = () => { document.body.classList.toggle("wrap"); $("wrap").classList.toggle("on"); };
message(main, spinner("Opening…"));
try {
  if (!p.src) throw new Error("No file was given");
  let text = await (await fetchOk(p.src)).text();
  const cut = text.length > LIMIT; if (cut) text = text.slice(0, LIMIT);
  if (p.lang === "html") text = text.replace(/url\(data:[^)]{200,}\)/g, "url(data:…embedded…)").replace(/(src|href)="data:[^"]{200,}"/g, '$1="data:…embedded…"');
  const lines = text.split("\n");
  $("tx").textContent = text;
  $("ln").textContent = lines.map((_, i) => i + 1).join("\n");
  $("info").textContent = `${p.lang === "html" ? "Page source (embedded fonts and images shortened)" : "Text"} · ${lines.length.toLocaleString()} lines${cut ? " · first 2 MB" : ""}`;
  if (p.lang === "html" || p.lang === "md") { document.body.classList.add("wrap"); $("wrap").classList.add("on"); }
  message(main, null);
} catch (err) { failure(main, err); }
