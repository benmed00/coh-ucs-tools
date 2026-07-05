/* Extended SPA sections — diff, languages, search, settings, etc. */

import { api, apiUrl, esc, fmt, loadFiles, fileOptions, fileLabel, toast, destroyCharts, makeChart, CHART_COLORS, profileQueryString, profileBarHtml, bindProfileBar } from "./core.js";
import { navigateRoute, routePath } from "./router.js";

export function highlightTokens(text) {
  return esc(text).replace(/(%\d[A-Za-z]*%)/g, '<mark class="token">$1</mark>');
}

export async function copyTable(btn, tableSel) {
  const table = btn.closest(".section")?.querySelector(tableSel) || document.querySelector(tableSel);
  if (!table) return;
  const rows = [...table.querySelectorAll("tr")].map(tr =>
    [...tr.cells].map(c => c.innerText).join("\t")
  ).join("\n");
  await navigator.clipboard.writeText(rows);
  toast("Copied to clipboard");
}

/* ------------------------------------------------------------------ diff */
export async function renderDiff(params) {
  const el = document.getElementById("view");
  el.innerHTML = `<div class="loading">Loading</div>`;
  const files = await loadFiles();
  const a = params.get("a") || "", b = params.get("b") || "", filter = params.get("filter") || "changed";
  el.innerHTML = `
    <h2 class="section-title">DIFF</h2>
    <p class="section-sub">Side-by-side entry diff with <code>%token%</code> highlighting.</p>
    <div class="form-row section">
      <label class="field">File A<select id="d-a"><option value="">—</option>${fileOptions(files, a)}</select></label>
      <label class="field">File B<select id="d-b"><option value="">—</option>${fileOptions(files, b)}</select></label>
      <label class="field">Filter<select id="d-f">
        ${["changed","missing","empty","token_mismatch"].map(f =>
          `<option value="${f}" ${f===filter?"selected":""}>${f}</option>`).join("")}
      </select></label>
      <button class="btn" id="d-go">Diff</button>
    </div>
    <div id="diff-out"></div>`;
  document.getElementById("d-go").onclick = () => {
    const va = document.getElementById("d-a").value, vb = document.getElementById("d-b").value;
    if (!va || !vb) { toast("Pick both files"); return; }
    navigateRoute("diff", { a: va, b: vb, filter: document.getElementById("d-f").value });
  };
  if (a && b) await runDiff(a, b, filter);
}

async function runDiff(a, b, filter) {
  const out = document.getElementById("diff-out");
  out.innerHTML = `<div class="loading">Diffing</div>`;
  const d = await api(`/api/files/${a}/diff/${b}?filter=${filter}&limit=200`);
  out.innerHTML = `
    <div class="banner">${fmt(d.total)} row(s) · filter <code>${esc(filter)}</code>
      <button class="btn ghost small copy-btn" style="margin-left:10px">Copy table</button></div>
    <div class="table-wrap"><table class="data" id="diff-table">
      <thead><tr><th>id</th><th>kind</th><th>A</th><th>B</th></tr></thead>
      <tbody>${d.rows.map(r => `<tr>
        <td class="num">${r.key}</td><td>${esc(r.kind)}</td>
        <td class="val">${r.a_value != null ? highlightTokens(r.a_value) : '<em>—</em>'}</td>
        <td class="val">${r.b_value != null ? highlightTokens(r.b_value) : '<em>—</em>'}</td>
      </tr>`).join("")}</tbody></table></div>`;
  out.querySelector(".copy-btn")?.addEventListener("click", e => copyTable(e.target, "#diff-table"));
}

/* --------------------------------------------------------------- ranges */
export async function renderRanges(params) {
  const el = document.getElementById("view");
  el.innerHTML = `<div class="loading">Loading</div>`;
  const files = await loadFiles();
  const a = params.get("a") || "", b = params.get("b") || "";
  el.innerHTML = `
    <h2 class="section-title">MISSING RANGES</h2>
    <p class="section-sub">Heatmap of missing ID blocks — click a bucket to look up entries.
       Empty gaps render in-game as <code>$id No Key</code>.</p>
    <div class="form-row">
      <label class="field">A<select id="r-a">${fileOptions(files, a)}</select></label>
      <label class="field">B<select id="r-b">${fileOptions(files, b)}</select></label>
      <button class="btn" id="r-go">Load</button>
    </div>
    <div id="ranges-out"></div>`;
  document.getElementById("r-go").onclick = () => {
    navigateRoute("ranges", { a: document.getElementById("r-a").value, b: document.getElementById("r-b").value });
  };
  if (a && b) await loadRanges(a, b);
}

async function loadRanges(a, b) {
  const out = document.getElementById("ranges-out");
  const d = await api(`/api/compare/${a}/${b}/ranges`);
  const bar = (segments, label, fileId) => {
    const max = Math.max(...segments.map(s => s.count), 1);
    return `<div class="card"><h3>Missing in ${esc(label)}</h3>
      ${segments.length ? segments.map(s => `
        <div class="range-bar" data-file="${fileId}" data-start="${s.start}" data-end="${s.end}" title="${s.start}–${s.end}: ${s.count}">
          <i style="width:${(100*s.count/max).toFixed(1)}%"></i>
          <span>${s.start}–${s.end} (${s.count})</span>
        </div>`).join("") : `<p class="keybar-label" style="color:var(--green)">Full coverage</p>`}
    </div>`;
  };
  out.innerHTML = `<div class="grid cols-2">${bar(d.a_missing,"A",a)}${bar(d.b_missing,"B",b)}</div>
    <div id="range-lookup"></div>`;
  out.querySelectorAll(".range-bar").forEach(barEl => barEl.addEventListener("click", async () => {
    const fid = barEl.dataset.file;
    const p = new URLSearchParams({ search: barEl.dataset.start, limit: 20 });
    const entries = await api(`/api/files/${fid}/entries?${p}`);
    document.getElementById("range-lookup").innerHTML = `
      <h3 class="section-title" style="margin-top:20px">Lookup ${barEl.dataset.start}–${barEl.dataset.end}</h3>
      <div class="table-wrap"><table class="data"><tbody>
        ${entries.entries.map(e => `<tr><td class="num">${e.key}</td><td class="val">${esc(e.value)}</td></tr>`).join("")}
      </tbody></table></div>`;
  }));
}

/* ------------------------------------------------------------ validator */
export async function renderValidator(params) {
  const el = document.getElementById("view");
  const files = await loadFiles();
  const fid = params.get("file") || "";
  el.innerHTML = `
    <h2 class="section-title">VALIDATOR</h2>
    <p class="section-sub">Script detection, MISSING literals, duplicates, invalid lines.</p>
    <label class="field">File<select id="v-file"><option value="">—</option>${fileOptions(files, fid)}</select></label>
    <div id="v-out"></div>`;
  document.getElementById("v-file").onchange = () => {
    const v = document.getElementById("v-file").value;
    if (v) navigateRoute("validator", { file: v });
  };
  if (fid) await loadValidator(fid);
}

async function loadValidator(fid) {
  const out = document.getElementById("v-out");
  out.innerHTML = `<div class="loading">Validating</div>`;
  const [val, lint, issues] = await Promise.all([
    api(`/api/files/${fid}/validate`),
    api(`/api/files/${fid}/lint`),
    api(`/api/files/${fid}/issues`),
  ]);
  out.innerHTML = `
    <div class="grid cols-2">
      <div class="card"><h3>Validation</h3>
        <div class="stat-row"><span class="k">status</span><span class="v ${val.ok?'good':'bad'}">${val.ok?'OK':'FAILED'}</span></div>
        <div class="stat-row"><span class="k">errors</span><span class="v">${val.errors}</span></div>
        <div class="stat-row"><span class="k">warnings</span><span class="v">${val.warnings}</span></div>
        <a class="btn ghost small" href="${apiUrl(`/api/files/${fid}/issues.csv`)}">Export CSV</a>
      </div>
      <div class="card"><h3>Lint</h3>
        <div class="stat-row"><span class="k">token issues</span><span class="v">${lint.token_issue_count}</span></div>
        <div class="stat-row"><span class="k">script findings</span><span class="v">${lint.script_finding_count}</span></div>
        <div class="stat-row"><span class="k">entries w/ issues</span><span class="v">${lint.entries_with_issues}</span></div>
      </div>
    </div>
    <div class="table-wrap" style="margin-top:16px"><table class="data">
      <thead><tr><th>type</th><th>key</th><th>detail</th></tr></thead>
      <tbody>
        ${issues.duplicates.map(d => `<tr><td>duplicate</td><td class="num">${d.key}</td><td>lines ${d.lines.join(", ")}</td></tr>`).join("")}
        ${issues.invalid_lines.map(l => `<tr><td>invalid</td><td>${l.line}</td><td>${esc(l.reason)}</td></tr>`).join("")}
      </tbody></table></div>`;
}

/* ------------------------------------------------------------- languages */
export async function renderLanguages() {
  const el = document.getElementById("view");
  el.innerHTML = `<div class="loading">Loading hub</div>`;
  const [d, cov] = await Promise.all([api("/api/languages"), api("/api/languages/coverage")]);
  const covMap = Object.fromEntries((cov.locales || []).map(r => [r.code, r]));
  el.innerHTML = `
    <h2 class="section-title">LANGUAGES</h2>
    <p class="section-sub">Coverage vs reference (${fmt(d.reference_keys)} keys).
      <a href="${apiUrl("/api/languages/coverage.csv")}" class="btn ghost small" style="margin-left:8px">Export CSV</a>
    </p>
    <div class="card" style="margin-bottom:16px">
      <h3 style="font-size:14px;margin:0 0 8px">Coverage comparison</h3>
      <div class="chart-box" style="height:220px"><canvas id="cov-bar"></canvas></div>
    </div>
    <div class="table-wrap" style="margin-bottom:16px">
      <table class="data"><thead><tr>
        <th>code</th><th>found</th><th>keys</th><th>coverage</th><th>missing</th><th>placeholders</th><th>gaps</th>
      </tr></thead><tbody>
        ${(cov.locales || []).map(r => `<tr>
          <td>${esc(r.code)}</td>
          <td>${r.found ? "yes" : "—"}</td>
          <td class="num">${fmt(r.keys)}</td>
          <td>${r.coverage_percent}%</td>
          <td class="num">${fmt(r.missing_vs_reference)}</td>
          <td class="num">${fmt(r.placeholders)}</td>
          <td class="num">${r.gap_range_count}</td>
        </tr>`).join("")}
      </tbody></table>
    </div>
    <div class="grid cols-2">${d.languages.map(l => {
      const extra = covMap[l.code];
      return `
      <div class="card">
        <div class="card-header">
          <h3>${esc(l.code)} — ${esc(l.name)}</h3>
          <span class="kind-tag">${esc(l.source_badge)}</span>
        </div>
        <div class="chart-box" style="height:140px"><canvas id="donut-${l.code}"></canvas></div>
        <div class="stat-row"><span class="k">keys</span><span class="v">${fmt(l.keys)}</span></div>
        <div class="stat-row"><span class="k">coverage</span><span class="v">${l.coverage_percent}%</span></div>
        ${extra && extra.found ? `<div class="stat-row"><span class="k">missing vs RU</span><span class="v">${fmt(extra.missing_vs_reference)}</span></div>
        <div class="stat-row"><span class="k">placeholders</span><span class="v">${fmt(extra.placeholders)}</span></div>` : ""}
        <p style="font-size:13px;color:var(--text-dim)">${esc(l.notes)}</p>
        ${l.download_url ? `<a class="btn ghost small" href="${l.download_url}">Download</a>` : ""}
      </div>`;
    }).join("")}</div>`;
  destroyCharts();
  try {
    const labels = (cov.locales || []).filter(r => r.found).map(r => r.code);
    const data = (cov.locales || []).filter(r => r.found).map(r => r.coverage_percent);
    const bar = document.getElementById("cov-bar");
    if (bar && labels.length) {
      await makeChart(bar, {
        type: "bar",
        data: { labels, datasets: [{ label: "coverage %", data, backgroundColor: CHART_COLORS.olive }] },
        options: { maintainAspectRatio: false, scales: { y: { max: 100, beginAtZero: true } }, plugins: { legend: { display: false } } },
      });
    }
    for (const l of d.languages) {
      const ctx = document.getElementById(`donut-${l.code}`);
      if (!ctx) continue;
      await makeChart(ctx, {
        type: "doughnut",
        data: { labels: ["covered","gap"], datasets: [{ data: [l.coverage_percent, 100-l.coverage_percent],
          backgroundColor: [CHART_COLORS.green, CHART_COLORS.dim], borderColor: "transparent" }] },
        options: { maintainAspectRatio: false, plugins: { legend: { display: false } }, cutout: "65%" },
      });
    }
  } catch { /* Chart.js unavailable offline */ }
}

/* ---------------------------------------------------------- merge wizard */
export async function renderMergeWizard(params) {
  const el = document.getElementById("view");
  const files = await loadFiles();
  const tab = params.get("tab") || "twoway";
  el.innerHTML = `
    <h2 class="section-title">MERGE WIZARD</h2>
    <p class="section-sub">Two-way or three-way merge — nothing translated, originals untouched.</p>
    ${profileBarHtml()}
    <div class="form-row" style="margin-bottom:12px">
      <a class="btn ghost small ${tab==="twoway"?"active":""}" href="${routePath("merge-wizard", { tab: "twoway" })}">Two-way</a>
      <a class="btn ghost small ${tab==="threeway"?"active":""}" href="${routePath("merge-wizard", { tab: "threeway" })}">Three-way</a>
    </div>
    <div id="mw-panel"></div>`;
  bindProfileBar(el);
  if (tab === "threeway") await renderThreewayPanel(files, params);
  else await renderTwowayPanel(files, params);
}

async function renderTwowayPanel(files, params) {
  document.getElementById("mw-panel").innerHTML = `
    <div class="card" style="max-width:800px">
      <div class="form-row">
        <label class="field">1. Target<select id="mw-t">${fileOptions(files, params.get("target")||"")}</select></label>
        <label class="field">2. Source<select id="mw-s">${fileOptions(files, params.get("source")||"")}</select></label>
      </div>
      <div class="form-row">
        <label class="toggle"><input type="radio" name="mw-m" value="placeholder" checked> placeholders</label>
        <label class="toggle"><input type="radio" name="mw-m" value="fill_from_source"> fill verbatim</label>
        <button class="btn ghost" id="mw-preview">3. Preview</button>
        <button class="btn" id="mw-run">Merge</button>
      </div>
      <div id="mw-out"></div>
    </div>`;
  document.getElementById("mw-preview").onclick = async () => {
    const out = document.getElementById("mw-out");
    out.innerHTML = `<div class="loading">Preview</div>`;
    const mode = document.querySelector('input[name="mw-m"]:checked').value;
    const r = await api(`/api/merge/preview?${profileQueryString()}`, { method: "POST", headers: {"Content-Type":"application/json"},
      body: JSON.stringify({ target_id: document.getElementById("mw-t").value, source_id: document.getElementById("mw-s").value, mode, limit: 30 }) });
    out.innerHTML = `<div class="banner">Would add ${fmt(r.total_would_add)} id(s)</div>
      <div class="table-wrap"><table class="data"><thead><tr><th>id</th><th>source</th><th>result</th></tr></thead>
      <tbody>${r.preview.map(p => `<tr><td class="num">${p.key}</td><td class="val">${esc(p.source_value||"")}</td><td class="val">${esc(p.result_value)}</td></tr>`).join("")}</tbody></table></div>`;
  };
  document.getElementById("mw-run").onclick = async () => {
    const mode = document.querySelector('input[name="mw-m"]:checked').value;
    const r = await api(`/api/merge?${profileQueryString()}`, { method: "POST", headers: {"Content-Type":"application/json"},
      body: JSON.stringify({ target_id: document.getElementById("mw-t").value, source_id: document.getElementById("mw-s").value, mode }) });
    toast("Merge complete");
    document.getElementById("mw-out").innerHTML = `<div class="banner"><a href="${r.download_url}">Download ${esc(r.filename)}</a></div>`;
  };
}

async function renderThreewayPanel(files, params) {
  document.getElementById("mw-panel").innerHTML = `
    <div class="card" style="max-width:900px">
      <p class="section-sub">Base + branch A + branch B (e.g. THQ retail vs NSV vs CE).</p>
      <div class="form-row">
        <label class="field">Base<select id="3w-b">${fileOptions(files, params.get("base")||"")}</select></label>
        <label class="field">Branch A<select id="3w-a">${fileOptions(files, params.get("a")||"")}</select></label>
        <label class="field">Branch B<select id="3w-b2">${fileOptions(files, params.get("b")||"")}</select></label>
      </div>
      <div class="form-row">
        <label class="field">Strategy<select id="3w-s">
          <option value="prefer_a">prefer A</option>
          <option value="prefer_b">prefer B</option>
          <option value="manual_conflicts">list conflicts</option>
        </select></label>
        <button class="btn" id="3w-go">Three-way merge</button>
      </div>
      <div id="3w-out"></div>
    </div>`;
  document.getElementById("3w-go").onclick = async () => {
    const out = document.getElementById("3w-out");
    out.innerHTML = `<div class="loading">Merging</div>`;
    const body = {
      base_id: document.getElementById("3w-b").value,
      a_id: document.getElementById("3w-a").value,
      b_id: document.getElementById("3w-b2").value,
      strategy: document.getElementById("3w-s").value,
    };
    if (!body.base_id || !body.a_id || !body.b_id) { toast("Pick all three files"); return; }
    const r = await api("/api/merge/threeway", { method: "POST", body: JSON.stringify(body) });
    out.innerHTML = `
      <div class="banner"><a href="${r.download_url}">Download merged (${fmt(r.keys)} keys)</a>
        · ${r.conflicts.length} conflict(s)</div>
      ${r.conflicts.length ? `<div class="table-wrap"><table class="data"><thead><tr><th>id</th><th>base</th><th>A</th><th>B</th></tr></thead>
        <tbody>${r.conflicts.slice(0,50).map(c => `<tr><td class="num">${c.key}</td>
          <td class="val">${esc(c.base||"—")}</td><td class="val">${esc(c.a||"—")}</td><td class="val">${esc(c.b||"—")}</td></tr>`).join("")}
        </tbody></table></div>` : ""}`;
  };
}

/* --------------------------------------------------------------- install */
export async function renderInstall() {
  const el = document.getElementById("view");
  el.innerHTML = `<h2 class="section-title">INSTALL DETECT</h2>
    <button class="btn" id="inst-go">Scan known paths</button><div id="inst-out"></div>`;
  document.getElementById("inst-go").onclick = async () => {
    const d = await api("/api/install/detect");
    document.getElementById("inst-out").innerHTML = `
      <div class="grid cols-2" style="margin-top:16px">${d.candidates.map(c => `
        <div class="card"><h3>${esc(c.install_type)}</h3>
          <div class="stat-row"><span class="k">found</span><span class="v ${c.exists?'good':'bad'}">${c.exists?'yes':'no'}</span></div>
          ${c.ucs_path ? `<div class="stat-row"><span class="k">ucs</span><span class="v" style="font-size:11px">${esc(c.ucs_path)}</span></div>` : ""}
        </div>`).join("")}</div>
      <div class="card" style="margin-top:16px"><h3>PowerShell</h3>
        <pre class="mono-block">${esc(d.backup_command)}\n${esc(d.copy_command)}</pre>
        <button class="btn ghost small" id="copy-ps">Copy commands</button></div>`;
    document.getElementById("copy-ps").onclick = () => {
      navigator.clipboard.writeText(`${d.backup_command}\n${d.copy_command}`);
      toast("Copied");
    };
  };
}

/* ---------------------------------------------------------------- mt lab */
export async function renderMtLab() {
  const el = document.getElementById("view");
  const files = await loadFiles();
  el.innerHTML = `
    <h2 class="section-title">MT LAB</h2>
    <p class="section-sub">Queue machine-translation QA jobs (never written to game files).</p>
    <div class="form-row">
      <label class="field">Source<select id="mt-s">${fileOptions(files,"")}</select></label>
      <label class="field">sl<input id="mt-sl" value="ru"></label>
      <label class="field">tl<input id="mt-tl" value="en"></label>
      <label class="field">limit<input id="mt-lim" type="number" value="20"></label>
      <button class="btn" id="mt-q">Queue</button>
    </div>
    <div id="mt-status"></div><div id="mt-report"></div>`;
  async function poll() {
    const s = await api("/api/mt/status");
    document.getElementById("mt-status").innerHTML = `
      <div class="banner">${esc(s.status)} — ${s.progress}/${s.total} ${esc(s.message)}</div>
      <div class="keybar"><i style="width:${s.total ? 100*s.progress/s.total : 0}%"></i></div>`;
    if (s.status === "done") {
      const r = await api("/api/mt/report");
      document.getElementById("mt-report").innerHTML = `
        <div class="table-wrap"><table class="data"><thead><tr><th>id</th><th>source</th><th>MT</th><th>ref</th></tr></thead>
        <tbody>${(r.rows||[]).slice(0,50).map(row => `<tr>
          <td class="num">${row.key}</td><td class="val">${esc(row.source)}</td>
          <td class="val">${esc(row.mt)}</td><td class="val">${esc(row.reference)}</td></tr>`).join("")}
        </tbody></table></div>`;
    } else if (s.status === "running") setTimeout(poll, 2000);
  }
  document.getElementById("mt-q").onclick = async () => {
    await api("/api/mt/queue", { method:"POST", headers:{"Content-Type":"application/json"},
      body: JSON.stringify({ source_id: document.getElementById("mt-s").value,
        sl: document.getElementById("mt-sl").value, tl: document.getElementById("mt-tl").value,
        limit: +document.getElementById("mt-lim").value }) });
    poll();
  };
  poll();
}

/* -------------------------------------------------------------- glossary */
export async function renderGlossary() {
  const el = document.getElementById("view");
  const d = await api("/api/glossary");
  const rows = Object.entries(d.terms);
  el.innerHTML = `
    <h2 class="section-title">GLOSSARY</h2>
    <div class="table-wrap"><table class="data" id="gl-table">
      <thead><tr><th>term</th><th>fixed translation</th><th></th></tr></thead>
      <tbody>${rows.map(([k,v]) => `<tr><td><input value="${esc(k)}" class="gl-k"></td>
        <td><input value="${esc(v)}" class="gl-v"></td><td><button class="btn ghost small gl-rm">×</button></td></tr>`).join("")}
      </tbody></table></div>
    <button class="btn ghost" id="gl-add">Add row</button>
    <button class="btn" id="gl-save">Save</button>`;
  document.getElementById("gl-add").onclick = () => {
    document.querySelector("#gl-table tbody").insertAdjacentHTML("beforeend",
      `<tr><td><input class="gl-k"></td><td><input class="gl-v"></td><td><button class="btn ghost small gl-rm">×</button></td></tr>`);
  };
  document.getElementById("gl-save").onclick = async () => {
    const terms = {};
    document.querySelectorAll("#gl-table tbody tr").forEach(tr => {
      const k = tr.querySelector(".gl-k").value.trim();
      const v = tr.querySelector(".gl-v").value.trim();
      if (k) terms[k] = v;
    });
    await api("/api/glossary", { method:"PUT", headers:{"Content-Type":"application/json"}, body: JSON.stringify({ terms }) });
    toast("Glossary saved");
  };
  document.getElementById("gl-table").addEventListener("click", e => {
    if (e.target.classList.contains("gl-rm")) e.target.closest("tr").remove();
  });
}

/* -------------------------------------------------------------- timeline */
export async function renderTimeline() {
  const d = await api("/api/versions/timeline");
  document.getElementById("view").innerHTML = `
    <h2 class="section-title">TIMELINE</h2>
    <div class="timeline">${d.entries.map(e => `
      <div class="timeline-item ${e.available?'':'dim'}">
        <div class="tl-era">${esc(e.era)}</div>
        <h3>${esc(e.name)}</h3>
        <div class="stat-row"><span class="k">keys</span><span class="v">${fmt(e.keys)}</span></div>
        <p style="font-size:13px;color:var(--text-dim)">${esc(e.notes)}</p>
      </div>`).join("")}</div>`;
}

/* -------------------------------------------------------- depots/sources */
export async function renderDepots() {
  const [dep, src] = await Promise.all([api("/api/depots"), api("/api/sources")]);
  const dd = dep.depotdownloader ? `Found: ${esc(dep.depotdownloader)}` : "DepotDownloader not on PATH — manual commands only";
  document.getElementById("view").innerHTML = `
    <h2 class="section-title">DEPOTS &amp; SOURCES</h2>
    <p class="muted" style="margin-bottom:12px">${dd}. Automated download uses server env <code>STEAM_USERNAME</code> / <code>STEAM_PASSWORD</code>.</p>
    <div class="grid cols-2">
      <div><h3 class="section-title" style="font-size:16px">Depots</h3>
        ${dep.depots.map(d => `<div class="card" data-lang="${esc(d.language.toLowerCase())}"><h3>${esc(d.language)} (app ${d.app_id})</h3>
          <p>${esc(d.description)}</p><pre class="mono-block">${esc(d.command_template)}</pre>
          <p class="muted" style="font-size:12px">→ ${esc(d.expected_file || "")}</p>
          <div class="form-row" style="margin-top:10px">
            <button class="btn small depot-dl" ${dep.depotdownloader ? "" : "disabled"}>Download</button>
            <button class="btn ghost small depot-build" ${d.build_script ? "" : "disabled"}>Import &amp; build</button>
          </div>
          <div class="depot-out" style="font-size:12px;margin-top:8px"></div></div>`).join("")}
      </div>
      <div><h3 class="section-title" style="font-size:16px">Sources</h3>
        ${src.sources.map(s => `<div class="card tool-card"><span class="cat">${esc(s.trust)}</span>
          <h3><a href="${esc(s.url)}" target="_blank">${esc(s.name)}</a></h3><p>${esc(s.description)}</p></div>`).join("")}
      </div>
    </div>`;
  document.querySelectorAll(".depot-dl").forEach(btn => {
    btn.onclick = async () => {
      const card = btn.closest(".card");
      const lang = card.dataset.lang;
      const out = card.querySelector(".depot-out");
      out.textContent = "Downloading…";
      try {
        const r = await api("/api/depot/download", { method: "POST", headers: {"Content-Type":"application/json"},
          body: JSON.stringify({ language: lang, build: true }) });
        if (r.download && r.download.success) {
          out.innerHTML = `OK — <code>${esc(r.download.dest)}</code> (${r.download.bytes} bytes)`;
          if (r.build) out.innerHTML += r.build.built ? " · build OK" : " · build failed";
        } else {
          out.textContent = r.error || r.stderr_tail || "Download failed";
        }
      } catch (e) { out.textContent = e.message; }
    };
  });
  document.querySelectorAll(".depot-build").forEach(btn => {
    btn.onclick = async () => {
      const card = btn.closest(".card");
      const lang = card.dataset.lang;
      const out = card.querySelector(".depot-out");
      out.textContent = "Building…";
      try {
        const r = await api("/api/depot/import", { method: "POST", headers: {"Content-Type":"application/json"},
          body: JSON.stringify({ language: lang }) });
        out.textContent = r.built ? `Built ${r.version_id || lang}` : (r.stderr || "Build failed — place NSV in downloads/");
      } catch (e) { out.textContent = e.message; }
    };
  });
}

/* ---------------------------------------------------------------- search */
export async function renderSearch(params) {
  const el = document.getElementById("view");
  const q = params.get("q") || "";
  el.innerHTML = `
    <h2 class="section-title">SEARCH</h2>
    <div class="form-row">
      <label class="field" style="flex:2"><input id="sq" value="${esc(q)}" placeholder="query"></label>
      <label class="toggle"><input type="checkbox" id="sq-fuzzy"> fuzzy</label>
      <label class="toggle"><input type="checkbox" id="sq-regex"> regex</label>
      <button class="btn" id="sq-go">Search</button>
    </div>
    <div id="search-out"></div>
    <div id="xref-out"></div>`;
  document.getElementById("sq-go").onclick = () => runSearch();
  if (q) runSearch();
  async function runSearch() {
    const query = document.getElementById("sq").value;
    navigateRoute("search", { q: query });
    const p = new URLSearchParams({ q: query });
    if (document.getElementById("sq-fuzzy").checked) p.set("fuzzy", "true");
    if (document.getElementById("sq-regex").checked) p.set("regex", "true");
    const d = await api(`/api/search/global?${p}`);
    document.getElementById("search-out").innerHTML = `
      <div class="table-wrap"><table class="data"><thead><tr><th>file</th><th>id</th><th>text</th><th>score</th></tr></thead>
      <tbody>${d.hits.map(h => `<tr data-key="${h.key}">
        <td>${esc(h.file_name)}</td><td class="num"><a href="#" class="xref-link">${h.key}</a></td>
        <td class="val">${esc(h.value)}</td><td>${h.score ?? ""}</td></tr>`).join("")}
      </tbody></table></div>`;
    document.querySelectorAll(".xref-link").forEach(a => a.addEventListener("click", async e => {
      e.preventDefault();
      const key = a.textContent;
      const x = await api(`/api/crossref/${key}`);
      document.getElementById("xref-out").innerHTML = `
        <h3>Cross-ref id ${key}</h3><div class="table-wrap"><table class="data"><thead><tr><th>file</th><th>value</th><th>sim</th></tr></thead>
        <tbody>${x.versions.map(v => `<tr><td>${esc(v.file_name)}</td><td class="val">${esc(v.value||"")}</td><td>${v.similarity}</td></tr>`).join("")}
        </tbody></table></div>`;
    }));
  }
}

/* ------------------------------------------------------------- bookmarks */
export async function renderBookmarks() {
  const el = document.getElementById("view");
  const d = await api("/api/bookmarks");
  el.innerHTML = `
    <h2 class="section-title">BOOKMARKS</h2>
    <p class="section-sub">Quick QA list of entry ids (e.g. known-bad <code>559200</code>).</p>
    <div class="form-row">
      <input id="bm-add" placeholder="numeric id">
      <button class="btn" id="bm-go">Add</button>
    </div>
    <ul class="bm-list">${d.ids.map(id => `<li>${id} <button data-rm="${id}" class="btn ghost small">remove</button></li>`).join("")}</ul>`;
  document.getElementById("bm-go").onclick = async () => {
    const id = +document.getElementById("bm-add").value;
    if (!id) return;
    await api("/api/bookmarks", { method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify({ ids: [id] }) });
    renderBookmarks();
  };
  el.querySelectorAll("[data-rm]").forEach(b => b.onclick = async () => {
    await api(`/api/bookmarks/${b.dataset.rm}`, { method:"DELETE" });
    renderBookmarks();
  });
}

/* ---------------------------------------------------------- patch builder */
export async function renderPatch(params) {
  const files = await loadFiles();
  const mode = params.get("mode") || "build";
  document.getElementById("view").innerHTML = `
    <h2 class="section-title">PATCH BUILDER</h2>
    <div class="form-row" style="margin-bottom:12px">
      <a class="btn ghost small ${mode==="build"?"active":""}" href="${routePath("patch", { mode: "build" })}">Build subset</a>
      <a class="btn ghost small ${mode==="apply"?"active":""}" href="${routePath("patch", { mode: "apply" })}">Apply patch</a>
    </div>
    <div id="pb-panel"></div>`;
  if (mode === "apply") {
    document.getElementById("pb-panel").innerHTML = `
      <p class="section-sub">Overlay a patch UCS onto a base file (changed + new keys).</p>
      <div class="form-row">
        <label class="field">Base<select id="pa-b">${fileOptions(files, params.get("base")||"")}</select></label>
        <label class="field">Patch<select id="pa-p">${fileOptions(files, params.get("patch")||"")}</select></label>
        <button class="btn" id="pa-go">Apply</button>
      </div>
      <div id="pa-out"></div>`;
    document.getElementById("pa-go").onclick = async () => {
      const r = await api("/api/patch/apply", { method:"POST", headers:{"Content-Type":"application/json"},
        body: JSON.stringify({ base_id: document.getElementById("pa-b").value, patch_id: document.getElementById("pa-p").value }) });
      document.getElementById("pa-out").innerHTML = `<div class="banner">
        <a href="${r.download_url}">Download patched (${r.keys} keys)</a>
        · ${r.changed} changed · ${r.added} added</div>`;
    };
    return;
  }
  document.getElementById("pb-panel").innerHTML = `
    <div class="form-row">
      <label class="field">File<select id="pb-f">${fileOptions(files, params.get("file")||"")}</select></label>
      <label class="field">Ranges<input id="pb-r" placeholder="559200-559650" value="${esc(params.get("ranges")||"")}"></label>
      <button class="btn" id="pb-go">Build subset</button>
    </div>
    <div id="pb-out"></div>`;
  document.getElementById("pb-go").onclick = async () => {
    const r = await api("/api/patch/build", { method:"POST", headers:{"Content-Type":"application/json"},
      body: JSON.stringify({ file_id: document.getElementById("pb-f").value,
        ranges: document.getElementById("pb-r").value.split(/[,\s]+/).filter(Boolean) }) });
    document.getElementById("pb-out").innerHTML = `<div class="banner"><a href="${r.download_url}">Download patch (${r.keys} keys)</a></div>`;
  };
}

/* ---------------------------------------------------------- campaign map */
export async function renderCampaigns() {
  const el = document.getElementById("view");
  const d = await api("/api/campaigns/ranges");
  el.innerHTML = `
    <h2 class="section-title">CAMPAIGN RANGES</h2>
    <p class="section-sub">Approximate CoH1 id namespaces — use with patch builder / search.</p>
    <div class="grid cols-2">${Object.entries(d.campaigns).map(([pack, ranges]) => `
      <div class="card"><h3>${esc(pack.replace(/_/g, " "))}</h3>
        <div class="table-wrap"><table class="data"><thead><tr><th>name</th><th>range</th><th></th></tr></thead>
        <tbody>${ranges.map(r => `<tr>
          <td>${esc(r.name)}</td><td class="num">${r.start}–${r.end}</td>
          <td><a href="${routePath("patch", { mode: "build", ranges: `${r.start}-${r.end}` })}">patch</a></td>
        </tr>`).join("")}</tbody></table></div>
      </div>`).join("")}
    </div>`;
}

/* ----------------------------------------------------------- game profiles */
export async function renderGames(params) {
  const el = document.getElementById("view");
  const files = await loadFiles();
  const fid = params.get("file") || "";
  const [profiles, classify] = await Promise.all([
    api("/api/games"),
    fid ? api(`/api/files/${fid}/game-profile`) : Promise.resolve(null),
  ]);
  el.innerHTML = `
    <h2 class="section-title">GAME PROFILES</h2>
    <p class="section-sub">CoH1 / CoH2 / Dawn of War UCS dialect hints.</p>
    <label class="field">Classify upload<select id="gp-file"><option value="">—</option>${fileOptions(files, fid)}</select></label>
    <div class="grid cols-2" style="margin-top:16px">
      ${profiles.profiles.map(p => `<div class="card"><h3>${esc(p.name)}</h3>
        <div class="stat-row"><span class="k">id</span><span class="v">${esc(p.id)}</span></div>
        <div class="stat-row"><span class="k">BOM</span><span class="v">${p.bom_required?"required":"optional"}</span></div>
        <div class="stat-row"><span class="k">typical max key</span><span class="v">${fmt(p.typical_max_key)}</span></div>
        <p style="font-size:13px;color:var(--text-dim)">${esc(p.notes)}</p></div>`).join("")}
    </div>
    <div id="gp-out"></div>`;
  document.getElementById("gp-file").onchange = e => {
    if (e.target.value) navigateRoute("games", { file: e.target.value });
  };
  if (classify) {
    document.getElementById("gp-out").innerHTML = `
      <h3 class="section-title" style="margin-top:20px">Classification</h3>
      <div class="banner">Best match: <strong>${esc(classify.classification.best_match)}</strong>
        (${(classify.classification.confidence*100).toFixed(0)}% confidence)</div>
      <div class="table-wrap"><table class="data"><thead><tr><th>profile</th><th>score</th></tr></thead>
      <tbody>${classify.classification.candidates.map(c => `<tr><td>${esc(c.name)}</td><td class="num">${c.score}</td></tr>`).join("")}
      </tbody></table></div>
      ${classify.classification.warnings.length ? `<p class="section-sub">Warnings: ${classify.classification.warnings.map(esc).join("; ")}</p>` : ""}`;
  }
}

/* ------------------------------------------------------------- sga browser */
export async function renderSga() {
  document.getElementById("view").innerHTML = `
    <h2 class="section-title">SGA BROWSER</h2>
    <p class="section-sub">Scan install archives; list internals; extract locale <code>.ucs</code> files.</p>
    <div class="form-row">
      <label class="field" style="flex:2">Install path<input id="sga-p" placeholder="C:\\Games\\Company of Heroes..."></label>
      <button class="btn" id="sga-go">Scan archives</button>
      <button class="btn ghost" id="sga-locale">Locale scan</button>
      <button class="btn" id="sga-extract-all">Extract all UCS</button>
    </div>
    <div id="sga-out"></div>`;
  document.getElementById("sga-locale").onclick = async () => {
    const install = document.getElementById("sga-p").value;
    if (!install) { toast("Enter install path"); return; }
    const d = await api(`/api/sga/locale-scan?install_path=${encodeURIComponent(install)}`);
    document.getElementById("sga-out").innerHTML = `
      <div class="banner">${d.count} archive(s) with locale UCS</div>
      ${d.archives.map(a => `<div class="card" style="margin-top:10px"><h3>${esc(a.relative)}</h3>
        <p>${esc(a.locale_hint||"locale")} · ${a.locale_ucs.length} file(s)</p>
        <ul>${a.locale_ucs.map(u => `<li>${esc(u.path)} (${fmt(u.size)} B)</li>`).join("")}</ul></div>`).join("")}`;
  };
  document.getElementById("sga-extract-all").onclick = async () => {
    const install = document.getElementById("sga-p").value;
    if (!install) { toast("Enter install path"); return; }
    const d = await api("/api/sga/extract-locales", { method: "POST",
      body: JSON.stringify({ install_path: install }) });
    toast(`Extracted ${d.uploaded} UCS file(s)`);
    document.getElementById("sga-out").innerHTML = `
      <div class="banner">${d.uploaded} uploaded · ${d.errors?.length||0} error(s)</div>
      <ul>${(d.files||[]).map(f => `<li><a href="${routePath("upload", { file: f.file_id })}">${esc(f.internal_path)}</a></li>`).join("")}</ul>`;
  };
  document.getElementById("sga-go").onclick = async () => {
    const p = encodeURIComponent(document.getElementById("sga-p").value);
    const d = await api(`/api/sga/scan?install_path=${p}`);
    document.getElementById("sga-out").innerHTML = `
      <div class="table-wrap"><table class="data"><thead><tr><th>archive</th><th>size</th><th>stub?</th><th></th></tr></thead>
      <tbody>${d.files.map(f => `<tr>
        <td><a href="#" class="sga-open" data-path="${esc(document.getElementById("sga-p").value)}\\${esc(f.path)}">${esc(f.path)}</a></td>
        <td>${fmt(f.size)}</td><td>${f.likely_stub?"yes":"no"}</td>
        <td><button class="btn ghost small sga-open" data-path="${esc(document.getElementById("sga-p").value)}\\${esc(f.path)}">Browse</button></td>
      </tr>`).join("")}
      </tbody></table></div>
      <div id="sga-detail"></div>`;
    document.querySelectorAll(".sga-open").forEach(btn => btn.onclick = async e => {
      e.preventDefault();
      const path = btn.dataset.path.replace(/\\\\/g, "\\");
      const c = await api(`/api/sga/${encodeURIComponent(path)}/contents`);
      const detail = document.getElementById("sga-detail");
      if (c.error) { detail.innerHTML = `<div class="banner error">${esc(c.error)}</div>`; return; }
      const locale = (c.locale_ucs || []).slice(0, 20);
      detail.innerHTML = `
        <h3 class="section-title" style="margin-top:20px">${esc(c.archive_name)} · ${fmt(c.file_count)} files
          ${c.locale_hint ? `· locale: ${esc(c.locale_hint)}` : ""}</h3>
        ${locale.length ? `<p class="section-sub">Locale UCS: ${locale.map(esc).join(", ")}</p>` : ""}
        <div class="table-wrap"><table class="data"><thead><tr><th>path</th><th>size</th><th></th></tr></thead>
        <tbody>${(c.files || []).filter(f => !f.likely_stub).slice(0, 100).map(f => `<tr>
          <td>${esc(f.path)}</td><td>${fmt(f.size)}</td>
          <td>${f.path.toLowerCase().endsWith(".ucs") ? `<button class="btn ghost small sga-ex" data-arch="${esc(path)}" data-int="${esc(f.path)}">Extract</button>` : ""}</td>
        </tr>`).join("")}
        </tbody></table></div>`;
      detail.querySelectorAll(".sga-ex").forEach(b => b.onclick = async () => {
        const r = await api(`/api/sga/${encodeURIComponent(b.dataset.arch)}/extract`, {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ internal_path: b.dataset.int }),
        });
        sessionStorage.setItem("coh-sga-inject", JSON.stringify({
          arch: b.dataset.arch, internal: b.dataset.int, file_id: r.file_id || "",
        }));
        toast(r.file_id ? `Extracted → upload ${r.file_id}` : `Extracted ${r.bytes} bytes`);
        if (r.file_id) navigateRoute("upload", { file: r.file_id });
      });
      await renderSgaInjectPanel(detail, path, c.files || []);
    });
  };
}

async function renderSgaInjectPanel(detail, archPath, archiveFiles) {
  const ucsPaths = archiveFiles.filter(f => f.path.toLowerCase().endsWith(".ucs") && !f.likely_stub);
  if (!ucsPaths.length) return;
  const stored = JSON.parse(sessionStorage.getItem("coh-sga-inject") || "{}");
  const files = (await loadFiles()).filter(f => f.kind !== "version");
  const prePath = stored.arch === archPath ? stored.internal : ucsPaths[0].path;
  const preFile = stored.arch === archPath ? stored.file_id : "";
  detail.insertAdjacentHTML("beforeend", `
    <div class="card" id="sga-inject" style="margin-top:20px">
      <h3 class="section-title" style="font-size:14px">Inject edited UCS into archive</h3>
      <p class="section-sub">Replace a locale file inside a copy of this SGA — originals on disk are never overwritten.</p>
      <div class="form-row">
        <label class="field">Internal path
          <select id="sga-in-path">${ucsPaths.map(f =>
            `<option value="${esc(f.path)}" ${f.path === prePath ? "selected" : ""}>${esc(f.path)}</option>`
          ).join("")}</select>
        </label>
        <label class="field">Modified UCS
          <select id="sga-in-file"><option value="">—</option>${fileOptions(files, preFile)}</select>
        </label>
        <button class="btn" id="sga-in-go">Inject SGA</button>
      </div>
      <div id="sga-in-out"></div>
    </div>`);
  document.getElementById("sga-in-go").onclick = async () => {
    const internal = document.getElementById("sga-in-path").value;
    const ucsId = document.getElementById("sga-in-file").value;
    if (!ucsId) { toast("Pick the modified UCS file"); return; }
    const out = document.getElementById("sga-in-out");
    out.innerHTML = `<div class="loading">Packing</div>`;
    try {
      const r = await api(`/api/sga/${encodeURIComponent(archPath)}/inject-ucs`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ internal_path: internal, ucs_id: ucsId }),
      });
      out.innerHTML = `<div class="banner"><a href="${r.download_url}">Download ${esc(r.output.split(/[/\\\\]/).pop())}</a>
        · ${fmt(r.bytes)} bytes</div>`;
      toast("SGA packed");
    } catch (err) {
      out.innerHTML = `<div class="banner error">${esc(err.message)}</div>`;
    }
  };
}

/* -------------------------------------------------------- verify checklist */
export async function renderVerify(params) {
  const el = document.getElementById("view");
  const files = await loadFiles();
  const fid = params.get("file") || "";
  el.innerHTML = `
    <h2 class="section-title">VERIFY CHECKLIST</h2>
    <p class="section-sub">Known-bad IDs (<code>559200</code>, <code>9419700</code>, ToV menus) — run before installing in-game.</p>
    <label class="field">File<select id="vf-file"><option value="">—</option>${fileOptions(files, fid)}</select></label>
    <button class="btn" id="vf-go">Run checklist</button>
    <div id="vf-out"></div>`;
  document.getElementById("vf-file").onchange = e => {
    if (e.target.value) navigateRoute("verify", { file: e.target.value });
  };
  document.getElementById("vf-go").onclick = () => {
    const v = document.getElementById("vf-file").value;
    if (v) navigateRoute("verify", { file: v });
  };
  if (fid) await loadVerify(fid);
}

async function loadVerify(fid) {
  const out = document.getElementById("vf-out");
  out.innerHTML = `<div class="loading">Checking</div>`;
  const d = await api(`/api/files/${fid}/verify`);
  const row = r => `<tr class="${r.status}">
    <td class="num">${r.key}</td><td>${esc(r.category)}</td><td>${esc(r.label)}</td>
    <td class="${r.status === "pass" ? "good" : r.status === "fail" ? "bad" : ""}">${esc(r.status)}</td>
    <td>${esc(r.message)}</td><td class="val">${r.value != null ? esc(r.value) : "—"}</td></tr>`;
  out.innerHTML = `
    <div class="banner ${d.ok ? "" : "error"}">${d.passed}/${d.total} pass · ${d.failed} fail · ${d.warned} warn
      ${d.ok ? "— ready for in-game check" : "— fix failures before install"}</div>
    <div class="table-wrap"><table class="data"><thead><tr><th>id</th><th>cat</th><th>label</th><th>status</th><th>message</th><th>value</th></tr></thead>
    <tbody>${d.items.map(row).join("")}</tbody></table></div>
    <div class="card" style="margin-top:16px"><h3>In-game steps</h3><ul>
      ${(d.install_tips || []).map(t => `<li>${esc(t)}</li>`).join("")}
    </ul></div>`;
}

/* ---------------------------------------------------------- translation I/O */
export async function renderTranslation(params) {
  const files = await loadFiles();
  const fid = params.get("file") || "";
  document.getElementById("view").innerHTML = `
    <h2 class="section-title">PO / TMX</h2>
    <p class="section-sub">Export for CAT tools (gettext PO, TMX 1.4); import translations back to UCS.</p>
    <label class="field">Template UCS<select id="tr-file"><option value="">—</option>${fileOptions(files, fid)}</select></label>
    <div class="form-row" style="margin-top:12px">
      <a class="btn ghost" id="tr-po-dl" href="#">Download PO</a>
      <a class="btn ghost" id="tr-tmx-dl" href="#">Download TMX</a>
    </div>
    <div class="card" style="margin-top:20px">
      <h3>Import PO or TMX</h3>
      <label class="field">Format<select id="tr-fmt"><option value="po">PO (gettext)</option><option value="tmx">TMX</option></select></label>
      <textarea id="tr-text" rows="12" style="width:100%;font-family:var(--mono);background:var(--panel);color:var(--text);border:1px solid var(--border);padding:8px" placeholder="Paste .po or .tmx content"></textarea>
      <button class="btn" id="tr-import" style="margin-top:8px">Import → new UCS</button>
      <div id="tr-out"></div>
    </div>`;
  const syncLinks = () => {
    const id = document.getElementById("tr-file").value;
    document.getElementById("tr-po-dl").href = id ? apiUrl(`/api/files/${id}/po`) : "#";
    document.getElementById("tr-tmx-dl").href = id ? apiUrl(`/api/files/${id}/tmx`) : "#";
  };
  document.getElementById("tr-file").onchange = () => {
    syncLinks();
    const v = document.getElementById("tr-file").value;
    if (v) navigateRoute("translation", { file: v });
  };
  document.getElementById("tr-import").onclick = async () => {
    const id = document.getElementById("tr-file").value;
    const text = document.getElementById("tr-text").value;
    if (!id || !text) { toast("Pick file and paste content"); return; }
    const fmt = document.getElementById("tr-fmt").value;
    const body = fmt === "tmx" ? { tmx: text } : { po: text };
    const path = fmt === "tmx" ? "tmx" : "po";
    const r = await api(`/api/files/${id}/${path}`, { method: "POST", body: JSON.stringify(body) });
    document.getElementById("tr-out").innerHTML = `<div class="banner"><a href="${routePath("upload", { file: r.file_id })}">Imported ${r.keys} keys → ${r.file_id}</a></div>`;
  };
  if (fid) { document.getElementById("tr-file").value = fid; syncLinks(); }
}

/* --------------------------------------------------------------- editor */
export async function renderEditor(params) {
  const el = document.getElementById("view");
  const files = await loadFiles();
  const fid = params.get("file") || "";
  el.innerHTML = `
    <h2 class="section-title">UCS EDITOR</h2>
    <p class="section-sub">Monaco editor with live lint. Save creates a new upload.</p>
    <label class="field">File<select id="ed-file"><option value="">—</option>${fileOptions(files, fid)}</select></label>
    <div id="monaco" style="height:420px;border:1px solid var(--border);margin:12px 0"></div>
    <button class="btn" id="ed-save">Save as new upload</button>
    <div id="ed-sga" style="margin-top:12px"></div>
    <div id="ed-lint" class="banner" style="margin-top:12px"></div>`;
  const loadMonaco = () => new Promise((resolve) => {
    if (window.monaco) return resolve();
    const s = document.createElement("script");
    s.src = "https://cdn.jsdelivr.net/npm/monaco-editor@0.52.0/min/vs/loader.js";
    s.onload = () => {
      require.config({ paths: { vs: "https://cdn.jsdelivr.net/npm/monaco-editor@0.52.0/min/vs" } });
      require(["vs/editor/editor.main"], resolve);
    };
    document.head.appendChild(s);
  });
  let editor;
  async function loadFile(id) {
    if (!id) return;
    const page = await api(`/api/files/${id}/entries?limit=500`);
    const text = page.entries.map(e => `${e.key}\t${e.value}`).join("\n");
    await loadMonaco();
    if (!editor) {
      editor = monaco.editor.create(document.getElementById("monaco"), {
        value: text, language: "plaintext", theme: "vs-dark", automaticLayout: true,
      });
    } else editor.setValue(text);
    const lint = await api(`/api/files/${id}/lint`);
    document.getElementById("ed-lint").textContent =
      `${lint.entries_with_issues} entries with issues · ${lint.token_issue_count} token issues`;
  }
  document.getElementById("ed-file").onchange = e => loadFile(e.target.value);
  function showSgaInject(fileId) {
    const box = document.getElementById("ed-sga");
    let sga = null;
    try { sga = JSON.parse(sessionStorage.getItem("coh-sga-inject") || "null"); } catch { /* ignore */ }
    if (!sga?.arch) { box.innerHTML = ""; return; }
    box.innerHTML = `
      <div class="card">
        <h3 style="font-size:14px;margin:0 0 8px">Inject into SGA</h3>
        <p class="section-sub">${esc(sga.internal)} in ${esc(sga.arch.split(/[/\\\\]/).pop())}</p>
        <button class="btn small" id="ed-inject">Inject saved UCS into archive</button>
        <div id="ed-inject-out"></div>
      </div>`;
    document.getElementById("ed-inject").onclick = async () => {
      const out = document.getElementById("ed-inject-out");
      out.innerHTML = `<div class="loading">Packing SGA</div>`;
      try {
        const r = await api(`/api/sga/${encodeURIComponent(sga.arch)}/inject-ucs`, {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ internal_path: sga.internal, ucs_id: fileId }),
        });
        out.innerHTML = `<div class="banner"><a href="${r.download_url}">Download patched SGA</a></div>`;
        toast("SGA packed");
      } catch (err) {
        out.innerHTML = `<div class="banner error">${esc(err.message)}</div>`;
      }
    };
  }
  document.getElementById("ed-save").onclick = async () => {
    const id = document.getElementById("ed-file").value;
    if (!id || !editor) { toast("Load a file first"); return; }
    const entries = editor.getValue().split(/\r?\n/).filter(Boolean).map(line => {
      const t = line.indexOf("\t");
      return t < 0 ? null : { key: parseInt(line.slice(0, t), 10), value: line.slice(t + 1) };
    }).filter(Boolean);
    const r = await api(`/api/files/${id}/save`, { method: "POST", body: JSON.stringify({ entries }) });
    toast(`Saved as ${r.file_id}`);
    try {
      const cur = JSON.parse(sessionStorage.getItem("coh-sga-inject") || "null");
      if (cur) sessionStorage.setItem("coh-sga-inject", JSON.stringify({ ...cur, file_id: r.file_id }));
    } catch { /* ignore */ }
    showSgaInject(r.file_id);
  };
  if (fid) await loadFile(fid);
  showSgaInject(fid);
}

/* --------------------------------------------------------------- settings */
export async function renderSettings() {
  const theme = localStorage.getItem("coh-theme") || "dark";
  const lang = localStorage.getItem("coh-ui-lang") || "en";
  let auth = { auth_enabled: false, authenticated: false };
  try { auth = await api("/api/auth/status"); } catch { /* offline */ }
  const sessionHint = () => {
    if (auth.session_expired) {
      return `<p class="bad" style="font-size:13px">Session expired — sign in again to upload or merge.</p>`;
    }
    if (auth.session_expires_in_s != null && auth.session_expires_in_s < 3600 && auth.authenticated) {
      const mins = Math.ceil(auth.session_expires_in_s / 60);
      return `<p class="muted" style="font-size:13px">Session expires in ~${mins} min — re-login soon to avoid interruption.</p>`;
    }
    if (auth.session_expires_in_s != null && auth.authenticated) {
      const hrs = Math.floor(auth.session_expires_in_s / 3600);
      const mins = Math.ceil((auth.session_expires_in_s % 3600) / 60);
      return `<p class="muted" style="font-size:13px">Session valid for ${hrs ? `${hrs}h ` : ""}${mins}m.</p>`;
    }
    return "";
  };
  document.getElementById("view").innerHTML = `
    <h2 class="section-title">SETTINGS</h2>
    <div class="card" style="max-width:480px;margin-bottom:16px">
      <h3 style="font-size:14px;margin:0 0 10px">Authentication</h3>
      ${auth.authenticated
        ? `<p>Signed in as <strong>${esc(auth.user || "")}</strong> (${esc(auth.method || "")})</p>
           ${sessionHint()}
           <button class="btn ghost small" id="auth-logout">Sign out</button>`
        : auth.auth_enabled
          ? `<p class="muted" style="font-size:13px">Server requires login or API key for uploads and merges.</p>
             <label class="field">Username<input id="auth-user" autocomplete="username"></label>
             <label class="field" style="margin-top:8px">Password<input type="password" id="auth-pass" autocomplete="current-password"></label>
             <button class="btn small" id="auth-login" style="margin-top:10px">Sign in</button>
             ${auth.oauth_configured ? `<a class="btn ghost small" href="${apiUrl("/api/auth/oauth/login")}" style="margin-left:8px">OAuth</a>` : ""}`
          : `<p class="muted" style="font-size:13px">No server auth configured.</p>`}
    </div>
    <div class="card" style="max-width:480px">
      <label class="toggle"><input type="checkbox" id="theme-t" ${theme==="light"?"checked":""}> Light theme</label>
      <label class="field" style="margin-top:16px">UI language
        <select id="ui-lang"><option value="en">English</option><option value="fr">Français</option><option value="ar">العربية</option></select>
      </label>
      <label class="field" style="margin-top:16px">API key (for uploads/merge when server requires it)
        <input type="password" id="api-key" placeholder="X-API-Key" autocomplete="off" style="width:100%;margin-top:6px;padding:8px;background:var(--panel);border:1px solid var(--border);color:var(--text)">
      </label>
      <p style="margin-top:16px"><a href="${apiUrl("/docs")}" target="_blank">OpenAPI docs (/docs)</a> ·
        <a href="${apiUrl("/api/export/openapi-client")}" target="_blank">Client snippets</a></p>
      <button class="btn ghost small" id="dup-probe" style="margin-top:12px">Generate duplicate-ID probe</button>
      <div id="dup-out"></div>
    </div>
    <div class="card" style="max-width:720px;margin-top:16px">
      <h3 style="font-size:14px;margin:0 0 10px">Webhook delivery log</h3>
      <button class="btn ghost small" id="wh-retry" style="margin-bottom:8px">Retry dead letters</button>
      <div id="wh-log"><div class="loading">Loading</div></div>
    </div>`;
  const renderWhLog = async () => {
    try {
      const wh = await api("/api/webhooks/deliveries?limit=25");
      const rows = wh.deliveries || [];
      document.getElementById("wh-log").innerHTML = rows.length ? `
        <div class="table-wrap"><table class="data"><thead><tr><th>event</th><th>url</th><th>ok</th><th>try</th><th>detail</th></tr></thead>
        <tbody>${rows.map(d => `<tr>
          <td>${esc(d.event)}</td><td style="font-size:11px;max-width:200px;overflow:hidden;text-overflow:ellipsis">${esc(d.url)}</td>
          <td class="${d.success ? "good" : "bad"}">${d.success ? "yes" : "no"}</td>
          <td>${d.attempt || 1}${d.dead_letter ? " DL" : ""}</td>
          <td style="font-size:11px">${d.success ? esc(String(d.status_code || "")) : esc(d.error || "")}</td>
        </tr>`).join("")}</tbody></table></div>`
        : `<p class="muted">No webhook deliveries yet.</p>`;
    } catch {
      document.getElementById("wh-log").innerHTML = `<p class="muted">Webhook log unavailable offline.</p>`;
    }
  };
  await renderWhLog();
  document.getElementById("wh-retry")?.addEventListener("click", async () => {
    try {
      const r = await api("/api/webhooks/retry-dead-letters", { method: "POST" });
      toast(`Retried ${r.retried}: ${r.succeeded} ok, ${r.failed} failed`);
      await renderWhLog();
    } catch (e) { toast(e.message); }
  });
  const loginBtn = document.getElementById("auth-login");
  if (loginBtn) {
    loginBtn.onclick = async () => {
      try {
        await api("/api/auth/login", { method: "POST", headers: {"Content-Type":"application/json"},
          body: JSON.stringify({
            username: document.getElementById("auth-user").value,
            password: document.getElementById("auth-pass").value,
          }) });
        toast("Signed in");
        renderSettings();
      } catch (e) { toast(e.message); }
    };
  }
  const logoutBtn = document.getElementById("auth-logout");
  if (logoutBtn) {
    logoutBtn.onclick = async () => {
      await api("/api/auth/logout", { method: "POST" });
      toast("Signed out");
      renderSettings();
    };
  }
  document.getElementById("dup-probe").onclick = async () => {
    const r = await api("/api/tools/duplicate-probe", { method: "POST" });
    document.getElementById("dup-out").innerHTML = `
      <div class="banner" style="margin-top:10px"><a href="${r.download_url}">Download probe</a></div>
      <ul style="font-size:13px;margin-top:8px">${(r.instructions||[]).map(i => `<li>${esc(i)}</li>`).join("")}</ul>`;
  };
  document.getElementById("theme-t").onchange = e => {
    const light = e.target.checked;
    document.documentElement.dataset.theme = light ? "light" : "dark";
    localStorage.setItem("coh-theme", light ? "light" : "dark");
  };
  document.getElementById("ui-lang").value = lang;
  document.getElementById("ui-lang").onchange = e => {
    localStorage.setItem("coh-ui-lang", e.target.value);
    toast("Language saved — reload to apply nav labels");
  };
  const keyInput = document.getElementById("api-key");
  keyInput.value = localStorage.getItem("coh-api-key") || "";
  keyInput.onchange = e => {
    const v = e.target.value.trim();
    if (v) localStorage.setItem("coh-api-key", v);
    else localStorage.removeItem("coh-api-key");
    toast("API key saved");
  };
}

/* --------------------------------------------------------------- about */
export async function renderAbout() {
  const el = document.getElementById("view");
  const faq = window.ABOUT_FAQ || [];
  el.innerHTML = `
    <article class="about-page">
      <h2 class="section-title">ABOUT COH UCS TOOLS</h2>
      <p class="section-sub">Open-source toolkit for <strong>Company of Heroes</strong> modders, translators, and archivists working with Relic <code>.ucs</code> localization files.</p>

      <div class="card about-lead">
        <p>CoH UCS Tools helps you hunt down missing string ids — the ones that show up in-game as
           <code>$559200 No Key</code> in Tales of Valor menus or other broken UI text. Upload any
           <code>RelicCOH.English.ucs</code> / <code>RelicCOH.Russian.ucs</code> locale file, validate
           encoding and line format, compare coverage against another version, and merge missing ids safely.</p>
        <p>The web console and REST API share the same Python parser used by the CLI — UTF-16-LE, <code>FF FE</code> BOM,
           CRLF endings, tab-separated <code>id→text</code> rows, no comments.</p>
      </div>

      <h3 class="about-heading">What you can do</h3>
      <ul class="about-list">
        <li><a href="${routePath("upload")}">Upload &amp; analyze</a> — BOM detection, duplicate ids, invalid lines, entry browser</li>
        <li><a href="${routePath("compare")}">Compare two files</a> — coverage % and missing-id ranges both ways</li>
        <li><a href="${routePath("merge-wizard")}">Merge wizard</a> — graft missing ids with placeholders or verbatim copy</li>
        <li><a href="${routePath("validator")}">Validator</a> — full UCS format checklist before shipping a mod</li>
        <li><a href="${routePath("translation")}">PO / TMX export</a> — gettext and TMX interchange for CAT tools</li>
        <li><a href="${routePath("languages")}">Languages hub</a> — known CoH1 retail and community locale versions</li>
      </ul>

      <h3 class="about-heading">Who it is for</h3>
      <p>Complete Edition owners fixing broken menus, localization researchers recovering official English text,
         French/German/Spanish community patch authors, and developers wiring CI against the
         <a href="${apiUrl("/docs")}" target="_blank" rel="noopener">REST API</a>.</p>

      <h3 class="about-heading">Frequently asked questions</h3>
      <div class="faq-list">
        ${faq.map(({ question, answer }) => `
          <details class="faq-item">
            <summary>${esc(question)}</summary>
            <p>${esc(answer)}</p>
          </details>`).join("")}
      </div>

      <p class="about-footer">MIT licensed · <a href="https://github.com/benmed00/coh-ucs-tools" target="_blank" rel="noopener">source on GitHub</a>
        · <a href="${routePath("upload")}">Open the console</a></p>
    </article>`;
}

/* apply saved theme on load */
export function initTheme() {
  const t = localStorage.getItem("coh-theme");
  if (t === "light") document.documentElement.dataset.theme = "light";
}
