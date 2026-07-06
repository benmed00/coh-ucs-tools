/* Shared SPA utilities */

import { t, getLocaleTag } from "./i18n.js";
import { routePath } from "./router.js";
import { isRouteAbortError, routeAlive, routeSignal } from "./routeScope.js";
import { showToast, prefersReducedMotion } from "./motion.js";

/** Main content mount (lazy — safe if modules load before #view exists). */
export function getView() {
  return document.getElementById("view");
}

/** @deprecated prefer setViewHtml() from routeScope.js */
export const view = {
  set innerHTML(html) {
    const el = getView();
    if (el) el.innerHTML = html;
  },
  get innerHTML() {
    return getView()?.innerHTML ?? "";
  },
  querySelector(sel) {
    return getView()?.querySelector(sel) ?? null;
  },
  querySelectorAll(sel) {
    return getView()?.querySelectorAll(sel) ?? [];
  },
};

export const toastEl = document.getElementById("toast");

export function esc(s) {
  return String(s).replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

export function toast(msg, ms = 3200) {
  showToast(toastEl, msg, ms);
}

export function apiUrl(path) {
  return (window.API_BASE || "") + path;
}

/** True when static UI is on a CDN and API is on another origin (e.g. GitHub Pages + Fly). */
export function isHybridUi() {
  const base = window.API_BASE || "";
  if (!base) return false;
  try {
    return new URL(base).origin !== window.location.origin;
  } catch {
    return true;
  }
}

export async function api(path, opts = {}) {
  const headers = new Headers(opts.headers || {});
  const storedKey = localStorage.getItem("coh-api-key");
  if (storedKey && !headers.has("X-API-Key")) {
    headers.set("X-API-Key", storedKey);
  }
  const credentials = isHybridUi() ? "omit" : "include";
  const signal = opts.signal ?? routeSignal();
  const fetchOpts = { credentials, ...opts, headers };
  if (signal) fetchOpts.signal = signal;
  const res = await fetch(apiUrl(path), fetchOpts);
  if (res.status === 204) return null;
  let body = null;
  try { body = await res.json(); } catch { /* non-JSON */ }
  if (!res.ok) {
    const detail = body && body.detail ? JSON.stringify(body.detail) : res.statusText;
    throw new Error(`${res.status}: ${detail}`);
  }
  return body;
}

export function fmt(n) { return Number(n).toLocaleString(getLocaleTag()); }

/** Friendly route-level error panel with optional retry. */
export function renderRouteError(err, { retry } = {}) {
  if (!routeAlive()) return;
  const mount = getView();
  if (!mount) return;
  const msg = String(err?.message || err || "");
  let friendly = t("err.generic");
  let hint = "";
  if (/^404\b/.test(msg)) {
    friendly = t("err.404");
    hint = t("err.404_hint");
  } else if (/^401\b/.test(msg)) {
    friendly = t("err.401");
    hint = t("err.401_hint");
  } else if (/^429\b/.test(msg)) {
    friendly = t("err.429");
  } else if (/failed to fetch|networkerror/i.test(msg)) {
    friendly = t("err.network");
  }
  const settingsLink = `<a href="${routePath("settings")}">${t("nav.settings")}</a>`;
  mount.innerHTML = `
    <div class="banner error">
      <strong>${esc(friendly)}</strong>
      ${hint ? `<p class="muted mt-sm">${hint.replace("{settings}", settingsLink)}</p>` : ""}
      ${retry ? `<div class="btn-row mt-sm"><button type="button" class="btn ghost small" id="err-retry">${t("btn.retry")}</button></div>` : ""}
      <details class="mt-sm"><summary>${t("err.details")}</summary>
        <pre class="mono-block">${esc(msg)}</pre></details>
    </div>`;
  mount.querySelector("#err-retry")?.addEventListener("click", () => retry());
}

export { isRouteAbortError };

/** Compact error panel for a sub-region (compare results, webhook log, etc.). */
export function renderPaneError(err, paneId, { retry } = {}) {
  if (!routeAlive()) return false;
  const msg = String(err?.message || err || "");
  let friendly = t("err.generic");
  if (/^404\b/.test(msg)) friendly = t("err.404");
  else if (/^401\b/.test(msg)) friendly = t("err.401");
  else if (/^429\b/.test(msg)) friendly = t("err.429");
  else if (/failed to fetch|networkerror/i.test(msg)) friendly = t("err.network");
  const html = `
    <div class="banner error">
      <strong>${esc(friendly)}</strong>
      ${retry ? `<div class="btn-row mt-sm"><button type="button" class="btn ghost small pane-retry">${t("btn.retry")}</button></div>` : ""}
      <details class="mt-sm"><summary>${t("err.details")}</summary>
        <pre class="mono-block">${esc(msg)}</pre></details>
    </div>`;
  const el = document.getElementById(paneId);
  if (!el || !routeAlive()) return false;
  el.innerHTML = html;
  el.querySelector(".pane-retry")?.addEventListener("click", () => retry?.());
  return true;
}

export function fileLabel(f) {
  const tag = { upload: "UPL", version: "VER", generated: "GEN" }[f.kind] || "?";
  const prof = f.detected_profile ? ` · ${f.detected_profile}` : "";
  return `[${tag}] ${f.name} — ${fmt(f.keys)} keys${prof}`;
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
    ["coh1", t("game.coh1")], ["coh2", t("game.coh2")], ["dow1", t("game.dow1")], ["dow2", t("game.dow2")],
  ].map(([v, l]) => `<option value="${v}" ${p === v ? "selected" : ""}>${l}</option>`).join("");
  return `<div class="form-row profile-bar mb-sm">
    <label class="field">${t("label.game_profile")}<select id="gp-select">${opts}</select></label>
    <label class="toggle"><input type="checkbox" id="gp-strict" ${strict ? "checked" : ""}> ${t("label.block_mismatch")}</label>
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
  const dur = prefersReducedMotion() ? 0 : 600;
  window.Chart.defaults.animation.duration = dur;
  window.Chart.defaults.animation.easing = "easeOutQuart";
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

export function getChartColors() {
  const s = getComputedStyle(document.documentElement);
  const pick = v => s.getPropertyValue(v).trim() || undefined;
  return {
    amber: pick("--amber") || "#ffb648",
    olive: pick("--olive") || "#8a9a5b",
    green: pick("--green") || "#9acd68",
    red: pick("--red") || "#e06c4f",
    dim: pick("--text-dim") || "#8f8c77",
  };
}

/** @deprecated use getChartColors() */
export const CHART_COLORS = getChartColors();

export function exportChartPng(canvasId, name = "chart.png") {
  const c = document.getElementById(canvasId);
  if (!c) return;
  const a = document.createElement("a");
  a.href = c.toDataURL("image/png");
  a.download = name;
  a.click();
}
