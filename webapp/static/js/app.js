/* CoH UCS Tools — SPA (path routing, no build step). */

import { applyRouteSeo } from "./seo.js";
import { initNavLinks, initSpaNav, navigateRoute, parseRoute, routePath, scrollToMain } from "./router.js";
import { t, initI18n, applyShellI18n } from "./i18n.js";
import { beginRoute, isRouteAbortError, patchHtml, q, setViewHtml } from "./routeScope.js";

import {
  view, toast, api, apiUrl, esc, fmt, loadFiles, fileOptions, UCS_FACTS, isHybridUi,
  destroyCharts, makeChart, getChartColors, exportChartPng, renderRouteError, renderPaneError,
  profileQueryString, profileBarHtml, bindProfileBar, getView,
} from "./core.js";
import {
  initTheme, renderDiff, renderRanges, renderValidator, renderLanguages,
  renderMergeWizard, renderInstall, renderMtLab, renderGlossary,
  renderTimeline, renderDepots, renderSearch, renderBookmarks,
  renderPatch, renderSga, renderSettings, renderEditor,
  renderVerify, renderTranslation,
  renderCampaigns, renderGames, renderAbout,
} from "./features.js";

initTheme();
initNavLinks();
initSpaNav();
initMobileNav();

function initMobileNav() {
  const toggle = document.getElementById("nav-toggle");
  const nav = document.getElementById("nav");
  if (!toggle || !nav) return;
  toggle.addEventListener("click", () => {
    const open = nav.classList.toggle("open");
    toggle.setAttribute("aria-expanded", open ? "true" : "false");
    toggle.textContent = open ? t("nav.menu_close") : t("nav.menu");
  });
  window.addEventListener("coh-route", () => {
    nav.classList.remove("open");
    toggle.setAttribute("aria-expanded", "false");
    toggle.textContent = t("nav.menu");
  });
}

/* ------------------------------------------------------------ dashboard */
async function renderDashboard() {
  if (!setViewHtml(`<div class="loading">${t("msg.scanning")}</div>`)) return;
  const [versions, files] = await Promise.all([
    api("/api/versions").then(d => d.versions),
    loadFiles(),
  ]);
  const maxKeys = Math.max(...versions.map(v => v.keys), 1);
  const uploads = files.filter(f => f.kind === "upload");
  const generated = files.filter(f => f.kind === "generated");
  const onDisk = versions.filter(v => v.available);
  const hybridBanner = isHybridUi() && onDisk.length === 0 ? `
    <div class="banner mb-md">
      <strong>${t("banner.hybrid_title")}</strong>
      ${t("banner.hybrid_body")}
      <a href="${routePath("upload")}">${t("misc.upload_your_ucs")}</a> ${t("banner.hybrid_or")}
    </div>` : "";

  if (!setViewHtml(`
    <h2 class="section-title">${t("route.dashboard")}</h2>
    <p class="section-sub">${t("route.dashboard.sub")}</p>
    ${hybridBanner}
    <div class="grid cols-2">
      ${versions.map(v => `
        <div class="card">
          <div class="card-header">
            <h3>${esc(v.name)}</h3>
            <span class="kind-tag">${v.available ? t("kind.on_disk") : t("kind.not_found")}</span>
          </div>
          <div class="keybar"><i style="width:${v.available ? (100 * v.keys / maxKeys).toFixed(1) : 0}%"></i></div>
          <div class="keybar-label">${v.available ? fmt(v.keys) + " " + t("msg.keys") : t("msg.file_not_present")}</div>
          <div class="stat-row"><span class="k">${t("stat.origin")}</span><span class="v">${esc(v.origin)}</span></div>
          <div class="stat-row"><span class="k">${t("stat.completeness")}</span><span class="v">${esc(v.completeness)}</span></div>
          ${v.available ? `<div class="btn-row"><a class="btn ghost small" href="${v.download_url}">${t("btn.download")}</a>
            <a class="btn ghost small" href="${routePath("upload", { file: v.id })}">${t("btn.analyze")}</a></div>` : ""}
        </div>`).join("")}
    </div>
    <h2 class="section-title mt-lg">${t("route.stored_files")}</h2>
    <p class="section-sub">${t("msg.stored_count", { uploads: uploads.length, generated: generated.length })}</p>
    ${files.length === 0 ? `<div class="empty"><span class="empty-icon">&#128194;</span>
        ${t("msg.empty_files")} <a href="${routePath("upload")}">${t("btn.upload_link")}</a>.</div>` : `
      <div class="table-wrap"><table class="data">
        <thead><tr><th>${t("table.kind")}</th><th>${t("table.name")}</th><th>${t("table.keys")}</th><th>${t("table.dups")}</th><th>${t("table.invalid")}</th><th></th></tr></thead>
        <tbody>${files.map(f => `
          <tr><td>${f.kind}</td><td class="val">${esc(f.name)}</td><td class="num">${fmt(f.keys)}</td>
            <td>${f.duplicates}</td><td>${f.invalid_lines}</td>
            <td><a href="${routePath("upload", { file: f.id })}">${t("table.analyze")}</a> · <a href="${apiUrl(`/api/downloads/${f.id}`)}">${t("table.dl")}</a>
            ${f.kind !== "version" ? ` · <a href="#" data-del="${f.id}" class="link-danger">${t("table.del")}</a>` : ""}</td></tr>`).join("")}
        </tbody></table></div>`}
  `)) return;
  view.querySelectorAll("[data-del]").forEach(a => a.addEventListener("click", async e => {
    e.preventDefault();
    await api(`/api/files/${a.dataset.del}`, { method: "DELETE" });
    toast(t("msg.deleted"));
    renderDashboard();
  }));
}

/* -------------------------------------------------------------- upload */
async function renderUpload(params) {
  if (!setViewHtml(`<div class="loading">${t("msg.preparing")}</div>`)) return;
  const files = await loadFiles();
  const selected = params.get("file") || "";
  const savedProfile = sessionStorage.getItem("coh-last-profile") || "coh1";
  const savedStrict = sessionStorage.getItem("coh-strict-profile") === "true";
  if (!setViewHtml(`
    <h2 class="section-title">${t("route.upload")}</h2>
    <p class="section-sub">${t("route.upload.sub")}</p>
    <div class="grid cols-2">
      <div><div class="dropzone" id="dropzone"><span class="dz-icon">&#9738;</span>
        <p><strong>${t("misc.drop_ucs")}</strong></p><input type="file" id="file-input" accept=".ucs" hidden></div>
        <div class="card mt-sm"><h3>${t("misc.format_heading")}</h3>
          ${UCS_FACTS.map(([k,v]) => `<div class="stat-row"><span class="k">${k}</span><span class="v">${esc(v)}</span></div>`).join("")}
        </div></div>
      <div><label class="field">${t("label.stored_file")}<select id="file-select"><option value="">—</option>${fileOptions(files, selected)}</select></label>
        <label class="field mt-sm">${t("label.expected_profile")}
          <select id="game-profile">
            <option value="coh1" ${savedProfile === "coh1" ? "selected" : ""}>${t("game.coh1")}</option>
            <option value="coh2" ${savedProfile === "coh2" ? "selected" : ""}>${t("game.coh2")}</option>
            <option value="dow1" ${savedProfile === "dow1" ? "selected" : ""}>${t("game.dow1")}</option>
            <option value="dow2" ${savedProfile === "dow2" ? "selected" : ""}>${t("game.dow2")}</option>
          </select>
        </label>
        <label class="toggle mt-sm"><input type="checkbox" id="strict-profile" ${savedStrict ? "checked" : ""}> ${t("label.reject_mismatch")}</label>
        <div id="analysis"></div></div>
    </div>
    <div id="entries-panel" class="mt-lg"></div>`)) return;
  q("game-profile")?.addEventListener("change", e => {
    sessionStorage.setItem("coh-last-profile", e.target.value);
  });
  q("strict-profile")?.addEventListener("change", e => {
    sessionStorage.setItem("coh-strict-profile", e.target.checked ? "true" : "false");
  });
  const dz = q("dropzone");
  const input = q("file-input");
  if (!dz || !input) return;
  async function upload(file) {
    if (!file) return;
    const fd = new FormData(); fd.append("file", file);
    const profile = q("game-profile")?.value || "coh1";
    const strict = q("strict-profile")?.checked ? "true" : "false";
    const res = await api(`/api/files?game_profile=${profile}&strict_profile=${strict}`, { method: "POST", body: fd });
    toast(res.message);
    if (res.game_profile) {
      const gp = res.game_profile;
      sessionStorage.setItem("coh-last-profile", profile);
      sessionStorage.setItem("coh-strict-profile", strict);
      toast(t("msg.classified_as", { profile: gp.best_match, pct: Math.round(gp.confidence * 100) }), 4000);
    }
    navigateRoute("upload", { file: res.file.id });
  }
  dz.onclick = () => input.click();
  input.onchange = () => upload(input.files[0]);
  ["dragover","dragleave","drop"].forEach(ev => dz.addEventListener(ev, e => {
    e.preventDefault(); dz.classList.toggle("drag", ev === "dragover");
    if (ev === "drop") upload(e.dataTransfer.files[0]);
  }));
  document.getElementById("file-select")?.addEventListener("change", e => {
    navigateRoute("upload", e.target.value ? { file: e.target.value } : undefined);
  });
  if (selected) await renderAnalysis(selected);
}

async function renderAnalysis(fileId) {
  if (!patchHtml("analysis", `<div class="loading">${t("msg.parsing")}</div>`)) return;
  const [f, val, gp] = await Promise.all([
    api(`/api/files/${fileId}`),
    api(`/api/files/${fileId}/validate`),
    api(`/api/files/${fileId}/game-profile`).catch(() => null),
  ]);
  const expected = sessionStorage.getItem("coh-last-profile") || "coh1";
  let profileBlock = "";
  if (gp) {
    const mismatch = gp.best_match !== expected;
    profileBlock = `
      <div class="banner mt-sm text-dim-sm">
        <strong>${t("misc.game_profile_label")}</strong> ${esc(gp.best_match)} (${Math.round(gp.confidence * 100)}% confidence)
        ${mismatch ? `<span class="bad">${t("misc.expected_mismatch", { expected: expected })}</span>` : `<span class="good">${t("misc.matches_selection")}</span>`}
        ${gp.warnings?.length ? `<ul class="mt-sm list-indented">${gp.warnings.map(w => `<li>${esc(w)}</li>`).join("")}</ul>` : ""}
      </div>`;
  }
  if (!patchHtml("analysis", `
    <div class="card"><h3>${esc(f.name)}</h3>
      <div class="stat-row"><span class="k">${t("stat.keys")}</span><span class="v good">${fmt(f.keys)}</span></div>
      <div class="stat-row"><span class="k">${t("stat.validation")}</span><span class="v ${val.ok?'good':'bad'}">${val.ok ? t("misc.ok_status") : t("misc.fail_status")}</span></div>
      ${profileBlock}
      <div class="btn-row">
        <a class="btn ghost small" href="${routePath("validator", { file: f.id })}">${t("btn.validator")}</a>
        <a class="btn ghost small" href="${routePath("compare", { a: f.id })}">${t("btn.compare")}</a>
        <a class="btn ghost small" href="${routePath("games", { file: f.id })}">${t("btn.game_profiles")}</a>
      </div>
    </div>`)) return;
  renderEntriesBrowser(fileId);
}

async function renderEntriesBrowser(fileId) {
  if (!patchHtml("entries-panel", `<h2 class="section-title">${t("route.entries")}</h2>
    <div class="form-row"><input type="search" id="q" placeholder="${t("misc.search_id_text")}">
      <label class="toggle"><input type="checkbox" id="q-regex"> ${t("misc.regex")}</label>
      <button class="btn small" id="q-go">${t("btn.search")}</button></div><div id="entries-out"></div>`)) return;
  const state = { offset: 0, limit: 50 };
  async function page() {
    const p = new URLSearchParams({ offset: state.offset, limit: state.limit });
    const search = q("q");
    if (search?.value) {
      p.set("search", search.value);
      p.set("regex", q("q-regex")?.checked ?? false);
    }
    const data = await api(`/api/files/${fileId}/entries?${p}`);
    if (!patchHtml("entries-out", data.total ? `
      <div class="table-wrap"><table class="data"><tbody>
        ${data.entries.map(e => `<tr><td class="num">${e.key}</td><td class="val">${esc(e.value)}</td></tr>`).join("")}
      </tbody></table></div>
      <div class="pager"><button class="btn ghost small" id="prev" ${state.offset===0?"disabled":""}>&larr;</button>
        ${fmt(state.offset+1)}–${fmt(Math.min(state.offset+state.limit,data.total))} / ${fmt(data.total)}
        <button class="btn ghost small" id="next" ${state.offset+state.limit>=data.total?"disabled":""}>&rarr;</button></div>` :
      `<div class="empty">${t("msg.no_matches")}</div>`)) return;
    q("entries-out")?.querySelector("#prev")?.addEventListener("click", () => {
      state.offset = Math.max(0, state.offset - state.limit);
      page();
    });
    q("entries-out")?.querySelector("#next")?.addEventListener("click", () => {
      state.offset += state.limit;
      page();
    });
  }
  q("q-go")?.addEventListener("click", () => { state.offset = 0; page(); });
  page();
}

/* -------------------------------------------------------------- compare */
async function renderCompare(params) {
  if (!setViewHtml(`<div class="loading">${t("msg.loading")}</div>`)) return;
  const files = await loadFiles();
  const a = params.get("a") || "", b = params.get("b") || "";
  if (!setViewHtml(`
    <h2 class="section-title">${t("route.compare")}</h2>
    <p class="section-sub">${t("route.compare.sub")}</p>
    ${profileBarHtml()}
    <div class="form-row">
      <label class="field">${t("label.file_a")}<select id="sel-a"><option value="">—</option>${fileOptions(files,a)}</select></label>
      <label class="field">${t("label.file_b")}<select id="sel-b"><option value="">—</option>${fileOptions(files,b)}</select></label>
      <button class="btn" id="go">${t("btn.compare")}</button>
      <a class="btn ghost" href="${routePath("diff", { a, b })}">${t("btn.diff_view")}</a>
      <a class="btn ghost" href="${routePath("ranges", { a, b })}">${t("btn.ranges")}</a>
    </div><div id="compare-out"></div>`)) return;
  bindProfileBar(getView());
  q("go")?.addEventListener("click", () => {
    const va = q("sel-a")?.value, vb = q("sel-b")?.value;
    if (va && vb) navigateRoute("compare", { a: va, b: vb });
  });
  if (a && b) await runCompare(a, b);
}

async function runCompare(a, b) {
  if (!patchHtml("compare-out", `<div class="loading">${t("msg.crunching")}</div>`)) return;
  let d;
  try {
    d = await api(`/api/compare?a=${a}&b=${b}&${profileQueryString()}`);
  } catch (err) {
    if (isRouteAbortError(err)) return;
    renderPaneError(err, "compare-out", { retry: () => runCompare(a, b) });
    return;
  }
  const colors = getChartColors();
  const side = (s, label) => `
    <div class="card"><div class="card-header"><h3>${esc(s.name)}</h3><span class="kind-tag">${t("kind.side")} ${label}</span></div>
      <div class="keybar"><i style="width:${s.coverage_percent}%"></i></div>
      <div class="keybar-label">${t("misc.coverage_missing", { pct: s.coverage_percent, missing: fmt(s.missing_keys) })}</div>
      ${s.missing_ranges.length ? `<details><summary>${t("misc.ranges_count", { count: s.missing_ranges.length })}</summary>
        <div class="text-dim-sm">${s.missing_ranges.map(esc).join(", ")}</div></details>` : ""}
    </div>`;
  if (!patchHtml("compare-out", `
    <div class="banner">${t("misc.union_common", { union: fmt(d.union_keys), common: fmt(d.common_keys) })}
      <button class="btn ghost small" onclick="exportChartPng('ch-overlap','overlap.png')">${t("btn.export_chart")}</button></div>
    <div class="grid cols-2">${side(d.a,"A")}${side(d.b,"B")}</div>
    <div class="grid cols-2 mt-md">
      <div class="card"><div class="chart-box"><canvas id="ch-keys"></canvas></div></div>
      <div class="card"><div class="chart-box"><canvas id="ch-overlap"></canvas></div></div>
    </div>`)) return;
  window.exportChartPng = exportChartPng;
  destroyCharts();
  try {
    await makeChart(q("ch-keys"), {
      type: "bar", data: { labels: ["A","B"], datasets: [
        { label: t("misc.present"), data: [d.a.total_keys, d.b.total_keys], backgroundColor: colors.olive },
        { label: t("table.missing"), data: [d.a.missing_keys, d.b.missing_keys], backgroundColor: colors.red },
      ]}, options: { maintainAspectRatio: false, responsive: true, scales: { x: { stacked: true }, y: { stacked: true } } },
    });
    await makeChart(q("ch-overlap"), {
      type: "doughnut", data: { labels: ["common","only A","only B"],
        datasets: [{ data: [d.common_keys, d.b.missing_keys, d.a.missing_keys],
          backgroundColor: [colors.green, colors.amber, colors.red] }] },
      options: { maintainAspectRatio: false, responsive: true, cutout: "60%" },
    });
  } catch { /* Chart.js unavailable offline */ }
}

/* ---------------------------------------------------------------- merge */
async function renderMerge(params) {
  if (!setViewHtml(`<div class="loading">${t("msg.loading")}</div>`)) return;
  const files = await loadFiles();
  if (!setViewHtml(`
    <h2 class="section-title">${t("route.merge")}</h2>
    <p class="section-sub">${t("route.merge.sub")}</p>
    ${profileBarHtml()}
    <div class="card max-w-card">
      <div class="form-row">
        <label class="field">${t("label.target")}<select id="m-target">${fileOptions(files, params.get("target")||"")}</select></label>
        <label class="field">${t("label.source")}<select id="m-source">${fileOptions(files, params.get("source")||"")}</select></label>
      </div>
      <div class="form-row">
        <label class="toggle"><input type="radio" name="mode" value="placeholder" checked> &lt;MISSING&gt;</label>
        <label class="toggle"><input type="radio" name="mode" value="fill_from_source"> ${t("tab.fill_verbatim")}</label>
      </div>
      <button class="btn" id="m-go">${t("btn.merge")}</button><div id="merge-out"></div>
    </div>`)) return;
  bindProfileBar(getView());
  q("m-go")?.addEventListener("click", async () => {
    try {
    const r = await api(`/api/merge?${profileQueryString()}`, { method:"POST", headers:{"Content-Type":"application/json"},
      body: JSON.stringify({ target_id: q("m-target")?.value,
        source_id: q("m-source")?.value,
        mode: document.querySelector('input[name="mode"]:checked')?.value }) });
    patchHtml("merge-out", `<div class="banner"><a href="${r.download_url}">${t("misc.download_filename", { name: r.filename })}</a></div>`);
    } catch (err) { if (!isRouteAbortError(err)) toast(err.message); }
  });
}

/* ---------------------------------------------------------------- tools */
async function renderTools() {
  const tools = (await api("/api/tools")).tools;
  if (!setViewHtml(`
    <h2 class="section-title">${t("route.tools")}</h2>
    <p class="section-sub">${t("route.tools.sub")}</p>
    <div class="grid cols-3">${tools.map(tool => `
      <div class="card tool-card"><span class="cat">${esc(tool.category)}</span>
        <h3><a href="${esc(tool.url)}" target="_blank">${esc(tool.name)}</a></h3><p>${esc(tool.description)}</p></div>`).join("")}
    </div>
    <p class="mt-md"><a href="${routePath("depots")}">${t("misc.depots_sources_link")}</a> · <a href="${apiUrl("/docs")}" target="_blank">${t("misc.api_docs_link")}</a></p>`)) return;
}

/* --------------------------------------------------------------- router */
const routes = {
  dashboard: renderDashboard,
  about: renderAbout,
  upload: renderUpload,
  compare: renderCompare,
  merge: renderMerge,
  tools: renderTools,
  diff: renderDiff,
  ranges: renderRanges,
  validator: renderValidator,
  languages: renderLanguages,
  "merge-wizard": renderMergeWizard,
  install: renderInstall,
  mt: renderMtLab,
  glossary: renderGlossary,
  timeline: renderTimeline,
  depots: renderDepots,
  search: renderSearch,
  bookmarks: renderBookmarks,
  patch: renderPatch,
  sga: renderSga,
  settings: renderSettings,
  editor: renderEditor,
  verify: renderVerify,
  translation: renderTranslation,
  campaigns: renderCampaigns,
  games: renderGames,
};

async function route() {
  destroyCharts();
  beginRoute();
  const { name, params } = parseRoute();
  const handler = routes[name] || renderDashboard;
  const routeKey = routes[name] ? name : "dashboard";
  applyRouteSeo(routeKey);
  applyShellI18n();
  document.querySelectorAll("#nav a[data-route]").forEach(a =>
    a.classList.toggle("active", a.dataset.route === routeKey));
  try {
    await handler(params);
    scrollToMain();
  } catch (err) {
    if (isRouteAbortError(err)) return;
    renderRouteError(err, { retry: () => route() });
  }
}

window.addEventListener("coh-theme-changed", route);

window.addEventListener("popstate", route);
window.addEventListener("coh-route", route);
window.addEventListener("coh-i18n-changed", route);
initI18n().then(route);

window.addEventListener("coh-locale-click", () => { navigateRoute("languages"); });
