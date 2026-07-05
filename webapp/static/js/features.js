/* Extended SPA sections — diff, languages, search, settings, etc. */

import { api, esc, fmt, loadFiles, fileOptions, fileLabel, toast, destroyCharts, makeChart, CHART_COLORS } from "./core.js";

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
    location.hash = `#/diff?a=${va}&b=${vb}&filter=${document.getElementById("d-f").value}`;
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
    location.hash = `#/ranges?a=${document.getElementById("r-a").value}&b=${document.getElementById("r-b").value}`;
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
    if (v) location.hash = `#/validator?file=${v}`;
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
        <a class="btn ghost small" href="/api/files/${fid}/issues.csv">Export CSV</a>
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
  const d = await api("/api/languages");
  el.innerHTML = `
    <h2 class="section-title">LANGUAGES</h2>
    <p class="section-sub">Coverage vs reference (${fmt(d.reference_keys)} keys).</p>
    <div class="grid cols-2">${d.languages.map(l => `
      <div class="card">
        <span class="kind-tag">${esc(l.source_badge)}</span>
        <h3>${esc(l.code)} — ${esc(l.name)}</h3>
        <div class="chart-box" style="height:140px"><canvas id="donut-${l.code}"></canvas></div>
        <div class="stat-row"><span class="k">keys</span><span class="v">${fmt(l.keys)}</span></div>
        <div class="stat-row"><span class="k">coverage</span><span class="v">${l.coverage_percent}%</span></div>
        <p style="font-size:13px;color:var(--text-dim)">${esc(l.notes)}</p>
        ${l.download_url ? `<a class="btn ghost small" href="${l.download_url}">Download</a>` : ""}
      </div>`).join("")}</div>`;
  destroyCharts();
  if (window.Chart) {
    d.languages.forEach(l => {
      const ctx = document.getElementById(`donut-${l.code}`);
      if (!ctx) return;
      makeChart(ctx, {
        type: "doughnut",
        data: { labels: ["covered","gap"], datasets: [{ data: [l.coverage_percent, 100-l.coverage_percent],
          backgroundColor: [CHART_COLORS.green, CHART_COLORS.dim], borderColor: "transparent" }] },
        options: { maintainAspectRatio: false, plugins: { legend: { display: false } }, cutout: "65%" },
      });
    });
  }
}

/* ---------------------------------------------------------- merge wizard */
export async function renderMergeWizard(params) {
  const el = document.getElementById("view");
  const files = await loadFiles();
  el.innerHTML = `
    <h2 class="section-title">MERGE WIZARD</h2>
    <p class="section-sub">3-step merge with preview — nothing translated, originals untouched.</p>
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
    const r = await api("/api/merge/preview", { method: "POST", headers: {"Content-Type":"application/json"},
      body: JSON.stringify({ target_id: document.getElementById("mw-t").value, source_id: document.getElementById("mw-s").value, mode, limit: 30 }) });
    out.innerHTML = `<div class="banner">Would add ${fmt(r.total_would_add)} id(s)</div>
      <div class="table-wrap"><table class="data"><thead><tr><th>id</th><th>source</th><th>result</th></tr></thead>
      <tbody>${r.preview.map(p => `<tr><td class="num">${p.key}</td><td class="val">${esc(p.source_value||"")}</td><td class="val">${esc(p.result_value)}</td></tr>`).join("")}</tbody></table></div>`;
  };
  document.getElementById("mw-run").onclick = async () => {
    const mode = document.querySelector('input[name="mw-m"]:checked').value;
    const r = await api("/api/merge", { method: "POST", headers: {"Content-Type":"application/json"},
      body: JSON.stringify({ target_id: document.getElementById("mw-t").value, source_id: document.getElementById("mw-s").value, mode }) });
    toast("Merge complete");
    document.getElementById("mw-out").innerHTML = `<div class="banner"><a href="${r.download_url}">Download ${esc(r.filename)}</a></div>`;
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
  document.getElementById("view").innerHTML = `
    <h2 class="section-title">DEPOTS &amp; SOURCES</h2>
    <div class="grid cols-2">
      <div><h3 class="section-title" style="font-size:16px">Depots</h3>
        ${dep.depots.map(d => `<div class="card"><h3>${esc(d.language)} (app ${d.app_id})</h3>
          <p>${esc(d.description)}</p><pre class="mono-block">${esc(d.command_template)}</pre></div>`).join("")}
      </div>
      <div><h3 class="section-title" style="font-size:16px">Sources</h3>
        ${src.sources.map(s => `<div class="card tool-card"><span class="cat">${esc(s.trust)}</span>
          <h3><a href="${esc(s.url)}" target="_blank">${esc(s.name)}</a></h3><p>${esc(s.description)}</p></div>`).join("")}
      </div>
    </div>`;
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
    location.hash = `#/search?q=${encodeURIComponent(query)}`;
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
  document.getElementById("view").innerHTML = `
    <h2 class="section-title">PATCH BUILDER</h2>
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

/* ------------------------------------------------------------- sga browser */
export async function renderSga() {
  document.getElementById("view").innerHTML = `
    <h2 class="section-title">SGA BROWSER</h2>
    <div class="form-row">
      <label class="field" style="flex:2">Install path<input id="sga-p" placeholder="C:\\Games\\Company of Heroes..."></label>
      <button class="btn" id="sga-go">Scan</button>
    </div>
    <div id="sga-out"></div>`;
  document.getElementById("sga-go").onclick = async () => {
    const p = encodeURIComponent(document.getElementById("sga-p").value);
    const d = await api(`/api/sga/scan?install_path=${p}`);
    document.getElementById("sga-out").innerHTML = `
      <div class="table-wrap"><table class="data"><thead><tr><th>path</th><th>size</th><th>stub?</th></tr></thead>
      <tbody>${d.files.map(f => `<tr><td>${esc(f.path)}</td><td>${fmt(f.size)}</td><td>${f.likely_stub?"yes":"no"}</td></tr>`).join("")}
      </tbody></table></div>`;
  };
}

/* --------------------------------------------------------------- settings */
export async function renderSettings() {
  const theme = localStorage.getItem("coh-theme") || "dark";
  document.getElementById("view").innerHTML = `
    <h2 class="section-title">SETTINGS</h2>
    <div class="card" style="max-width:480px">
      <label class="toggle"><input type="checkbox" id="theme-t" ${theme==="light"?"checked":""}> Light theme</label>
      <p style="margin-top:16px"><a href="/docs" target="_blank">OpenAPI docs (/docs)</a> ·
        <a href="/api/export/openapi-client" target="_blank">Client snippets</a></p>
    </div>`;
  document.getElementById("theme-t").onchange = e => {
    const light = e.target.checked;
    document.documentElement.dataset.theme = light ? "light" : "dark";
    localStorage.setItem("coh-theme", light ? "light" : "dark");
  };
}

/* apply saved theme on load */
export function initTheme() {
  const t = localStorage.getItem("coh-theme");
  if (t === "light") document.documentElement.dataset.theme = "light";
}
