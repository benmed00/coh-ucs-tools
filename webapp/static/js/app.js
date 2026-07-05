/* CoH UCS Tools — SPA (path routing, no build step). */

import { applyRouteSeo } from "./seo.js";
import { initNavLinks, initSpaNav, navigateRoute, parseRoute, routePath } from "./router.js";
import { t, initI18n, applyShellI18n } from "./i18n.js";

import {
  view, toast, api, apiUrl, esc, fmt, loadFiles, fileOptions, UCS_FACTS, isHybridUi,
  destroyCharts, makeChart, CHART_COLORS, exportChartPng,
  profileQueryString, profileBarHtml, bindProfileBar,
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
  view.innerHTML = `<div class="loading">${t("msg.scanning")}</div>`;
  const [versions, files] = await Promise.all([
    api("/api/versions").then(d => d.versions),
    loadFiles(),
  ]);
  const maxKeys = Math.max(...versions.map(v => v.keys), 1);
  const uploads = files.filter(f => f.kind === "upload");
  const generated = files.filter(f => f.kind === "generated");
  const onDisk = versions.filter(v => v.available);
  const hybridBanner = isHybridUi() && onDisk.length === 0 ? `
    <div class="banner" style="margin-bottom:20px">
      <strong>Public API — no bundled game files.</strong>
      This Fly.io host does not ship copyrighted <code>.ucs</code> files.
      Built-in version cards appear only when files exist on the server disk.
      <a href="${routePath("upload")}">Upload your UCS</a> or run the CLI locally with your game install paths.
    </div>` : "";

  view.innerHTML = `
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
          <div class="stat-row"><span class="k">origin</span><span class="v">${esc(v.origin)}</span></div>
          <div class="stat-row"><span class="k">completeness</span><span class="v">${esc(v.completeness)}</span></div>
          ${v.available ? `<div class="btn-row"><a class="btn ghost small" href="${v.download_url}">${t("btn.download")}</a>
            <a class="btn ghost small" href="${routePath("upload", { file: v.id })}">${t("btn.analyze")}</a></div>` : ""}
        </div>`).join("")}
    </div>
    <h2 class="section-title" style="margin-top:38px">${t("route.stored_files")}</h2>
    <p class="section-sub">${uploads.length} upload(s), ${generated.length} generated.</p>
    ${files.length === 0 ? `<div class="empty"><span class="empty-icon">&#128194;</span>
        ${t("msg.empty_files")} <a href="${routePath("upload")}">${t("btn.upload_link")}</a>.</div>` : `
      <div class="table-wrap"><table class="data">
        <thead><tr><th>${t("table.kind")}</th><th>${t("table.name")}</th><th>${t("table.keys")}</th><th>${t("table.dups")}</th><th>${t("table.invalid")}</th><th></th></tr></thead>
        <tbody>${files.map(f => `
          <tr><td>${f.kind}</td><td class="val">${esc(f.name)}</td><td class="num">${fmt(f.keys)}</td>
            <td>${f.duplicates}</td><td>${f.invalid_lines}</td>
            <td><a href="${routePath("upload", { file: f.id })}">${t("table.analyze")}</a> · <a href="${apiUrl(`/api/downloads/${f.id}`)}">${t("table.dl")}</a>
            ${f.kind !== "version" ? ` · <a href="#" data-del="${f.id}" style="color:var(--red)">${t("table.del")}</a>` : ""}</td></tr>`).join("")}
        </tbody></table></div>`}
  `;
  view.querySelectorAll("[data-del]").forEach(a => a.addEventListener("click", async e => {
    e.preventDefault();
    await api(`/api/files/${a.dataset.del}`, { method: "DELETE" });
    toast(t("msg.deleted"));
    renderDashboard();
  }));
}

/* -------------------------------------------------------------- upload */
async function renderUpload(params) {
  view.innerHTML = `<div class="loading">${t("msg.preparing")}</div>`;
  const files = await loadFiles();
  const selected = params.get("file") || "";
  const savedProfile = sessionStorage.getItem("coh-last-profile") || "coh1";
  const savedStrict = sessionStorage.getItem("coh-strict-profile") === "true";
  view.innerHTML = `
    <h2 class="section-title">${t("route.upload")}</h2>
    <div class="grid cols-2">
      <div><div class="dropzone" id="dropzone"><span class="dz-icon">&#9738;</span>
        <p><strong>Drop .ucs here</strong></p><input type="file" id="file-input" accept=".ucs" hidden></div>
        <div class="card" style="margin-top:16px"><h3>Format</h3>
          ${UCS_FACTS.map(([k,v]) => `<div class="stat-row"><span class="k">${k}</span><span class="v">${esc(v)}</span></div>`).join("")}
        </div></div>
      <div><label class="field">Stored file<select id="file-select"><option value="">—</option>${fileOptions(files, selected)}</select></label>
        <label class="field" style="margin-top:12px">Expected game profile
          <select id="game-profile">
            <option value="coh1" ${savedProfile === "coh1" ? "selected" : ""}>CoH 1</option>
            <option value="coh2" ${savedProfile === "coh2" ? "selected" : ""}>CoH 2</option>
            <option value="dow1" ${savedProfile === "dow1" ? "selected" : ""}>Dawn of War</option>
            <option value="dow2" ${savedProfile === "dow2" ? "selected" : ""}>DoW II</option>
          </select>
        </label>
        <label class="toggle" style="margin-top:8px"><input type="checkbox" id="strict-profile" ${savedStrict ? "checked" : ""}> Reject mismatch</label>
        <div id="analysis"></div></div>
    </div>
    <div id="entries-panel" style="margin-top:30px"></div>`;
  document.getElementById("game-profile").onchange = e => {
    sessionStorage.setItem("coh-last-profile", e.target.value);
  };
  document.getElementById("strict-profile").onchange = e => {
    sessionStorage.setItem("coh-strict-profile", e.target.checked ? "true" : "false");
  };
  const dz = document.getElementById("dropzone"), input = document.getElementById("file-input");
  async function upload(file) {
    if (!file) return;
    const fd = new FormData(); fd.append("file", file);
    const profile = document.getElementById("game-profile")?.value || "coh1";
    const strict = document.getElementById("strict-profile")?.checked ? "true" : "false";
    const res = await api(`/api/files?game_profile=${profile}&strict_profile=${strict}`, { method: "POST", body: fd });
    toast(res.message);
    if (res.game_profile) {
      const gp = res.game_profile;
      sessionStorage.setItem("coh-last-profile", profile);
      sessionStorage.setItem("coh-strict-profile", strict);
      toast(`Classified as ${gp.best_match} (${Math.round(gp.confidence * 100)}%)`, 4000);
    }
    navigateRoute("upload", { file: res.file.id });
  }
  dz.onclick = () => input.click();
  input.onchange = () => upload(input.files[0]);
  ["dragover","dragleave","drop"].forEach(ev => dz.addEventListener(ev, e => {
    e.preventDefault(); dz.classList.toggle("drag", ev === "dragover");
    if (ev === "drop") upload(e.dataTransfer.files[0]);
  }));
  document.getElementById("file-select").onchange = e => {
    navigateRoute("upload", e.target.value ? { file: e.target.value } : undefined);
  };
  if (selected) await renderAnalysis(selected);
}

async function renderAnalysis(fileId) {
  const analysis = document.getElementById("analysis");
  analysis.innerHTML = `<div class="loading">${t("msg.parsing")}</div>`;
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
      <div class="banner" style="margin-top:10px;font-size:13px">
        <strong>Game profile:</strong> ${esc(gp.best_match)} (${Math.round(gp.confidence * 100)}% confidence)
        ${mismatch ? `<span class="bad"> — expected ${esc(expected)}</span>` : `<span class="good"> — matches selection</span>`}
        ${gp.warnings?.length ? `<ul style="margin:8px 0 0;padding-left:18px">${gp.warnings.map(w => `<li>${esc(w)}</li>`).join("")}</ul>` : ""}
      </div>`;
  }
  analysis.innerHTML = `
    <div class="card"><h3>${esc(f.name)}</h3>
      <div class="stat-row"><span class="k">keys</span><span class="v good">${fmt(f.keys)}</span></div>
      <div class="stat-row"><span class="k">validation</span><span class="v ${val.ok?'good':'bad'}">${val.ok?'OK':'FAIL'}</span></div>
      ${profileBlock}
      <div class="btn-row">
        <a class="btn ghost small" href="${routePath("validator", { file: f.id })}">${t("btn.validator")}</a>
        <a class="btn ghost small" href="${routePath("compare", { a: f.id })}">${t("btn.compare")}</a>
        <a class="btn ghost small" href="${routePath("games", { file: f.id })}">${t("btn.game_profiles")}</a>
      </div>
    </div>`;
  renderEntriesBrowser(fileId);
}

async function renderEntriesBrowser(fileId) {
  const panel = document.getElementById("entries-panel");
  panel.innerHTML = `<h2 class="section-title">${t("route.entries")}</h2>
    <div class="form-row"><input type="search" id="q" placeholder="id or text">
      <label class="toggle"><input type="checkbox" id="q-regex"> regex</label>
      <button class="btn small" id="q-go">${t("btn.search")}</button></div><div id="entries-out"></div>`;
  const state = { offset: 0, limit: 50 };
  const out = document.getElementById("entries-out");
  async function page() {
    const p = new URLSearchParams({ offset: state.offset, limit: state.limit });
    const q = document.getElementById("q");
    if (q.value) { p.set("search", q.value); p.set("regex", document.getElementById("q-regex").checked); }
    const data = await api(`/api/files/${fileId}/entries?${p}`);
    out.innerHTML = data.total ? `
      <div class="table-wrap"><table class="data"><tbody>
        ${data.entries.map(e => `<tr><td class="num">${e.key}</td><td class="val">${esc(e.value)}</td></tr>`).join("")}
      </tbody></table></div>
      <div class="pager"><button class="btn ghost small" id="prev" ${state.offset===0?"disabled":""}>&larr;</button>
        ${fmt(state.offset+1)}–${fmt(Math.min(state.offset+state.limit,data.total))} / ${fmt(data.total)}
        <button class="btn ghost small" id="next" ${state.offset+state.limit>=data.total?"disabled":""}>&rarr;</button></div>` :
      `<div class="empty">${t("msg.no_matches")}</div>`;
    out.querySelector("#prev")?.addEventListener("click", () => { state.offset = Math.max(0, state.offset - state.limit); page(); });
    out.querySelector("#next")?.addEventListener("click", () => { state.offset += state.limit; page(); });
  }
  document.getElementById("q-go").onclick = () => { state.offset = 0; page(); };
  page();
}

/* -------------------------------------------------------------- compare */
async function renderCompare(params) {
  view.innerHTML = `<div class="loading">${t("msg.loading")}</div>`;
  const files = await loadFiles();
  const a = params.get("a") || "", b = params.get("b") || "";
  view.innerHTML = `
    <h2 class="section-title">${t("route.compare")}</h2>
    ${profileBarHtml()}
    <div class="form-row">
      <label class="field">A<select id="sel-a"><option value="">—</option>${fileOptions(files,a)}</select></label>
      <label class="field">B<select id="sel-b"><option value="">—</option>${fileOptions(files,b)}</select></label>
      <button class="btn" id="go">${t("btn.compare")}</button>
      <a class="btn ghost" href="${routePath("diff", { a, b })}">${t("btn.diff_view")}</a>
      <a class="btn ghost" href="${routePath("ranges", { a, b })}">${t("btn.ranges")}</a>
    </div><div id="compare-out"></div>`;
  bindProfileBar(view);
  document.getElementById("go").onclick = () => {
    const va = document.getElementById("sel-a").value, vb = document.getElementById("sel-b").value;
    if (va && vb) navigateRoute("compare", { a: va, b: vb });
  };
  if (a && b) await runCompare(a, b);
}

async function runCompare(a, b) {
  const out = document.getElementById("compare-out");
  out.innerHTML = `<div class="loading">${t("msg.crunching")}</div>`;
  let d;
  try {
    d = await api(`/api/compare?a=${a}&b=${b}&${profileQueryString()}`);
  } catch (err) {
    out.innerHTML = `<div class="banner error">${esc(err.message)}</div>`;
    return;
  }
  const side = (s, label) => `
    <div class="card"><div class="card-header"><h3>${esc(s.name)}</h3><span class="kind-tag">${t("kind.side")} ${label}</span></div>
      <div class="keybar"><i style="width:${s.coverage_percent}%"></i></div>
      <div class="keybar-label">${s.coverage_percent}% coverage · ${fmt(s.missing_keys)} missing</div>
      ${s.missing_ranges.length ? `<details><summary>${s.missing_ranges.length} range(s)</summary>
        <div style="font-size:12px">${s.missing_ranges.map(esc).join(", ")}</div></details>` : ""}
    </div>`;
  out.innerHTML = `
    <div class="banner">union ${fmt(d.union_keys)} · common ${fmt(d.common_keys)}
      <button class="btn ghost small" onclick="exportChartPng('ch-overlap','overlap.png')">${t("btn.export_chart")}</button></div>
    <div class="grid cols-2">${side(d.a,"A")}${side(d.b,"B")}</div>
    <div class="grid cols-2" style="margin-top:18px">
      <div class="card"><div class="chart-box"><canvas id="ch-keys"></canvas></div></div>
      <div class="card"><div class="chart-box"><canvas id="ch-overlap"></canvas></div></div>
    </div>`;
  window.exportChartPng = exportChartPng;
  destroyCharts();
  try {
    await makeChart(document.getElementById("ch-keys"), {
      type: "bar", data: { labels: ["A","B"], datasets: [
        { label: "present", data: [d.a.total_keys, d.b.total_keys], backgroundColor: CHART_COLORS.olive },
        { label: "missing", data: [d.a.missing_keys, d.b.missing_keys], backgroundColor: CHART_COLORS.red },
      ]}, options: { maintainAspectRatio: false, responsive: true, scales: { x: { stacked: true }, y: { stacked: true } } },
    });
    await makeChart(document.getElementById("ch-overlap"), {
      type: "doughnut", data: { labels: ["common","only A","only B"],
        datasets: [{ data: [d.common_keys, d.b.missing_keys, d.a.missing_keys],
          backgroundColor: [CHART_COLORS.green, CHART_COLORS.amber, CHART_COLORS.red] }] },
      options: { maintainAspectRatio: false, responsive: true, cutout: "60%" },
    });
  } catch { /* Chart.js unavailable offline */ }
}

/* ---------------------------------------------------------------- merge */
async function renderMerge(params) {
  view.innerHTML = `<div class="loading">${t("msg.loading")}</div>`;
  const files = await loadFiles();
  view.innerHTML = `
    <h2 class="section-title">${t("route.merge")}</h2>
    <p class="section-sub">${t("route.merge.sub")}</p>
    ${profileBarHtml()}
    <div class="card" style="max-width:760px">
      <div class="form-row">
        <label class="field">Target<select id="m-target">${fileOptions(files, params.get("target")||"")}</select></label>
        <label class="field">Source<select id="m-source">${fileOptions(files, params.get("source")||"")}</select></label>
      </div>
      <div class="form-row">
        <label class="toggle"><input type="radio" name="mode" value="placeholder" checked> &lt;MISSING&gt;</label>
        <label class="toggle"><input type="radio" name="mode" value="fill_from_source"> fill verbatim</label>
      </div>
      <button class="btn" id="m-go">${t("btn.merge")}</button><div id="merge-out"></div>
    </div>`;
  bindProfileBar(view);
  document.getElementById("m-go").onclick = async () => {
    try {
    const r = await api(`/api/merge?${profileQueryString()}`, { method:"POST", headers:{"Content-Type":"application/json"},
      body: JSON.stringify({ target_id: document.getElementById("m-target").value,
        source_id: document.getElementById("m-source").value,
        mode: document.querySelector('input[name="mode"]:checked').value }) });
    document.getElementById("merge-out").innerHTML = `<div class="banner"><a href="${r.download_url}">Download ${esc(r.filename)}</a></div>`;
    } catch (err) { toast(err.message); }
  };
}

/* ---------------------------------------------------------------- tools */
async function renderTools() {
  const tools = (await api("/api/tools")).tools;
  view.innerHTML = `
    <h2 class="section-title">${t("route.tools")}</h2>
    <div class="grid cols-3">${tools.map(t => `
      <div class="card tool-card"><span class="cat">${esc(t.category)}</span>
        <h3><a href="${esc(t.url)}" target="_blank">${esc(t.name)}</a></h3><p>${esc(t.description)}</p></div>`).join("")}
    </div>
    <p style="margin-top:20px"><a href="${routePath("depots")}">Depots &amp; sources</a> · <a href="${apiUrl("/docs")}" target="_blank">API docs</a></p>`;
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
  const { name, params } = parseRoute();
  const handler = routes[name] || renderDashboard;
  const routeKey = routes[name] ? name : "dashboard";
  applyRouteSeo(routeKey);
  applyShellI18n();
  document.querySelectorAll("#nav a[data-route]").forEach(a =>
    a.classList.toggle("active", a.dataset.route === routeKey));
  try { await handler(params); }
  catch (err) { view.innerHTML = `<div class="banner error">${esc(err.message)}</div>`; }
}

window.addEventListener("popstate", route);
window.addEventListener("coh-route", route);
window.addEventListener("coh-i18n-changed", route);
initI18n().then(route);

window.addEventListener("coh-locale-click", () => { navigateRoute("languages"); });
