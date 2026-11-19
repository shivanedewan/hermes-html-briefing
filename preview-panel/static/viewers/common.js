// Shared helpers for the viewer pages.
export function params() {
  const out = {};
  for (const part of location.hash.slice(1).split("&")) {
    const i = part.indexOf("=");
    if (i > 0) out[decodeURIComponent(part.slice(0, i))] = decodeURIComponent(part.slice(i + 1));
  }
  // only same-origin API paths may be opened
  if (out.src && !/^\/api\/(raw|pdf|sheet)\//.test(out.src)) out.src = "";
  return out;
}

export function message(host, html) {
  host.querySelectorAll(".msg").forEach((m) => m.remove());
  if (html == null) return;
  const m = document.createElement("div"); m.className = "msg"; m.innerHTML = html; host.append(m);
}

export const spinner = (text) => `<div><div class="spinner"></div>${text}</div>`;

export async function fetchOk(url) {
  const r = await fetch(url);
  if (!r.ok) {
    let detail = `The server answered ${r.status}`;
    try { detail = (await r.json()).error || detail; } catch (_) {}
    throw new Error(detail);
  }
  return r;
}

export function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

export function failure(host, err) {
  message(host, `<div><b>This file can't be previewed</b><br>${escapeHtml(err.message || err)}<br><br>You can still download it.</div>`);
}
