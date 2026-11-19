// Spreadsheet viewer: the server reads .xlsx/.csv (values, formulas when never calculated); cells are shown as text only.
import { params, message, spinner, fetchOk, failure } from "./common.js";
const $ = (id) => document.getElementById(id);
const p = params(); const main = $("main");
let book = null, current = 0;
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
message(main, spinner("Reading spreadsheet…"));
try {
  if (!p.src) throw new Error("No file was given");
  book = await (await fetchOk(p.src)).json();
  if (!book.sheets?.length) throw new Error("The workbook has no sheets");
  book.sheets.forEach((s, i) => { const b = document.createElement("button"); b.textContent = s.name; b.onclick = () => { current = i; draw(); }; $("sheets").append(b); });
  $("sheets").hidden = book.sheets.length < 2 && !/\.xls/i.test(p.src);
  draw(); message(main, null);
} catch (err) { failure(main, err); }
