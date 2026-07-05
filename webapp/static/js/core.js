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
  const res = await fetch(apiUrl(path), { credentials: "include", ...opts, headers });
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

export function profileQueryString() {
  const game_profile = sessionStorage.getItem("coh-last-profile") || "coh1";
  const strict_profile = sessionStorage.getItem("coh-strict-profile") === "true";
  return `game_profile=${encodeURIComponent(game_profile)}&strict_profile=${strict_profile}`;
}

export function profileBarHtml() {
  const p = sessionStorage.getItem("coh-last-profile") || "coh1";
  const strict = sessionStorage.getItem("coh-strict-profile") === "true";
  const opts = [
    ["coh1", "CoH 1"], ["coh2", "CoH 2"], ["dow1", "Dawn of War"], ["dow2", "DoW II"],
  ].map(([v, l]) => `<option value="${v}" ${p === v ? "selected" : ""}>${l}</option>`).join("");
  return `<div class="form-row profile-bar" style="margin-bottom:12px">
    <label class="field">Game profile<select id="gp-select">${opts}</select></label>
    <label class="toggle"><input type="checkbox" id="gp-strict" ${strict ? "checked" : ""}> Block mismatch</label>
  </div>`;
}

export function bindProfileBar(root = document) {
  root.querySelector("#gp-select")?.addEventListener("change", e => {
    sessionStorage.setItem("coh-last-profile", e.target.value);
  });
  root.querySelector("#gp-strict")?.addEventListener("change", e => {
    sessionStorage.setItem("coh-strict-profile", e.target.checked ? "true" : "false");
  });
}

export const UCS_FACTS = [
  ["Encoding", "UTF-16-LE", "Two bytes per character, little-endian."],
  ["BOM", "FF FE", "Byte-order mark at file start."],
  ["Separator", "first TAB", "Value is everything after the FIRST tab."],
  ["Fallback", "$id No Key", "Engine renders this when an id has no entry."],
];

const CHART_CDN = "https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.js";
let chartLoadPromise = null;

function configureChartDefaults() {
  if (!window.Chart) return;
  window.Chart.defaults.color = "#8f8c77";
  window.Chart.defaults.borderColor = "#3a4028";
  window.Chart.defaults.font.family = '"IBM Plex Mono", monospace';
}

/** Lazy-load Chart.js on first chart render (compare / languages views). */
export async function ensureChart() {
  if (window.Chart) {
    configureChartDefaults();
    return window.Chart;
  }
  if (!chartLoadPromise) {
    chartLoadPromise = new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = CHART_CDN;
      script.async = true;
      script.onload = () => {
        configureChartDefaults();
        resolve(window.Chart);
      };
      script.onerror = () => reject(new Error("Failed to load Chart.js"));
      document.head.appendChild(script);
    });
  }
  return chartLoadPromise;
}

export let charts = [];
export function destroyCharts() { charts.forEach(c => c.destroy()); charts = []; }

export async function makeChart(ctx, cfg) {
  await ensureChart();
  const c = new window.Chart(ctx, cfg);
  charts.push(c);
  return c;
}

export const CHART_COLORS = { amber: "#ffb648", olive: "#8a9a5b", green: "#9acd68", red: "#e06c4f", dim: "#8f8c77" };

export function exportChartPng(canvasId, name = "chart.png") {
  const c = document.getElementById(canvasId);
  if (!c) return;
  const a = document.createElement("a");
  a.href = c.toDataURL("image/png");
  a.download = name;
  a.click();
}
