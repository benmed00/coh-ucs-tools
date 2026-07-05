/* CoH UCS Tools — SPA (hash routing, no build step). */

import {
  view, toast, api, apiUrl, esc, fmt, loadFiles, fileOptions, UCS_FACTS,
  destroyCharts, makeChart, CHART_COLORS, exportChartPng,
} from "./core.js";
import {
  initTheme, renderDiff, renderRanges, renderValidator, renderLanguages,
  renderMergeWizard, renderInstall, renderMtLab, renderGlossary,
  renderTimeline, renderDepots, renderSearch, renderBookmarks,
  renderPatch, renderSga, renderSettings, renderEditor,
  renderVerify, renderTranslation,
  renderCampaigns, renderGames,
} from "./features.js";

initTheme();

/* ------------------------------------------------------------ dashboard */
async function renderDashboard() {
  view.innerHTML = `<div class="loading">Scanning depots</div>`;
  const [versions, files] = await Promise.all([
    api("/api/versions").then(d => d.versions),
    loadFiles(),
  ]);
  const maxKeys = Math.max(...versions.map(v => v.keys), 1);
  const uploads = files.filter(f => f.kind === "upload");
  const generated = files.filter(f => f.kind === "generated");

  view.innerHTML = `
    <h2 class="section-title">DASHBOARD</h2>
    <p class="section-sub">Known Company of Heroes 1 <code>.ucs</code> versions registered on this server.</p>
    <div class="grid cols-2">
      ${versions.map(v => `
        <div class="card">
          <span class="kind-tag">${v.available ? "on disk" : "not found"}</span>
          <h3>${esc(v.name)}</h3>
          <div class="keybar"><i style="width:${v.available ? (100 * v.keys / maxKeys).toFixed(1) : 0}%"></i></div>
          <div class="keybar-label">${v.available ? fmt(v.keys) + " keys" : "file not present"}</div>
          <div class="stat-row"><span class="k">origin</span><span class="v">${esc(v.origin)}</span></div>
          <div class="stat-row"><span class="k">completeness</span><span class="v">${esc(v.completeness)}</span></div>
          ${v.available ? `<a class="btn ghost small" href="${v.download_url}">Download</a>
            <a class="btn ghost small" href="#/upload?file=${v.id}">Analyze</a>` : ""}
        </div>`).join("")}
    </div>
    <h2 class="section-title" style="margin-top:38px">STORED FILES</h2>
    <p class="section-sub">${uploads.length} upload(s), ${generated.length} generated.</p>
    ${files.length === 0 ? `<div class="empty"><span class="empty-icon">&#128194;</span>
        Nothing here — <a href="#/upload">Upload</a>.</div>` : `
      <div class="table-wrap"><table class="data">
        <thead><tr><th>kind</th><th>name</th><th>keys</th><th>dups</th><th>invalid</th><th></th></tr></thead>
        <tbody>${files.map(f => `
          <tr><td>${f.kind}</td><td class="val">${esc(f.name)}</td><td class="num">${fmt(f.keys)}</td>
            <td>${f.duplicates}</td><td>${f.invalid_lines}</td>
            <td><a href="#/upload?file=${f.id}">analyze</a> · <a href="${apiUrl(`/api/downloads/${f.id}`)}">dl</a>
            ${f.kind !== "version" ? ` · <a href="#" data-del="${f.id}" style="color:var(--red)">del</a>` : ""}</td></tr>`).join("")}
        </tbody></table></div>`}
  `;
  view.querySelectorAll("[data-del]").forEach(a => a.addEventListener("click", async e => {
    e.preventDefault();
    await api(`/api/files/${a.dataset.del}`, { method: "DELETE" });
    toast("Deleted");
    renderDashboard();
  }));
}

/* -------------------------------------------------------------- upload */
async function renderUpload(params) {
  view.innerHTML = `<div class="loading">Preparing</div>`;
  const files = await loadFiles();
  const selected = params.get("file") || "";
  view.innerHTML = `
    <h2 class="section-title">UPLOAD &amp; ANALYZE</h2>
    <div class="grid cols-2">
      <div><div class="dropzone" id="dropzone"><span class="dz-icon">&#9738;</span>
        <p><strong>Drop .ucs here</strong></p><input type="file" id="file-input" accept=".ucs" hidden></div>
        <div class="card" style="margin-top:16px"><h3>Format</h3>
          ${UCS_FACTS.map(([k,v]) => `<div class="stat-row"><span class="k">${k}</span><span class="v">${esc(v)}</span></div>`).join("")}
        </div></div>
      <div><label class="field">Stored file<select id="file-select"><option value="">—</option>${fileOptions(files, selected)}</select></label>
        <div id="analysis"></div></div>
    </div>
    <div id="entries-panel" style="margin-top:30px"></div>`;
  const dz = document.getElementById("dropzone"), input = document.getElementById("file-input");
  async function upload(file) {
    if (!file) return;
    const fd = new FormData(); fd.append("file", file);
    const res = await api("/api/files", { method: "POST", body: fd });
    toast(res.message);
    location.hash = `#/upload?file=${res.file.id}`;
  }
  dz.onclick = () => input.click();
  input.onchange = () => upload(input.files[0]);
  ["dragover","dragleave","drop"].forEach(ev => dz.addEventListener(ev, e => {
    e.preventDefault(); dz.classList.toggle("drag", ev === "dragover");
    if (ev === "drop") upload(e.dataTransfer.files[0]);
  }));
  document.getElementById("file-select").onchange = e => {
    location.hash = e.target.value ? `#/upload?file=${e.target.value}` : "#/upload";
  };
  if (selected) await renderAnalysis(selected);
}

async function renderAnalysis(fileId) {
  const analysis = document.getElementById("analysis");
  analysis.innerHTML = `<div class="loading">Parsing</div>`;
  const [f, val] = await Promise.all([
    api(`/api/files/${fileId}`), api(`/api/files/${fileId}/validate`),
  ]);
  analysis.innerHTML = `
    <div class="card"><h3>${esc(f.name)}</h3>
      <div class="stat-row"><span class="k">keys</span><span class="v good">${fmt(f.keys)}</span></div>
      <div class="stat-row"><span class="k">validation</span><span class="v ${val.ok?'good':'bad'}">${val.ok?'OK':'FAIL'}</span></div>
      <a class="btn ghost small" href="#/validator?file=${f.id}">Validator</a>
      <a class="btn ghost small" href="#/compare?a=${f.id}">Compare</a>
    </div>`;
  renderEntriesBrowser(fileId);
}

async function renderEntriesBrowser(fileId) {
  const panel = document.getElementById("entries-panel");
  panel.innerHTML = `<h2 class="section-title">ENTRIES</h2>
    <div class="form-row"><input type="search" id="q" placeholder="id or text">
      <label class="toggle"><input type="checkbox" id="q-regex"> regex</label>
      <button class="btn small" id="q-go">Search</button></div><div id="entries-out"></div>`;
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
      `<div class="empty">No matches — try regex or check for <code>$id No Key</code> gaps.</div>`;
    out.querySelector("#prev")?.addEventListener("click", () => { state.offset = Math.max(0, state.offset - state.limit); page(); });
    out.querySelector("#next")?.addEventListener("click", () => { state.offset += state.limit; page(); });
  }
  document.getElementById("q-go").onclick = () => { state.offset = 0; page(); };
  page();
}

/* -------------------------------------------------------------- compare */
async function renderCompare(params) {
  view.innerHTML = `<div class="loading">Loading</div>`;
  const files = await loadFiles();
  const a = params.get("a") || "", b = params.get("b") || "";
  view.innerHTML = `
    <h2 class="section-title">COMPARE</h2>
    <div class="form-row">
      <label class="field">A<select id="sel-a"><option value="">—</option>${fileOptions(files,a)}</select></label>
      <label class="field">B<select id="sel-b"><option value="">—</option>${fileOptions(files,b)}</select></label>
      <button class="btn" id="go">Compare</button>
      <a class="btn ghost" href="#/diff?a=${a}&b=${b}">Diff view</a>
      <a class="btn ghost" href="#/ranges?a=${a}&b=${b}">Ranges</a>
    </div><div id="compare-out"></div>`;
  document.getElementById("go").onclick = () => {
    const va = document.getElementById("sel-a").value, vb = document.getElementById("sel-b").value;
    if (va && vb) location.hash = `#/compare?a=${va}&b=${vb}`;
  };
  if (a && b) await runCompare(a, b);
}

async function runCompare(a, b) {
  const out = document.getElementById("compare-out");
  out.innerHTML = `<div class="loading">Crunching</div>`;
  const d = await api(`/api/compare?a=${a}&b=${b}`);
  const side = (s, label) => `
    <div class="card"><span class="kind-tag">side ${label}</span><h3>${esc(s.name)}</h3>
      <div class="keybar"><i style="width:${s.coverage_percent}%"></i></div>
      <div class="keybar-label">${s.coverage_percent}% coverage · ${fmt(s.missing_keys)} missing</div>
      ${s.missing_ranges.length ? `<details><summary>${s.missing_ranges.length} range(s)</summary>
        <div style="font-size:12px">${s.missing_ranges.map(esc).join(", ")}</div></details>` : ""}
    </div>`;
  out.innerHTML = `
    <div class="banner">union ${fmt(d.union_keys)} · common ${fmt(d.common_keys)}
      <button class="btn ghost small" onclick="exportChartPng('ch-overlap','overlap.png')">Export chart</button></div>
    <div class="grid cols-2">${side(d.a,"A")}${side(d.b,"B")}</div>
    <div class="grid cols-2" style="margin-top:18px">
      <div class="card"><div class="chart-box"><canvas id="ch-keys"></canvas></div></div>
      <div class="card"><div class="chart-box"><canvas id="ch-overlap"></canvas></div></div>
    </div>`;
  window.exportChartPng = exportChartPng;
  destroyCharts();
  if (window.Chart) {
    makeChart(document.getElementById("ch-keys"), {
      type: "bar", data: { labels: ["A","B"], datasets: [
        { label: "present", data: [d.a.total_keys, d.b.total_keys], backgroundColor: CHART_COLORS.olive },
        { label: "missing", data: [d.a.missing_keys, d.b.missing_keys], backgroundColor: CHART_COLORS.red },
      ]}, options: { maintainAspectRatio: false, responsive: true, scales: { x: { stacked: true }, y: { stacked: true } } },
    });
    makeChart(document.getElementById("ch-overlap"), {
      type: "doughnut", data: { labels: ["common","only A","only B"],
        datasets: [{ data: [d.common_keys, d.b.missing_keys, d.a.missing_keys],
          backgroundColor: [CHART_COLORS.green, CHART_COLORS.amber, CHART_COLORS.red] }] },
      options: { maintainAspectRatio: false, responsive: true, cutout: "60%" },
    });
  }
}

/* ---------------------------------------------------------------- merge */
async function renderMerge(params) {
  view.innerHTML = `<div class="loading">Loading</div>`;
  const files = await loadFiles();
  view.innerHTML = `
    <h2 class="section-title">MERGE</h2>
    <p class="section-sub">Quick merge — or use the <a href="#/merge-wizard">wizard</a> for preview.</p>
    <div class="card" style="max-width:760px">
      <div class="form-row">
        <label class="field">Target<select id="m-target">${fileOptions(files, params.get("target")||"")}</select></label>
        <label class="field">Source<select id="m-source">${fileOptions(files, params.get("source")||"")}</select></label>
      </div>
      <div class="form-row">
        <label class="toggle"><input type="radio" name="mode" value="placeholder" checked> &lt;MISSING&gt;</label>
        <label class="toggle"><input type="radio" name="mode" value="fill_from_source"> fill verbatim</label>
      </div>
      <button class="btn" id="m-go">Merge</button><div id="merge-out"></div>
    </div>`;
  document.getElementById("m-go").onclick = async () => {
    const r = await api("/api/merge", { method:"POST", headers:{"Content-Type":"application/json"},
      body: JSON.stringify({ target_id: document.getElementById("m-target").value,
        source_id: document.getElementById("m-source").value,
        mode: document.querySelector('input[name="mode"]:checked').value }) });
    document.getElementById("merge-out").innerHTML = `<div class="banner"><a href="${r.download_url}">Download ${esc(r.filename)}</a></div>`;
  };
}

/* ---------------------------------------------------------------- tools */
async function renderTools() {
  const tools = (await api("/api/tools")).tools;
  view.innerHTML = `
    <h2 class="section-title">TOOLS &amp; INTEL</h2>
    <div class="grid cols-3">${tools.map(t => `
      <div class="card tool-card"><span class="cat">${esc(t.category)}</span>
        <h3><a href="${esc(t.url)}" target="_blank">${esc(t.name)}</a></h3><p>${esc(t.description)}</p></div>`).join("")}
    </div>
    <p style="margin-top:20px"><a href="#/depots">Depots &amp; sources</a> · <a href="${apiUrl("/docs")}" target="_blank">API docs</a></p>`;
}

/* --------------------------------------------------------------- router */
const routes = {
  dashboard: renderDashboard,
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
  const hash = location.hash.slice(2) || "dashboard";
  const [name, query] = hash.split("?");
  const params = new URLSearchParams(query || "");
  const handler = routes[name] || renderDashboard;
  document.querySelectorAll("#nav a[data-route]").forEach(a =>
    a.classList.toggle("active", a.dataset.route === (routes[name] ? name : "dashboard")));
  try { await handler(params); }
  catch (err) { view.innerHTML = `<div class="banner error">${esc(err.message)}</div>`; }
}

window.addEventListener("hashchange", route);
route();

/* hero locale click → languages hub */
window.addEventListener("coh-locale-click", () => { location.hash = "#/languages"; });
