// Spreadsheet viewer: the server reads .xlsx/.csv (values, formulas when never calculated); cells are shown as text only.
import { params, message, spinner, fetchOk, failure } from "./common.js";
const $ = (id) => document.getElementById(id);
const p = params(); const main = $("main");
let book = null, current = 0;
const editing = /(?:^#|&)edit=1(?:&|$)/.test(location.hash) && /\.(csv|tsv)$/i.test(p.src);
const fileRef = decodeURIComponent((location.hash.match(/(?:^#|&)ref=([^&]+)/) || [, ""])[1]);
let original = "", wasDirty = false, curRow = null;
const post = (m) => window.parent.postMessage(m, location.origin);
const col = (i) => { let s = ""; i++; while (i) { const m = (i - 1) % 26; s = String.fromCharCode(65 + m) + s; i = Math.floor((i - 1) / 26); } return s; };
function draw() {
  const sh = book.sheets[current]; const q = $("filter").value.trim().toLowerCase();
  const width = Math.max(1, ...sh.rows.map((r) => r.length));
  const grid = $("grid"); grid.replaceChildren();
  const head = grid.createTHead().insertRow(); const c0 = document.createElement("th"); c0.className = "rn"; head.append(c0);
  for (let i = 0; i < width; i++) { const th = document.createElement("th"); th.textContent = col(i); head.append(th); }
  const body = grid.createTBody(); let shown = 0;
  sh.rows.forEach((row, ri) => {
    if (q && ri > 0 && !row.some((c) => c.toLowerCase().includes(q))) return;
    const tr = body.insertRow(); const rn = tr.insertCell(); rn.className = "rn"; rn.textContent = ri + 1;
    for (let i = 0; i < width; i++) {
      const td = tr.insertCell(); const v = row[i] ?? ""; td.textContent = v; td.title = v;
      if (editing) { td.contentEditable = "plaintext-only"; td.dataset.r = ri; td.dataset.c = i; }
      if (/^-?[\d,]+(\.\d+)?%?$/.test(v)) td.className = "n"; if (v.startsWith("=")) td.className = "f";
    }
    if (ri > 0) shown++;
  });
  $("info").innerHTML = "";
  const t = document.createElement("span"); t.textContent = `${sh.name} · ${Math.max(0, sh.rows.length - 1)} rows × ${width} columns` + (q ? ` · ${shown} match` : "");
  $("info").append(t);
  if (sh.truncated) { const n = document.createElement("span"); n.className = "note"; n.textContent = ` · showing the first ${sh.rows.length} rows of ${sh.total_rows}; download for the full sheet`; $("info").append(n); }
  document.querySelectorAll(".sheets button").forEach((b, i) => b.classList.toggle("on", i === current));
}
$("filter").oninput = () => book && draw();

// ---- CSV editing (saved as a new version by the server; the original file is never overwritten)
function rowsFromGrid() {
  const rows = book.sheets[0].rows;
  document.querySelectorAll("td[data-r]").forEach((td) => { const r = +td.dataset.r, c = +td.dataset.c; (rows[r] ||= [])[c] = td.textContent.replace(/\n+$/, ""); });
  return rows;
}
const sep = () => /\.tsv$/i.test(p.src) ? "\t" : ",";
function toCsv(rows) {
  const s = sep();
  return rows.map((r) => r.map((v = "") => (s === "," && /[",\n\r]/.test(v)) || (s === "\t" && /[\t\n"]/.test(v)) ? `"${String(v).replace(/"/g, '""')}"` : v).join(s)).join("\r\n") + "\r\n";
}
function checkDirty() {
  const d = toCsv(rowsFromGrid()) !== original;
  $("save").disabled = !d;
  if (d !== wasDirty) { wasDirty = d; post({ type: "dirty", dirty: d }); }
  $("info").querySelector(".dirty")?.remove();
  if (d) { const s = document.createElement("span"); s.className = "dirty"; s.textContent = " · unsaved changes"; $("info").append(s); }
}
async function saveCsv() {
  if ($("save").disabled) return;
  $("save").disabled = true; $("save").textContent = "Saving…";
  try {
    const r = await fetch("/api/save", { method: "POST", headers: { "Content-Type": "application/json", "X-Hermes": "1" },
      body: JSON.stringify({ ref: fileRef, text: toCsv(rowsFromGrid()) }) });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(data.error || `The server answered ${r.status}`);
    wasDirty = false; post({ type: "saved", ref: data.ref });
  } catch (err) { alert("Not saved: " + err.message); $("save").disabled = false; }
  finally { $("save").textContent = "Save as new version"; }
}
if (editing) {
  document.body.classList.add("editing"); $("edit-tools").hidden = false; $("filter").hidden = true;
  $("grid").addEventListener("input", checkDirty);
  $("grid").addEventListener("focusin", (e) => { const td = e.target.closest("td[data-r]"); if (!td) return;
    document.querySelectorAll("tr.cur").forEach((t) => t.classList.remove("cur")); td.parentElement.classList.add("cur"); curRow = +td.dataset.r; });
  $("grid").addEventListener("keydown", (e) => {
    const td = e.target.closest("td[data-r]"); if (!td) return;
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); document.querySelector(`td[data-r="${+td.dataset.r + 1}"][data-c="${td.dataset.c}"]`)?.focus(); }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") { e.preventDefault(); saveCsv(); }
  });
  $("save").onclick = saveCsv;
  $("addrow").onclick = () => { const rows = rowsFromGrid(); rows.push(new Array(rows[0]?.length || 1).fill("")); draw(); checkDirty();
    document.querySelector(`td[data-r="${rows.length - 1}"][data-c="0"]`)?.focus(); };
  $("delrow").onclick = () => { if (curRow == null || curRow === 0) return alert("Click a cell in the row to delete (the header row stays)");
    const rows = rowsFromGrid(); rows.splice(curRow, 1); curRow = null; draw(); checkDirty(); };
  $("addcol").onclick = () => { const rows = rowsFromGrid(); rows.forEach((r, i) => r.push(i === 0 ? `Column ${r.length + 1}` : "")); draw(); checkDirty(); };
  $("cancel").onclick = () => { if (!wasDirty || confirm("Stop editing and lose your edits?")) post({ type: "cancel" }); };
}
message(main, spinner("Reading spreadsheet…"));
try {
  if (!p.src) throw new Error("No file was given");
  book = await (await fetchOk(p.src)).json();
  if (!book.sheets?.length) throw new Error("The workbook has no sheets");
  book.sheets.forEach((s, i) => { const b = document.createElement("button"); b.textContent = s.name; b.onclick = () => { current = i; draw(); }; $("sheets").append(b); });
  $("sheets").hidden = book.sheets.length < 2 && !/\.xls/i.test(p.src);
  if (editing && book.sheets[0].truncated) throw new Error("This table is too large to edit in the panel; ask Hermes to change it, or download it");
  if (editing) { const w = Math.max(...book.sheets[0].rows.map((r) => r.length)); book.sheets[0].rows.forEach((r) => { while (r.length < w) r.push(""); });
    original = toCsv(book.sheets[0].rows); }
  draw(); message(main, null);
  if (editing) { checkDirty(); document.querySelector('td[data-r="1"][data-c="0"]')?.focus(); }
} catch (err) { failure(main, err); }
