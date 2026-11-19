// Hermes preview panel (demo): chat on the left, Claude-style file panel on the right.
const $ = (id) => document.getElementById(id);
const state = { files: [], tabs: [], active: null, mode: {} };
const KIND_LABEL = { html: "HTML", pdf: "PDF", docx: "DOCX", office: "DOC", slides: "PPTX", sheet: "XLSX", image: "IMG", markdown: "MD", text: "TXT" };
const KIND_NAME = { html: "Web page", pdf: "PDF document", docx: "Word document", office: "Document", slides: "Presentation",
  sheet: "Spreadsheet", image: "Image", markdown: "Markdown", text: "Text" };
const MODES = {
  docx: [["doc", "Document"], ["exact", "Exact layout"]],
  html: [["page", "Page"], ["source", "Source"]],
  markdown: [["md", "Formatted"], ["source", "Source"]],
};

function icon(file, cls = "ci") {
  const s = document.createElement("span");
  s.className = `${cls} ${file.kind}`;
  s.textContent = file.ext === "csv" ? "CSV" : file.ext === "pdf" ? "PDF" : (KIND_LABEL[file.kind] || file.ext.toUpperCase());
  return s;
}
const size = (n) => n < 1024 ? `${n} B` : n < 1048576 ? `${(n / 1024).toFixed(0)} KB` : `${(n / 1048576).toFixed(1)} MB`;
const enc = (ref) => ref.split("/").map(encodeURIComponent).join("/");
function toast(text) { const t = $("toast"); t.textContent = text; t.classList.add("show"); clearTimeout(toast.t); toast.t = setTimeout(() => t.classList.remove("show"), 2600); }

function group(file) { return state.files.filter((f) => f.group === file.group).sort((a, b) => a.version - b.version); }
function latest(groupKey) { const g = state.files.filter((f) => f.group === groupKey); return g.sort((a, b) => b.version - a.version)[0]; }

async function load() {
  const r = await fetch("/api/files");
  const data = await r.json();
  state.files = data.files;
  state.soffice = data.soffice;
  renderCards(); renderList();
}

function renderCards() {
  const box = $("cards"); box.replaceChildren();
  const seen = new Set();
  const order = ["html", "slides", "docx", "pdf", "sheet"];
  const picks = state.files.filter((f) => f.root === "output" && order.includes(f.kind) && f.ext !== "csv")
    .sort((a, b) => order.indexOf(a.kind) - order.indexOf(b.kind));
  for (const f of picks) {
    if (seen.has(f.group)) continue; seen.add(f.group);
    const top = latest(f.group); const n = group(top).length;
    const b = document.createElement("button"); b.className = "card"; b.dataset.group = top.group;
    const t = document.createElement("div");
    const name = document.createElement("div"); name.className = "cn"; name.textContent = top.name;
    const meta = document.createElement("div"); meta.className = "cm"; meta.textContent = `${KIND_NAME[top.kind]} · ${size(top.size)}${n > 1 ? ` · ${n} versions` : ""}`;
    t.append(name, meta); b.append(icon(top), t);
    b.onclick = () => open(top.ref);
    box.append(b);
  }
}

function renderList() {
  const box = $("filelist"); box.replaceChildren();
  for (const f of [...state.files].sort((a, b) => (a.root === b.root ? a.name.localeCompare(b.name) : a.root === "uploads" ? -1 : 1))) {
    const row = document.createElement("div"); row.className = "frow"; row.tabIndex = 0;
    const name = document.createElement("div"); name.textContent = f.name;
    const badge = document.createElement("span"); badge.className = "badge"; badge.textContent = f.root === "uploads" ? "your file" : KIND_NAME[f.kind];
    const sz = document.createElement("small"); sz.textContent = size(f.size);
    row.append(icon(f), name, badge, sz);
    row.onclick = () => open(f.ref);
    row.onkeydown = (e) => { if (e.key === "Enter") open(f.ref); };
    box.append(row);
  }
}

function open(ref) {
  const file = state.files.find((f) => f.ref === ref); if (!file) return;
  const i = state.tabs.findIndex((t) => state.files.find((f) => f.ref === t)?.group === file.group);
  if (i >= 0) state.tabs[i] = ref; else state.tabs.push(ref);
  state.active = ref;
  document.body.classList.add("has-panel"); $("panel").hidden = false;
  renderTabs(); renderActive();
}

function closeTab(ref) {
  const i = state.tabs.indexOf(ref); if (i < 0) return;
  state.tabs.splice(i, 1);
  if (state.active === ref) state.active = state.tabs[Math.max(0, i - 1)] || null;
  if (!state.active) return closePanel();
  renderTabs(); renderActive();
}

function closePanel() {
  state.tabs = []; state.active = null; $("stage").replaceChildren();
  $("panel").hidden = true; document.body.classList.remove("has-panel", "full"); $("app").classList.remove("full");
  document.querySelectorAll(".card.active").forEach((c) => c.classList.remove("active"));
}

function renderTabs() {
  const box = $("tabs"); box.replaceChildren();
  for (const ref of state.tabs) {
    const f = state.files.find((x) => x.ref === ref);
    const b = document.createElement("div"); b.className = "tab" + (ref === state.active ? " on" : ""); b.setAttribute("role", "tab");
    b.setAttribute("aria-selected", ref === state.active); b.tabIndex = 0;
    const dot = document.createElement("i"); dot.className = `ci ${f.kind}`;
    const name = document.createElement("span"); name.textContent = f.name;
    const x = document.createElement("button"); x.className = "x"; x.title = "Close tab";
    x.innerHTML = '<svg viewBox="0 0 24 24"><path d="M6 6l12 12M18 6 6 18"/></svg>';
    x.onclick = (e) => { e.stopPropagation(); closeTab(ref); };
    b.append(dot, name, x);
    b.onclick = () => { state.active = ref; renderTabs(); renderActive(); };
    b.onkeydown = (e) => { if (e.key === "Enter") b.onclick(); };
    box.append(b);
  }
  document.querySelectorAll(".card").forEach((c) => c.classList.toggle("active", state.files.find((f) => f.ref === state.active)?.group === c.dataset.group));
}

function viewerUrl(f, mode) {
  const e = enc(f.ref);
  switch (f.kind) {
    case "html": return mode === "source" ? `/static/viewers/text.html#src=/api/raw/${e}&lang=html` : `/api/raw/${e}`;
    case "pdf": return `/static/viewers/pdf.html#src=/api/pdf/${e}&mode=doc`;
    case "slides": return `/static/viewers/pdf.html#src=/api/pdf/${e}&mode=slides`;
    case "office": return `/static/viewers/pdf.html#src=/api/pdf/${e}&mode=doc`;
    case "docx": return mode === "exact" ? `/static/viewers/pdf.html#src=/api/pdf/${e}&mode=doc` : `/static/viewers/docx.html#src=/api/raw/${e}`;
    case "sheet": return `/static/viewers/sheet.html#src=/api/sheet/${e}`;
    case "image": return `/static/viewers/image.html#src=/api/raw/${e}`;
    case "markdown": return mode === "source" ? `/static/viewers/text.html#src=/api/raw/${e}&lang=md` : `/static/viewers/markdown.html#src=/api/raw/${e}`;
    default: return `/static/viewers/text.html#src=/api/raw/${e}`;
  }
}

function renderActive() {
  const f = state.files.find((x) => x.ref === state.active); if (!f) return;
  const modes = MODES[f.kind];
  const mode = state.mode[f.group] || (modes ? modes[0][0] : "");
  $("kind-icon").replaceChildren(icon(f));
  $("fname").textContent = f.name;
  const versions = group(f);
  $("fmeta").textContent = `${KIND_NAME[f.kind]} · ${size(f.size)} · ${new Date(f.mtime * 1000).toLocaleString()}` +
    (f.root === "uploads" ? " · your file" : "");
  const vs = $("version"); vs.replaceChildren(); vs.hidden = versions.length < 2;
  for (const v of versions) { const o = document.createElement("option"); o.value = v.ref; o.textContent = `Version ${v.version}${v === versions.at(-1) ? " (latest)" : ""}`; o.selected = v.ref === f.ref; vs.append(o); }
  const seg = $("modes"); seg.replaceChildren(); seg.hidden = !modes;
  for (const [key, label] of modes || []) {
    if (key === "exact" && !state.soffice) continue;
    const b = document.createElement("button"); b.textContent = label; b.className = key === mode ? "on" : "";
    b.onclick = () => { state.mode[f.group] = key; renderActive(); };
    seg.append(b);
  }
  const url = viewerUrl(f, mode);
  $("download").href = `/api/download/${enc(f.ref)}`;
  $("newwin").href = url;
  const stage = $("stage"); stage.replaceChildren();
  const loading = document.createElement("div"); loading.className = "loading"; loading.innerHTML = '<div><div class="spinner"></div>Opening…</div>';
  const frame = document.createElement("iframe");
  frame.title = `Preview of ${f.name}`;
  if (f.kind === "html" && mode !== "source") {
    // model-written page: opaque-origin sandbox, scripts allowed only inside it
    frame.setAttribute("sandbox", "allow-scripts");
  } else {
    frame.setAttribute("sandbox", "allow-scripts allow-same-origin allow-downloads");
  }
  frame.addEventListener("load", () => loading.remove(), { once: true });
  frame.src = url;
  stage.append(loading, frame);
}

// -------- resize, full screen, keys
function setupGutter() {
  const g = $("gutter"); const split = $("split");
  try { const w = localStorage.getItem("hpp-panel-w"); if (w) document.documentElement.style.setProperty("--panel-w", w); } catch (_) {}
  let start = null;
  g.addEventListener("pointerdown", (e) => { start = { x: e.clientX, w: $("panel").getBoundingClientRect().width }; g.setPointerCapture(e.pointerId); document.body.classList.add("resizing"); });
  g.addEventListener("pointermove", (e) => {
    if (!start) return;
    const total = split.getBoundingClientRect().width;
    const w = Math.min(total - 340, Math.max(360, start.w - (e.clientX - start.x)));
    document.documentElement.style.setProperty("--panel-w", `${w}px`);
  });
  const end = () => { if (!start) return; start = null; document.body.classList.remove("resizing");
    try { localStorage.setItem("hpp-panel-w", getComputedStyle(document.documentElement).getPropertyValue("--panel-w")); } catch (_) {} };
  g.addEventListener("pointerup", end); g.addEventListener("pointercancel", end);
  g.addEventListener("keydown", (e) => {
    if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
    const w = $("panel").getBoundingClientRect().width + (e.key === "ArrowLeft" ? 40 : -40);
    document.documentElement.style.setProperty("--panel-w", `${Math.max(360, w)}px`);
  });
}

function toggleFull() { if (!state.active) return; $("app").classList.toggle("full"); }

document.addEventListener("keydown", (e) => {
  if (e.target.matches("input,select,textarea")) return;
  if (e.key === "Escape") { if ($("app").classList.contains("full")) $("app").classList.remove("full"); else if (state.active) closePanel(); }
  if ((e.key === "f" || e.key === "F") && !e.ctrlKey && !e.metaKey) toggleFull();
});

// -------- uploads (drop or pick)
async function upload(files) {
  let last = null;
  for (const file of files) {
    const r = await fetch("/api/upload", { method: "POST", headers: { "X-Filename": encodeURIComponent(file.name) }, body: file });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) { toast(`${file.name}: ${data.error || "could not be added"}`); continue; }
    last = data.ref;
  }
  await load();
  if (last) { open(last); toast("Added to the workspace"); }
}

function setupDrop() {
  const chat = $("chat"); let depth = 0;
  chat.addEventListener("dragenter", (e) => { e.preventDefault(); depth++; document.body.classList.add("dragging"); });
  chat.addEventListener("dragleave", () => { if (--depth <= 0) { depth = 0; document.body.classList.remove("dragging"); } });
  chat.addEventListener("dragover", (e) => e.preventDefault());
  chat.addEventListener("drop", (e) => { e.preventDefault(); depth = 0; document.body.classList.remove("dragging"); if (e.dataTransfer.files.length) upload(e.dataTransfer.files); });
  $("upload").addEventListener("change", (e) => { if (e.target.files.length) upload(e.target.files); e.target.value = ""; });
}

$("version").addEventListener("change", (e) => open(e.target.value));
$("full").onclick = toggleFull;
$("close").onclick = closePanel;
setupGutter(); setupDrop();
load().then(() => {
  // as in Hermes: when a run finishes, the main deliverable opens beside the chat
  const first = state.files.filter((f) => f.root === "output" && f.kind === "html").sort((a, b) => b.version - a.version)[0];
  if (first && !location.hash.includes("noauto") && !location.hash.includes("phone")) setTimeout(() => { open(first.ref); toast("Hermes created 5 files · the briefing opened beside the chat"); }, 500);
});
