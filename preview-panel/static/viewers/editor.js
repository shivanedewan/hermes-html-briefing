// Text editor for Markdown, text, JSON and CSV source. Saving never overwrites: the server writes the next version.
import { params, message, spinner, fetchOk, failure } from "./common.js";
const $ = (id) => document.getElementById(id);
const p = params(); const main = $("main"); const ed = $("ed");
const ref = (location.hash.match(/(?:^#|&)ref=([^&]+)/) || [])[1];
const fileRef = ref ? decodeURIComponent(ref) : "";
const md = p.lang === "md";
let original = "", saving = false;

const post = (m) => window.parent.postMessage(m, location.origin);
const dirty = () => ed.value !== original;
let wasDirty = false;

function status() {
  const d = dirty(); const s = $("status");
  s.className = "lbl" + (d ? " dirty" : "");
  s.textContent = d ? "Unsaved changes" : "No changes";
  if (d && p.lang === "json") { try { JSON.parse(ed.value); } catch (e) { s.className = "lbl err"; s.textContent = "JSON is not valid: " + e.message.slice(0, 80); } }
  $("save").disabled = !d || saving; $("revert").disabled = !d;
  if (d !== wasDirty) { wasDirty = d; post({ type: "dirty", dirty: d }); }
  const upto = ed.value.slice(0, ed.selectionStart); const line = upto.split("\n").length;
  $("pos").textContent = `Line ${line}, column ${upto.length - upto.lastIndexOf("\n")} · ${ed.value.length.toLocaleString()} characters`;
  if (md && !$("pv").hidden) render();
}
let timer = 0;
function render() { clearTimeout(timer); timer = setTimeout(() => {
  $("pv").innerHTML = window.DOMPurify.sanitize(window.marked.parse(ed.value, { gfm: true }), { USE_PROFILES: { html: true } });
  $("pv").querySelectorAll("a[href]").forEach((a) => { a.target = "_blank"; a.rel = "noopener noreferrer"; });
}, 120); }

async function save() {
  if (!dirty() || saving) return;
  saving = true; $("save").textContent = "Saving…"; status();
  try {
    const r = await fetch("/api/save", { method: "POST", headers: { "Content-Type": "application/json", "X-Hermes": "1" },
      body: JSON.stringify({ ref: fileRef, text: ed.value }) });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(data.error || `The server answered ${r.status}`);
    original = ed.value; wasDirty = false;
    post({ type: "saved", ref: data.ref });
  } catch (err) {
    $("status").className = "lbl err"; $("status").textContent = "Not saved: " + err.message;
  } finally { saving = false; $("save").textContent = "Save as new version"; $("save").disabled = !dirty(); }
}

ed.addEventListener("input", status);
ed.addEventListener("keyup", status); ed.addEventListener("click", status);
ed.addEventListener("keydown", (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") { e.preventDefault(); save(); }
  if (e.key === "Tab" && !e.shiftKey) { e.preventDefault(); document.execCommand("insertText", false, "  "); }
});
$("save").onclick = save;
$("revert").onclick = () => { if (confirm("Undo all your edits?")) { ed.value = original; status(); ed.focus(); } };
$("cancel").onclick = () => { if (!dirty() || confirm("Stop editing and lose your edits?")) post({ type: "cancel" }); };
$("preview").hidden = !md;
$("preview").onclick = () => { const on = $("pv").hidden; $("pv").hidden = !on; $("edwrap").classList.toggle("split", on); $("preview").classList.toggle("on", on); if (on) render(); };

message(main, spinner("Opening for editing…"));
try {
  if (!p.src || !fileRef) throw new Error("No file was given");
  original = await (await fetchOk(p.src)).text();
  ed.value = original; message(main, null); status();
  if (md && innerWidth > 760) $("preview").click();
  ed.focus(); ed.setSelectionRange(0, 0);
} catch (err) { failure(main, err); }
