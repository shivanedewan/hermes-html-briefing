// Line-by-line changes between a file and its previous version (Myers diff), text only.
import { params, message, spinner, fetchOk, failure } from "./common.js";
const $ = (id) => document.getElementById(id);
const p = params(); const main = $("main");
const old = (location.hash.match(/(?:^#|&)old=([^&]+)/) || [])[1];
const oldSrc = old && /^\/api\/raw\//.test(decodeURIComponent(old)) ? decodeURIComponent(old) : "";
const label = (k) => decodeURIComponent((location.hash.match(new RegExp(`(?:^#|&)${k}=([^&]+)`)) || [, ""])[1]);
let whole = false, ops = [];

function diff(a, b) {
  const n = a.length, m = b.length, max = n + m, v = new Map([[1, 0]]), trace = [];
  for (let d = 0; d <= max; d++) {
    trace.push(new Map(v));
    for (let k = -d; k <= d; k += 2) {
      let x = (k === -d || (k !== d && (v.get(k - 1) ?? -1) < (v.get(k + 1) ?? -1))) ? v.get(k + 1) ?? 0 : (v.get(k - 1) ?? 0) + 1;
      let y = x - k;
      while (x < n && y < m && a[x] === b[y]) { x++; y++; }
      v.set(k, x);
      if (x >= n && y >= m) return backtrack(trace, a, b, d);
    }
  }
  return [];
}
function backtrack(trace, a, b, dEnd) {
  const out = []; let x = a.length, y = b.length;
  for (let d = dEnd; d > 0; d--) {
    const v = trace[d]; const k = x - y;
    const prevK = (k === -d || (k !== d && (v.get(k - 1) ?? -1) < (v.get(k + 1) ?? -1))) ? k + 1 : k - 1;
    const px = v.get(prevK) ?? 0, py = px - prevK;
    while (x > px && y > py) { out.push(["=", a[x - 1], x, y]); x--; y--; }
    if (x === px) out.push(["+", b[y - 1], null, y]); else out.push(["-", a[x - 1], x, null]);
    x = px; y = py;
  }
  while (x > 0 && y > 0) { out.push(["=", a[x - 1], x, y]); x--; y--; }
  return out.reverse();
}

function draw() {
  const box = $("out"); box.replaceChildren();
  const near = new Set();
  ops.forEach((o, i) => { if (o[0] !== "=") for (let j = i - 3; j <= i + 3; j++) near.add(j); });
  let skipped = 0;
  const flush = () => { if (skipped) { const g = document.createElement("span"); g.className = "gap"; g.textContent = `… ${skipped} unchanged line${skipped > 1 ? "s" : ""}`; box.append(g); skipped = 0; } };
  ops.forEach((o, i) => {
    if (!whole && o[0] === "=" && !near.has(i)) { skipped++; return; }
    flush();
    const r = document.createElement("div"); r.className = "r" + (o[0] === "+" ? " add" : o[0] === "-" ? " del" : "");
    const a = document.createElement("span"); a.className = "n"; a.textContent = o[2] ?? "";
    const b = document.createElement("span"); b.className = "n"; b.textContent = o[3] ?? "";
    const m = document.createElement("span"); m.className = "m"; m.textContent = o[0] === "=" ? "" : o[0] === "+" ? "+" : "−";
    const t = document.createElement("span"); t.textContent = o[1];
    r.append(a, b, m, t); box.append(r);
  });
  flush();
}
$("all").onclick = () => { whole = !whole; $("all").textContent = whole ? "Show changes only" : "Show whole file"; draw(); };

message(main, spinner("Comparing versions…"));
try {
  if (!p.src || !oldSrc) throw new Error("Two versions are needed to show changes");
  const [a, b] = await Promise.all([fetchOk(oldSrc).then((r) => r.text()), fetchOk(p.src).then((r) => r.text())]);
  ops = diff(a.split("\n"), b.split("\n"));
  const plus = ops.filter((o) => o[0] === "+").length, minus = ops.filter((o) => o[0] === "-").length;
  const info = $("info"); info.textContent = `${label("a")} → ${label("b")}  `;
  const ps = document.createElement("span"); ps.className = "plus"; ps.textContent = `+${plus} `;
  const ms = document.createElement("span"); ms.className = "minus"; ms.textContent = `−${minus}`;
  info.append(ps, ms, plus + minus ? "" : " · no differences");
  draw(); message(main, null);
} catch (err) { failure(main, err); }
