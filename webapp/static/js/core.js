/* Shared SPA utilities */

export const view = document.getElementById("view");
export const toastEl = document.getElementById("toast");

export function esc(s) {
  return String(s).replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

export function toast(msg, ms = 3200) {
  toastEl.textContent = msg;
  toastEl.hidden = false;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => { toastEl.hidden = true; }, ms);
}

export function apiUrl(path) {
  return (window.API_BASE || "") + path;
}

export async function api(path, opts = {}) {
  const headers = new Headers(opts.headers || {});
  const storedKey = localStorage.getItem("coh-api-key");
  if (storedKey && !headers.has("X-API-Key")) {
    headers.set("X-API-Key", storedKey);
  }
  const res = await fetch(apiUrl(path), { ...opts, headers });
  if (res.status === 204) return null;
  let body = null;
  try { body = await res.json(); } catch { /* non-JSON */ }
  if (!res.ok) {
    const detail = body && body.detail ? JSON.stringify(body.detail) : res.statusText;
    throw new Error(`${res.status}: ${detail}`);
  }
  return body;
}

export function fmt(n) { return Number(n).toLocaleString("en-US"); }

export function fileLabel(f) {
  const tag = { upload: "UPL", version: "VER", generated: "GEN" }[f.kind] || "?";
  return `[${tag}] ${f.name} — ${fmt(f.keys)} keys`;
}

export async function loadFiles() {
  const data = await api("/api/files");
  return data.files;
}

export function fileOptions(files, selected) {
  return files.map(f =>
    `<option value="${f.id}" ${f.id === selected ? "selected" : ""}>${esc(fileLabel(f))}</option>`
  ).join("");
}

export const UCS_FACTS = [
  ["Encoding", "UTF-16-LE", "Two bytes per character, little-endian."],
  ["BOM", "FF FE", "Byte-order mark at file start."],
  ["Separator", "first TAB", "Value is everything after the FIRST tab."],
  ["Fallback", "$id No Key", "Engine renders this when an id has no entry."],
];

export let charts = [];
export function destroyCharts() { charts.forEach(c => c.destroy()); charts = []; }
export function makeChart(ctx, cfg) {
  const c = new Chart(ctx, cfg);
  charts.push(c);
  return c;
}
export const CHART_COLORS = { amber: "#ffb648", olive: "#8a9a5b", green: "#9acd68", red: "#e06c4f", dim: "#8f8c77" };
if (window.Chart) {
  Chart.defaults.color = "#8f8c77";
  Chart.defaults.borderColor = "#3a4028";
  Chart.defaults.font.family = '"IBM Plex Mono", monospace';
}

export function exportChartPng(canvasId, name = "chart.png") {
  const c = document.getElementById(canvasId);
  if (!c) return;
  const a = document.createElement("a");
  a.href = c.toDataURL("image/png");
  a.download = name;
  a.click();
}
