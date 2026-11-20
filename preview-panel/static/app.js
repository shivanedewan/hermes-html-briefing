// Hermes preview panel v1.1: chat on the left, Claude-style file panel on the right.
// Watches the workspace, opens new deliverables by itself, edits text files as new versions.
const $ = (id) => document.getElementById(id);
const state = { files: [], byRef: new Map(), tabs: [], active: null, mode: {}, dirty: new Set(), editing: null,
  writable: false, soffice: false, demo: false, first: true, frame: null };
const KIND_LABEL = { html: "HTML", pdf: "PDF", docx: "DOCX", office: "DOC", slides: "PPTX", sheet: "XLSX", image: "IMG", markdown: "MD", text: "TXT" };
const KIND_NAME = { html: "Web page", pdf: "PDF document", docx: "Word document", office: "Document", slides: "Presentation",
  sheet: "Spreadsheet", image: "Image", markdown: "Markdown", text: "Text" };
const PRIORITY = ["html", "slides", "docx", "pdf", "sheet", "markdown", "office", "text", "image"];
const POLL_MS = 1200;

function modesFor(f) {
  const changes = group(f).length > 1 && f.version > 1 && isTextual(f) ? [["changes", "Changes"]] : [];
  switch (f.kind) {
    case "docx": return [["doc", "Document"], ...(state.soffice ? [["exact", "Exact layout"]] : [])];
    case "html": return [["page", "Page"], ["source", "Source"]];
    case "markdown": return [["md", "Formatted"], ["source", "Source"], ...changes];
    case "text": return changes.length ? [["text", "Text"], ...changes] : null;
    case "sheet": return isCsv(f) && changes.length ? [["table", "Table"], ...changes] : null;
    default: return null;
  }
}
const isCsv = (f) => f.ext === "csv" || f.ext === "tsv";
const isTextual = (f) => f.kind === "markdown" || f.kind === "text" || isCsv(f);
const copyable = (f) => isTextual(f) || f.kind === "html";

function icon(file, cls = "ci") {
  const s = document.createElement("span");
  s.className = `${cls} ${file.kind}`;
  s.textContent = file.ext === "csv" ? "CSV" : file.ext === "pdf" ? "PDF" : (KIND_LABEL[file.kind] || file.ext.toUpperCase());
  return s;
}
const size = (n) => n < 1024 ? `${n} B` : n < 1048576 ? `${(n / 1024).toFixed(0)} KB` : `${(n / 1048576).toFixed(1)} MB`;
const enc = (ref) => ref.split("/").map(encodeURIComponent).join("/");
function toast(text) { const t = $("toast"); t.textContent = text; t.classList.add("show"); clearTimeout(toast.t); toast.t = setTimeout(() => t.classList.remove("show"), 3200); }
const group = (file) => state.files.filter((f) => f.group === file.group).sort((a, b) => a.version - b.version);
const latest = (key) => state.files.filter((f) => f.group === key).sort((a, b) => b.version - a.version)[0];
const file = (ref) => state.byRef.get(ref);

// ---------------------------------------------------------------- workspace watching
async function refresh() {
  let data;
  try { const r = await fetch("/api/files", { cache: "no-store" }); data = await r.json(); $("live").classList.remove("off"); }
  catch (_) { $("live").classList.add("off"); return; }
  const before = state.byRef;
  state.files = data.files; state.byRef = new Map(data.files.map((f) => [f.ref, f]));
  Object.assign(state, { writable: data.writable, soffice: data.soffice, demo: data.demo });
  $("simulate").hidden = !(data.demo && data.writable);
  const fresh = state.first ? [] : data.files.filter((f) => !before.has(f.ref));
  const changed = state.first ? [] : data.files.filter((f) => before.has(f.ref) &&
    (before.get(f.ref).mtime !== f.mtime || before.get(f.ref).writing !== f.writing));
  state.first = false;
  // tabs whose file disappeared
  state.tabs = state.tabs.filter((r) => state.byRef.has(r) || state.dirty.has(r));
  renderCards(fresh); renderList(fresh);
  if (fresh.length && !state.expect) {
    // a new deliverable appeared (Hermes wrote it): open the most important one beside the chat
    const pick = [...fresh].filter((f) => f.root === "output").sort((a, b) => PRIORITY.indexOf(a.kind) - PRIORITY.indexOf(b.kind))[0];
    if (pick && !(state.active && state.dirty.has(state.active))) {
      open(pick.ref);
      toast(fresh.length > 1 ? `Hermes created ${fresh.length} files · opened ${pick.name}` : `Hermes ${pick.writing ? "is writing" : "created"} ${pick.name}`);
    } else if (pick) toast(`Hermes created ${pick.name} (your edit is still open)`);
  }
  state.expect = null;
  for (const f of changed) {
    if (f.ref !== state.active) continue;
    if (state.dirty.has(f.ref)) { toast(`${f.name} changed on disk while you were editing; your text is kept`); continue; }
    if (!state.editing) updateActive(f);
  }
  if (state.active && state.byRef.has(state.active)) { renderTabs(); renderMeta(file(state.active)); }
}

// ---------------------------------------------------------------- left side
function renderCards(fresh = []) {
  const box = $("cards"); box.replaceChildren();
  const seen = new Set();
  const picks = state.files.filter((f) => f.root === "output" && ["html", "slides", "docx", "pdf", "sheet"].includes(f.kind) && !isCsv(f))
    .sort((a, b) => PRIORITY.indexOf(a.kind) - PRIORITY.indexOf(b.kind));
  for (const f of picks) {
    if (seen.has(f.group)) continue; seen.add(f.group);
    const top = latest(f.group); const n = group(top).length;
    const b = document.createElement("button"); b.className = "card" + (fresh.some((x) => x.group === top.group) ? " new" : "");
    b.dataset.group = top.group;
    const t = document.createElement("div");
    const name = document.createElement("div"); name.className = "cn"; name.textContent = top.name;
    const meta = document.createElement("div"); meta.className = "cm"; meta.textContent = `${KIND_NAME[top.kind]} · ${size(top.size)}${n > 1 ? ` · ${n} versions` : ""}`;
    t.append(name, meta); b.append(icon(top), t);
    b.onclick = () => open(top.ref);
    box.append(b);
  }
  markCards();
}

function renderList(fresh = []) {
  const box = $("filelist"); box.replaceChildren();
  const sorted = [...state.files].sort((a, b) => (a.root === b.root ? a.name.localeCompare(b.name, undefined, { numeric: true }) : a.root === "uploads" ? -1 : 1));
  for (const f of sorted) {
    const row = document.createElement("div"); row.className = "frow" + (fresh.includes(f) ? " new" : ""); row.tabIndex = 0;
    const name = document.createElement("div"); name.textContent = f.name;
    if (f.writing) { const w = document.createElement("span"); w.className = "writing-badge"; w.textContent = " writing…"; name.append(w); }
    const badge = document.createElement("span"); badge.className = "badge"; badge.textContent = f.root === "uploads" ? "your file" : KIND_NAME[f.kind];
    const sz = document.createElement("small"); sz.textContent = size(f.size);
    row.append(icon(f), name, badge, sz);
    row.onclick = () => open(f.ref);
    row.onkeydown = (e) => { if (e.key === "Enter") open(f.ref); };
    box.append(row);
  }
}

// ---------------------------------------------------------------- tabs
function open(ref, { force = false } = {}) {
  const f = file(ref); if (!f) return;
  if (!force && state.active && state.dirty.has(state.active) && state.active !== ref) {
    if (!confirm("You have unsaved edits. Leave them? (Cancel to keep editing)")) return;
    discard(state.active);
  }
  const i = state.tabs.findIndex((t) => file(t)?.group === f.group);
  if (i >= 0) state.tabs[i] = ref; else state.tabs.push(ref);
  state.active = ref; state.editing = null;
  document.body.classList.add("has-panel"); $("panel").hidden = false;
  renderTabs(); renderActive();
}

function discard(ref) { state.dirty.delete(ref); if (state.editing === ref) state.editing = null; }

function closeTab(ref) {
  if (state.dirty.has(ref) && !confirm("Close and lose your unsaved edits?")) return;
  discard(ref);
  const i = state.tabs.indexOf(ref); if (i < 0) return;
  state.tabs.splice(i, 1);
  if (state.active === ref) { state.active = state.tabs[Math.max(0, i - 1)] || null; state.editing = null; }
  if (!state.active) return closePanel(true);
  renderTabs(); renderActive();
}

function closePanel(skipCheck = false) {
  if (!skipCheck && state.dirty.size && !confirm("Close the panel and lose your unsaved edits?")) return;
  state.dirty.clear(); state.tabs = []; state.active = null; state.editing = null; $("stage").replaceChildren();
  $("panel").hidden = true; document.body.classList.remove("has-panel"); $("app").classList.remove("full");
  markCards();
}

function markCards() {
  const g = file(state.active)?.group;
  document.querySelectorAll(".card").forEach((c) => c.classList.toggle("active", !!g && g === c.dataset.group));
}

function renderTabs() {
  const box = $("tabs"); box.replaceChildren();
  for (const ref of state.tabs) {
    const f = file(ref); if (!f) continue;
    const b = document.createElement("div"); b.className = "tab" + (ref === state.active ? " on" : ""); b.setAttribute("role", "tab");
    b.setAttribute("aria-selected", ref === state.active); b.tabIndex = 0;
    const dot = document.createElement("i"); dot.className = `ci ${f.kind}`;
    const name = document.createElement("span"); name.textContent = f.name;
    b.append(dot, name);
    if (f.writing) { const w = document.createElement("span"); w.className = "writing"; w.textContent = "writing"; b.append(w); }
    if (state.dirty.has(ref)) { const d = document.createElement("i"); d.className = "dirty"; d.title = "Unsaved edits"; b.append(d); }
    const x = document.createElement("button"); x.className = "x"; x.title = "Close tab";
    x.innerHTML = '<svg viewBox="0 0 24 24"><path d="M6 6l12 12M18 6 6 18"/></svg>';
    x.onclick = (e) => { e.stopPropagation(); closeTab(ref); };
    b.append(x);
    b.onclick = () => { if (ref !== state.active) open(ref); };
    b.onkeydown = (e) => { if (e.key === "Enter") b.onclick(); };
    box.append(b);
  }
  markCards();
}

// ---------------------------------------------------------------- active file
function viewerUrl(f, mode) {
  const e = enc(f.ref); const prev = group(f).filter((v) => v.version < f.version).at(-1);
  if (state.editing === f.ref) return isCsv(f) ? `/static/viewers/sheet.html#src=/api/sheet/${e}&ref=${e}&edit=1` :
    `/static/viewers/editor.html#src=/api/raw/${e}&ref=${e}&lang=${f.kind === "markdown" ? "md" : f.ext}`;
  if (mode === "changes" && prev) return `/static/viewers/diff.html#src=/api/raw/${e}&old=/api/raw/${enc(prev.ref)}&a=${encodeURIComponent(prev.name)}&b=${encodeURIComponent(f.name)}`;
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

function currentMode(f) {
  const modes = modesFor(f);
  const m = state.mode[f.group];
  return modes ? (modes.some(([k]) => k === m) ? m : modes[0][0]) : "";
}

function renderMeta(f) {
  $("kind-icon").replaceChildren(icon(f));
  $("fname").textContent = f.name;
  const meta = [KIND_NAME[f.kind], size(f.size), new Date(f.mtime * 1000).toLocaleString()];
  if (f.root === "uploads") meta.push("your file");
  if (f.writing) meta.push("Hermes is writing…");
  if (state.editing === f.ref) meta.push(state.dirty.has(f.ref) ? "editing · unsaved" : "editing");
  $("fmeta").textContent = meta.join(" · ");
}

function renderActive() {
  const f = file(state.active); if (!f) return;
  const modes = state.editing ? null : modesFor(f);
  const mode = currentMode(f);
  renderMeta(f);
  const versions = group(f);
  const vs = $("version"); vs.replaceChildren(); vs.hidden = versions.length < 2 || !!state.editing;
  for (const v of versions) { const o = document.createElement("option"); o.value = v.ref; o.textContent = `Version ${v.version}${v === versions.at(-1) ? " (latest)" : ""}`; o.selected = v.ref === f.ref; vs.append(o); }
  const seg = $("modes"); seg.replaceChildren(); seg.hidden = !modes || modes.length < 2;
  for (const [key, label] of modes || []) {
    const b = document.createElement("button"); b.textContent = label; b.className = key === mode ? "on" : "";
    b.onclick = () => { state.mode[f.group] = key; renderActive(); };
    seg.append(b);
  }
  const edit = $("edit");
  edit.hidden = !f.editable || f.writing;
  edit.classList.toggle("on", state.editing === f.ref);
  edit.lastChild.textContent = state.editing === f.ref ? "Editing" : "Edit";
  $("copy").hidden = !copyable(f);
  const url = viewerUrl(f, mode);
  $("download").href = `/api/download/${enc(f.ref)}`;
  $("newwin").href = state.editing ? viewerUrl(f, "") : url;
  mount(url, f);
}

function mount(url, f) {
  const stage = $("stage"); stage.replaceChildren();
  const loading = document.createElement("div"); loading.className = "loading"; loading.innerHTML = '<div><div class="spinner"></div>Opening…</div>';
  const frame = document.createElement("iframe");
  frame.title = `Preview of ${f.name}`;
  // model-written HTML: opaque-origin sandbox (scripts run only inside it); our own viewers: same origin
  frame.setAttribute("sandbox", f.kind === "html" && url.startsWith("/api/raw/") ? "allow-scripts" : "allow-scripts allow-same-origin allow-downloads allow-modals");
  frame.addEventListener("load", () => loading.remove(), { once: true });
  frame.src = url;
  state.frame = frame;
  stage.append(loading, frame);
}

// a file that is open has changed on disk (Hermes wrote more, or a new save)
function updateActive(f) {
  renderMeta(f);
  const live = state.frame?.contentWindow;
  // markdown/text viewers update in place (keeps scroll, follows the end while Hermes writes)
  if (live && state.frame.src.includes("/viewers/") && /\/(markdown|text)\.html/.test(state.frame.src)) {
    live.postMessage({ type: "refresh", follow: f.writing }, location.origin);
  } else if (!f.writing) {
    renderActive();
  }
  $("edit").hidden = !f.editable || f.writing;
}

// ---------------------------------------------------------------- messages from viewers (editor, sheet editor)
window.addEventListener("message", async (e) => {
  if (e.origin !== location.origin || e.source !== state.frame?.contentWindow) return;
  const m = e.data || {};
  if (m.type === "dirty") {
    if (m.dirty) state.dirty.add(state.active); else state.dirty.delete(state.active);
    renderTabs(); renderMeta(file(state.active));
  } else if (m.type === "saved" && typeof m.ref === "string") {
    state.dirty.delete(state.active); state.editing = null; state.expect = m.ref;
    await refresh();
    open(m.ref, { force: true });
    toast(`Saved as ${file(m.ref)?.name || "a new version"} · the original is unchanged`);
  } else if (m.type === "cancel") {
    state.dirty.delete(state.active); state.editing = null; renderTabs(); renderActive();
  }
});

$("edit").onclick = () => {
  const f = file(state.active); if (!f?.editable) return;
  if (state.editing === f.ref) {
    if (state.dirty.has(f.ref) && !confirm("Stop editing and lose your unsaved edits?")) return;
    discard(f.ref);
  } else state.editing = f.ref;
  renderTabs(); renderActive();
};

$("copy").onclick = async () => {
  const f = file(state.active); if (!f) return;
  try {
    const text = await (await fetch(`/api/raw/${enc(f.ref)}`)).text();
    await copyText(text);
    toast(f.kind === "html" ? "Page source copied" : "Copied to the clipboard");
  } catch (_) { toast("Could not copy"); }
};

async function copyText(text) {
  try { await navigator.clipboard.writeText(text); return; } catch (_) {}
  const ta = document.createElement("textarea"); ta.value = text; ta.style.position = "fixed"; ta.style.opacity = "0";
  document.body.append(ta); ta.select(); document.execCommand("copy"); ta.remove();
}

// ---------------------------------------------------------------- resize, full screen, keys
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
  if (e.target.matches("input,select,textarea,[contenteditable]")) return;
  if (e.key === "Escape") { if ($("app").classList.contains("full")) $("app").classList.remove("full"); else if (state.active) closePanel(); }
  if ((e.key === "f" || e.key === "F") && !e.ctrlKey && !e.metaKey) toggleFull();
  if ((e.key === "e" || e.key === "E") && !e.ctrlKey && !e.metaKey && !$("edit").hidden && !state.editing) $("edit").click();
});
window.addEventListener("beforeunload", (e) => { if (state.dirty.size) { e.preventDefault(); e.returnValue = ""; } });

// ---------------------------------------------------------------- uploads (drop or pick) and the demo simulator
async function upload(files) {
  let last = null;
  for (const f of files) {
    const r = await fetch("/api/upload", { method: "POST", headers: { "X-Filename": encodeURIComponent(f.name), "X-Hermes": "1" }, body: f });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) { toast(`${f.name}: ${data.error || "could not be added"}`); continue; }
    last = data.ref;
  }
  if (last) { state.expect = last; await refresh(); open(last); toast("Added to the workspace"); }
}

function setupDrop() {
  const chat = $("chat"); let depth = 0;
  chat.addEventListener("dragenter", (e) => { e.preventDefault(); depth++; document.body.classList.add("dragging"); });
  chat.addEventListener("dragleave", () => { if (--depth <= 0) { depth = 0; document.body.classList.remove("dragging"); } });
  chat.addEventListener("dragover", (e) => e.preventDefault());
  chat.addEventListener("drop", (e) => { e.preventDefault(); depth = 0; document.body.classList.remove("dragging"); if (e.dataTransfer.files.length) upload(e.dataTransfer.files); });
  $("upload").addEventListener("change", (e) => { if (e.target.files.length) upload(e.target.files); e.target.value = ""; });
}

$("simulate").onclick = async () => {
  const r = await fetch("/api/simulate", { method: "POST", headers: { "X-Hermes": "1" } });
  if (!r.ok) toast((await r.json().catch(() => ({}))).error || "Simulation unavailable");
  // nothing else to do: the watcher sees the new file, opens it and follows it as it is written
};

$("version").addEventListener("change", (e) => open(e.target.value));
$("full").onclick = toggleFull;
$("close").onclick = () => closePanel();
setupGutter(); setupDrop();
refresh().then(() => {
  setInterval(refresh, POLL_MS);
  // as in Hermes: when a run finishes, the main deliverable opens beside the chat
  const first = state.files.filter((f) => f.root === "output" && f.kind === "html").sort((a, b) => b.version - a.version)[0];
  if (first && !location.hash.includes("noauto") && !location.hash.includes("phone")) setTimeout(() => { open(first.ref); toast("Hermes created 5 files · the briefing opened beside the chat"); }, 500);
});
