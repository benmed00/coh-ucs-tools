/* CoH UCS Tools — SPA (hash routing, no build step). */

const view = document.getElementById("view");
const toastEl = document.getElementById("toast");

/* ------------------------------------------------------------ utilities */
function esc(s) {
  return String(s).replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

function toast(msg, ms = 3200) {
  toastEl.textContent = msg;
  toastEl.hidden = false;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => { toastEl.hidden = true; }, ms);
}

async function api(path, opts = {}) {
  const res = await fetch(path, opts);
  if (res.status === 204) return null;
  let body = null;
  try { body = await res.json(); } catch { /* non-JSON */ }
  if (!res.ok) {
    const detail = body && body.detail ? JSON.stringify(body.detail) : res.statusText;
    throw new Error(`${res.status}: ${detail}`);
  }
  return body;
}

function fmt(n) { return Number(n).toLocaleString("en-US"); }

function fileLabel(f) {
  const tag = { upload: "UPL", version: "VER", generated: "GEN" }[f.kind] || "?";
  return `[${tag}] ${f.name} — ${fmt(f.keys)} keys`;
}

async function loadFiles() {
  const data = await api("/api/files");
  return data.files;
}

function fileOptions(files, selected) {
  return files.map(f =>
    `<option value="${f.id}" ${f.id === selected ? "selected" : ""}>${esc(fileLabel(f))}</option>`
  ).join("");
}

const UCS_FACTS = [
  ["Encoding", "UTF-16-LE", "Two bytes per character, little-endian — the same convention as Windows wide strings."],
  ["BOM", "FF FE", "The byte-order mark. Every shipped UCS file starts with these two bytes."],
  ["Separator", "first TAB", "The value is everything after the FIRST tab; values may legally contain more tabs."],
  ["Fallback", "$id No Key", "What the engine renders in-game when an id has no entry — the bug this toolkit hunts."],
];

/* --------------------------------------------------------------- charts */
let charts = [];
function destroyCharts() { charts.forEach(c => c.destroy()); charts = []; }
function makeChart(ctx, cfg) {
  const c = new Chart(ctx, cfg);
  charts.push(c);
  return c;
}
const CHART_COLORS = { amber: "#ffb648", olive: "#8a9a5b", green: "#9acd68", red: "#e06c4f", dim: "#8f8c77" };
if (window.Chart) {
  Chart.defaults.color = "#8f8c77";
  Chart.defaults.borderColor = "#3a4028";
  Chart.defaults.font.family = '"IBM Plex Mono", monospace';
}

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
    <p class="section-sub">Known Company of Heroes 1 <code>.ucs</code> versions registered on this server.
       Bars show unique key counts — more keys, more content covered.</p>
    <div class="grid cols-2">
      ${versions.map(v => `
        <div class="card">
          <span class="kind-tag">${v.available ? "on disk" : "not found"}</span>
          <h3>${esc(v.name)}</h3>
          <div class="keybar"><i style="width:${v.available ? (100 * v.keys / maxKeys).toFixed(1) : 0}%"></i></div>
          <div class="keybar-label">${v.available ? fmt(v.keys) + " keys" : "file not present on this machine"}</div>
          <div class="stat-row"><span class="k">origin</span><span class="v">${esc(v.origin)}</span></div>
          <div class="stat-row"><span class="k">completeness</span><span class="v ${v.completeness.startsWith("Complete") || v.completeness.startsWith("Superset") ? "good" : "warn"}">${esc(v.completeness)}</span></div>
          <p style="color:var(--text-dim);font-size:13px">${esc(v.notes)}</p>
          ${v.available ? `<a class="btn ghost small" href="${v.download_url}">&#8681; Download</a>
            <a class="btn ghost small" href="#/upload?file=${v.id}">Analyze</a>` : ""}
        </div>`).join("")}
    </div>
    <h2 class="section-title" style="margin-top:38px">STORED FILES</h2>
    <p class="section-sub">${uploads.length} upload(s), ${generated.length} generated merge result(s), ${versions.filter(v => v.available).length} registered version(s).</p>
    ${files.length === 0 ? `
      <div class="empty"><span class="empty-icon">&#128194;</span>
        Nothing here yet — head to <a href="#/upload">Upload &amp; Analyze</a> and drop a <code>.ucs</code> file.
      </div>` : `
      <div class="table-wrap"><table class="data">
        <thead><tr><th>kind</th><th>name</th><th>keys</th><th>dups</th><th>invalid</th><th>empty</th><th>encoding</th><th>bom</th><th></th></tr></thead>
        <tbody>${files.map(f => `
          <tr>
            <td>${f.kind}</td>
            <td class="val">${esc(f.name)}</td>
            <td class="num">${fmt(f.keys)}</td>
            <td>${f.duplicates}</td><td>${f.invalid_lines}</td><td>${f.empty_values}</td>
            <td>${esc(f.encoding)}</td><td>${f.has_bom ? "FF FE" : "—"}</td>
            <td><a href="#/upload?file=${f.id}">analyze</a> &middot; <a href="/api/downloads/${f.id}">download</a>
                ${f.kind !== "version" ? ` &middot; <a href="#" data-del="${f.id}" style="color:var(--red)">delete</a>` : ""}</td>
          </tr>`).join("")}
        </tbody></table></div>`}
  `;
  view.querySelectorAll("[data-del]").forEach(a => a.addEventListener("click", async e => {
    e.preventDefault();
    try {
      await api(`/api/files/${a.dataset.del}`, { method: "DELETE" });
      toast("File deleted");
      renderDashboard();
    } catch (err) { toast(err.message); }
  }));
}

/* -------------------------------------------------------------- upload */
async function renderUpload(params) {
  view.innerHTML = `<div class="loading">Preparing intake</div>`;
  const files = await loadFiles();
  const selected = params.get("file") || "";

  view.innerHTML = `
    <h2 class="section-title">UPLOAD &amp; ANALYZE</h2>
    <p class="section-sub">Drop a <code>.ucs</code> file for instant parsing — encoding &amp; BOM detection,
       duplicate/invalid-line reporting, validation and a searchable entry browser. Max 20&nbsp;MB.</p>
    <div class="grid cols-2">
      <div>
        <div class="dropzone" id="dropzone" data-tip="Files are parsed server-side with the exact same code as the CLI toolkit.">
          <span class="dz-icon">&#9738;</span>
          <p><strong>Drop a .ucs file here</strong> or click to choose</p>
          <p class="dz-hint">UTF-16-LE &middot; BOM FF FE &middot; id&#8677;text per line</p>
          <input type="file" id="file-input" accept=".ucs" hidden>
        </div>
        <div class="card" style="margin-top:16px">
          <h3>UCS format cheat sheet</h3>
          ${UCS_FACTS.map(([k, v, tip]) => `
            <div class="stat-row" data-tip="${esc(tip)}"><span class="k">${k}</span><span class="v">${esc(v)}</span></div>`).join("")}
        </div>
      </div>
      <div>
        <label class="field">Or analyze a stored file
          <select id="file-select">
            <option value="">— choose a file —</option>
            ${fileOptions(files, selected)}
          </select>
        </label>
        <div id="analysis" style="margin-top:16px">
          <div class="empty"><span class="empty-icon">&#128269;</span>
            No file selected. Upload one or pick a stored file to see its analysis.</div>
        </div>
      </div>
    </div>
    <div id="entries-panel" style="margin-top:30px"></div>
  `;

  const dz = document.getElementById("dropzone");
  const input = document.getElementById("file-input");
  const select = document.getElementById("file-select");

  async function upload(file) {
    if (!file) return;
    dz.querySelector("p").innerHTML = `Uploading <strong>${esc(file.name)}</strong>&hellip;`;
    const fd = new FormData();
    fd.append("file", file);
    try {
      const res = await api("/api/files", { method: "POST", body: fd });
      toast(res.message);
      location.hash = `#/upload?file=${res.file.id}`;
    } catch (err) {
      toast(err.message, 5000);
      renderUpload(params);
    }
  }

  dz.addEventListener("click", () => input.click());
  input.addEventListener("change", () => upload(input.files[0]));
  ["dragover", "dragleave", "drop"].forEach(ev => dz.addEventListener(ev, e => {
    e.preventDefault();
    dz.classList.toggle("drag", ev === "dragover");
    if (ev === "drop") upload(e.dataTransfer.files[0]);
  }));
  select.addEventListener("change", () => {
    location.hash = select.value ? `#/upload?file=${select.value}` : "#/upload";
  });

  if (selected) await renderAnalysis(selected);
}

async function renderAnalysis(fileId) {
  const analysis = document.getElementById("analysis");
  analysis.innerHTML = `<div class="loading">Parsing</div>`;
  let f, val;
  try {
    [f, val] = await Promise.all([
      api(`/api/files/${fileId}`),
      api(`/api/files/${fileId}/validate`),
    ]);
  } catch (err) {
    analysis.innerHTML = `<div class="banner error">${esc(err.message)}</div>`;
    return;
  }
  analysis.innerHTML = `
    <div class="card">
      <span class="kind-tag">${f.kind}</span>
      <h3>${esc(f.name)}</h3>
      <div class="stat-row"><span class="k">unique keys</span><span class="v good">${fmt(f.keys)}</span></div>
      <div class="stat-row"><span class="k">key range</span><span class="v">${f.min_key ?? "—"} … ${f.max_key ? fmt(f.max_key) : "—"}</span></div>
      <div class="stat-row"><span class="k">duplicates</span><span class="v ${f.duplicates ? "bad" : ""}">${f.duplicates}</span></div>
      <div class="stat-row"><span class="k">invalid lines</span><span class="v ${f.invalid_lines ? "bad" : ""}">${f.invalid_lines}</span></div>
      <div class="stat-row"><span class="k">empty values</span><span class="v ${f.empty_values ? "warn" : ""}">${f.empty_values}</span></div>
      <div class="stat-row" data-tip="Detected automatically: BOM first, then a strict UTF-16-LE probe.">
        <span class="k">encoding</span><span class="v">${esc(f.encoding)}${f.has_bom ? " + BOM FF FE" : ""}</span></div>
      <div class="stat-row"><span class="k">newline</span><span class="v">${esc(f.newline)}</span></div>
      <div class="stat-row"><span class="k">size</span><span class="v">${fmt(f.size)} bytes</span></div>
      <div class="stat-row"><span class="k">validation</span>
        <span class="v ${val.ok ? "good" : "bad"}">${val.ok ? "OK" : "FAILED"} — ${val.errors} error(s), ${val.warnings} warning(s)</span></div>
      <div style="margin-top:10px">
        <a class="btn ghost small" href="/api/downloads/${f.id}">&#8681; Download</a>
        <a class="btn ghost small" href="#/compare?a=${f.id}">Compare&hellip;</a>
      </div>
    </div>
    ${val.issues.length ? `
      <div class="table-wrap" style="margin-top:14px;max-height:260px;overflow-y:auto">
        <table class="data"><thead><tr><th>sev</th><th>code</th><th>id</th><th>message</th></tr></thead>
        <tbody>${val.issues.slice(0, 500).map(i => `
          <tr><td><span class="sev-${i.severity}">${i.severity}</span></td>
              <td>${esc(i.code)}</td><td class="num">${i.key ?? ""}</td>
              <td class="val">${esc(i.message)}</td></tr>`).join("")}
        </tbody></table>
      </div>
      ${val.issues.length > 500 ? `<p class="keybar-label">Showing first 500 of ${fmt(val.issues.length)} issues.</p>` : ""}` : ""}
  `;
  renderEntriesBrowser(fileId);
}

async function renderEntriesBrowser(fileId) {
  const panel = document.getElementById("entries-panel");
  panel.innerHTML = `
    <h2 class="section-title">ENTRY BROWSER</h2>
    <p class="section-sub">Search by numeric id or text. Toggle regex for pattern hunting
       (<code>Pz\\.? ?IV</code> style).</p>
    <div class="form-row">
      <label class="field" style="flex:2">Search
        <input type="search" id="q" placeholder="e.g. 559200 or Panzer…"></label>
      <label class="toggle"><input type="checkbox" id="q-regex"> regex</label>
      <button class="btn small" id="q-go">Search</button>
    </div>
    <div id="entries-out"><div class="loading">Loading entries</div></div>
  `;
  const state = { offset: 0, limit: 50 };
  const out = document.getElementById("entries-out");
  const q = document.getElementById("q");
  const qRegex = document.getElementById("q-regex");

  async function page() {
    out.innerHTML = `<div class="loading">Loading entries</div>`;
    const p = new URLSearchParams({ offset: state.offset, limit: state.limit });
    if (q.value) { p.set("search", q.value); p.set("regex", qRegex.checked); }
    let data;
    try { data = await api(`/api/files/${fileId}/entries?${p}`); }
    catch (err) { out.innerHTML = `<div class="banner error">${esc(err.message)}</div>`; return; }
    if (data.total === 0) {
      out.innerHTML = `<div class="empty"><span class="empty-icon">&#8709;</span>
        No entries match${q.value ? ` <code>${esc(q.value)}</code>` : ""}.
        ${qRegex.checked ? "Check your regex syntax." : "Try the regex toggle for patterns."}</div>`;
      return;
    }
    out.innerHTML = `
      <div class="table-wrap" style="max-height:420px;overflow-y:auto">
        <table class="data"><thead><tr><th style="width:110px">id</th><th>text</th></tr></thead>
        <tbody>${data.entries.map(e => `
          <tr><td class="num">${e.key}</td><td class="val">${e.value === "" ? '<span style="color:var(--text-dim)">(empty)</span>' : esc(e.value)}</td></tr>`).join("")}
        </tbody></table>
      </div>
      <div class="pager">
        <button class="btn ghost small" id="prev" ${state.offset === 0 ? "disabled" : ""}>&larr; prev</button>
        <span>${fmt(state.offset + 1)}–${fmt(Math.min(state.offset + state.limit, data.total))} of ${fmt(data.total)}</span>
        <button class="btn ghost small" id="next" ${state.offset + state.limit >= data.total ? "disabled" : ""}>next &rarr;</button>
      </div>`;
    out.querySelector("#prev")?.addEventListener("click", () => { state.offset = Math.max(0, state.offset - state.limit); page(); });
    out.querySelector("#next")?.addEventListener("click", () => { state.offset += state.limit; page(); });
  }

  document.getElementById("q-go").addEventListener("click", () => { state.offset = 0; page(); });
  q.addEventListener("keydown", e => { if (e.key === "Enter") { state.offset = 0; page(); } });
  page();
}

/* -------------------------------------------------------------- compare */
async function renderCompare(params) {
  view.innerHTML = `<div class="loading">Loading files</div>`;
  const files = await loadFiles();
  const a = params.get("a") || "";
  const b = params.get("b") || "";

  view.innerHTML = `
    <h2 class="section-title">COMPARE</h2>
    <p class="section-sub">Pick two files — get coverage percentages against the union key set and
       every missing id compressed into ranges, both ways.</p>
    ${files.length < 2 ? `
      <div class="empty"><span class="empty-icon">&#9878;</span>
        You need at least two stored files to compare. <a href="#/upload">Upload one</a> —
        the registered versions on the <a href="#/dashboard">dashboard</a> count too.</div>` : `
      <div class="form-row">
        <label class="field">Side A <select id="sel-a"><option value="">—</option>${fileOptions(files, a)}</select></label>
        <label class="field">Side B <select id="sel-b"><option value="">—</option>${fileOptions(files, b)}</select></label>
        <button class="btn" id="go">Compare</button>
      </div>
      <div id="compare-out">
        <div class="empty"><span class="empty-icon">&#9878;</span>Choose both sides and hit Compare.</div>
      </div>`}
  `;
  if (files.length < 2) return;

  const go = document.getElementById("go");
  go.addEventListener("click", () => {
    const va = document.getElementById("sel-a").value;
    const vb = document.getElementById("sel-b").value;
    if (!va || !vb) { toast("Pick both sides first"); return; }
    location.hash = `#/compare?a=${va}&b=${vb}`;
  });
  if (a && b) await runCompare(a, b);
}

async function runCompare(a, b) {
  const out = document.getElementById("compare-out");
  out.innerHTML = `<div class="loading">Crunching key sets</div>`;
  let d;
  try { d = await api(`/api/compare?a=${a}&b=${b}`); }
  catch (err) { out.innerHTML = `<div class="banner error">${esc(err.message)}</div>`; return; }

  const side = (s, label) => `
    <div class="card">
      <span class="kind-tag">side ${label}</span>
      <h3>${esc(s.name)}</h3>
      <div class="keybar"><i style="width:${s.coverage_percent}%"></i></div>
      <div class="keybar-label">${s.coverage_percent}% of the ${fmt(d.union_keys)}-key union</div>
      <div class="stat-row"><span class="k">total keys</span><span class="v">${fmt(s.total_keys)}</span></div>
      <div class="stat-row"><span class="k">missing here</span><span class="v ${s.missing_keys ? "bad" : "good"}">${fmt(s.missing_keys)}</span></div>
      <div class="stat-row"><span class="k">duplicates</span><span class="v">${s.duplicated_keys}</span></div>
      <div class="stat-row"><span class="k">invalid lines</span><span class="v">${s.invalid_lines}</span></div>
      <div class="stat-row"><span class="k">empty values</span><span class="v">${s.empty_values}</span></div>
      ${s.missing_ranges.length ? `
        <details><summary style="cursor:pointer;font-family:var(--mono);font-size:12px;color:var(--amber)">
          ${s.missing_ranges.length} missing range(s)</summary>
          <div style="max-height:180px;overflow-y:auto;font-family:var(--mono);font-size:12px;color:var(--text-dim);margin-top:6px">
            ${s.missing_ranges.map(esc).join(", ")}</div>
        </details>` : `<p class="keybar-label" style="color:var(--green)">Nothing missing — full coverage.</p>`}
    </div>`;

  out.innerHTML = `
    <div class="banner">union ${fmt(d.union_keys)} keys &middot; common ${fmt(d.common_keys)} keys</div>
    <div class="grid cols-2">${side(d.a, "A")}${side(d.b, "B")}</div>
    <div class="grid cols-2" style="margin-top:18px">
      <div class="card"><h3>Key counts</h3><div class="chart-box"><canvas id="ch-keys"></canvas></div></div>
      <div class="card"><h3>Key overlap</h3><div class="chart-box"><canvas id="ch-overlap"></canvas></div></div>
    </div>`;

  destroyCharts();
  if (window.Chart) {
    makeChart(document.getElementById("ch-keys"), {
      type: "bar",
      data: {
        labels: [d.a.name, d.b.name],
        datasets: [
          { label: "present", data: [d.a.total_keys, d.b.total_keys], backgroundColor: CHART_COLORS.olive },
          { label: "missing", data: [d.a.missing_keys, d.b.missing_keys], backgroundColor: CHART_COLORS.red },
        ],
      },
      options: {
        maintainAspectRatio: false, responsive: true,
        scales: { x: { stacked: true, ticks: { callback: (v, i) => (i === 0 ? "A" : "B") } }, y: { stacked: true } },
      },
    });
    makeChart(document.getElementById("ch-overlap"), {
      type: "doughnut",
      data: {
        labels: ["common", "only in A", "only in B"],
        datasets: [{
          data: [d.common_keys, d.b.missing_keys, d.a.missing_keys],
          backgroundColor: [CHART_COLORS.green, CHART_COLORS.amber, CHART_COLORS.red],
          borderColor: "#12140e",
        }],
      },
      options: { maintainAspectRatio: false, responsive: true, cutout: "60%" },
    });
  }
}

/* ---------------------------------------------------------------- merge */
async function renderMerge(params) {
  view.innerHTML = `<div class="loading">Loading files</div>`;
  const files = await loadFiles();

  view.innerHTML = `
    <h2 class="section-title">MERGE</h2>
    <p class="section-sub">Graft the missing ids of the <em>source</em> onto the <em>target</em>.
       Target text is preserved verbatim; nothing is ever translated and originals are never touched.</p>
    ${files.length < 2 ? `
      <div class="empty"><span class="empty-icon">&#9874;</span>
        You need at least two stored files to merge. <a href="#/upload">Upload one</a> first.</div>` : `
      <div class="card" style="max-width:760px">
        <div class="form-row">
          <label class="field">Target (text preserved)
            <select id="m-target"><option value="">—</option>${fileOptions(files, params.get("target"))}</select></label>
          <label class="field">Source (contributes missing ids)
            <select id="m-source"><option value="">—</option>${fileOptions(files, params.get("source"))}</select></label>
        </div>
        <div class="form-row">
          <label class="toggle" data-tip="Missing ids get a literal <MISSING> placeholder — shown verbatim in-game until a human translates them.">
            <input type="radio" name="mode" value="placeholder" checked> &lt;MISSING&gt; placeholders</label>
          <label class="toggle" data-tip="Missing ids get the source file's ORIGINAL text, copied verbatim. Never machine-translated.">
            <input type="radio" name="mode" value="fill_from_source"> fill from source (verbatim)</label>
        </div>
        <button class="btn" id="m-go">&#9874; Merge</button>
        <div id="merge-out"></div>
      </div>`}
  `;
  if (files.length < 2) return;

  document.getElementById("m-go").addEventListener("click", async () => {
    const target_id = document.getElementById("m-target").value;
    const source_id = document.getElementById("m-source").value;
    const mode = document.querySelector('input[name="mode"]:checked').value;
    const out = document.getElementById("merge-out");
    if (!target_id || !source_id) { toast("Pick target and source first"); return; }
    if (target_id === source_id) { toast("Target and source must differ"); return; }
    out.innerHTML = `<div class="loading">Merging</div>`;
    try {
      const r = await api("/api/merge", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ target_id, source_id, mode }),
      });
      out.innerHTML = `
        <div class="banner">
          Merge complete: <strong>${fmt(r.total_entries)}</strong> entries
          (${fmt(r.preserved)} preserved, ${fmt(r.added)} added via <code>${esc(r.mode)}</code>).<br>
          <a class="btn small" style="margin-top:10px;display:inline-block" href="${r.download_url}">&#8681; Download ${esc(r.filename)}</a>
        </div>`;
    } catch (err) {
      out.innerHTML = `<div class="banner error">${esc(err.message)}</div>`;
    }
  });
}

/* ---------------------------------------------------------------- tools */
async function renderTools() {
  view.innerHTML = `<div class="loading">Fetching intel</div>`;
  const tools = (await api("/api/tools")).tools;
  view.innerHTML = `
    <h2 class="section-title">EXTERNAL TOOLS &amp; INTEL</h2>
    <p class="section-sub">Curated field kit for CoH1 localization work — editors, depot archaeology and community lore.</p>
    <div class="grid cols-3">
      ${tools.map(t => `
        <div class="card tool-card">
          <span class="cat">${esc(t.category)}</span>
          <h3><a href="${esc(t.url)}" target="_blank" rel="noopener">${esc(t.name)} &#8599;</a></h3>
          <p>${esc(t.description)}</p>
        </div>`).join("")}
    </div>
    <div class="card" style="margin-top:24px">
      <h3>This service's own API</h3>
      <p style="color:var(--text-dim)">Everything the UI does goes through the documented REST API.
      Explore it live in <a href="/docs" target="_blank" rel="noopener">Swagger UI</a>,
      read it in <a href="/redoc" target="_blank" rel="noopener">ReDoc</a>, or grab the raw
      <a href="/openapi.json" target="_blank" rel="noopener">openapi.json</a>.</p>
    </div>`;
}

/* --------------------------------------------------------------- router */
const routes = {
  dashboard: renderDashboard,
  upload: renderUpload,
  compare: renderCompare,
  merge: renderMerge,
  tools: renderTools,
};

async function route() {
  destroyCharts();
  const hash = location.hash.slice(2) || "dashboard"; // strip "#/"
  const [name, query] = hash.split("?");
  const params = new URLSearchParams(query || "");
  const handler = routes[name] || renderDashboard;
  document.querySelectorAll("#nav a[data-route]").forEach(a =>
    a.classList.toggle("active", a.dataset.route === (routes[name] ? name : "dashboard")));
  try {
    await handler(params);
  } catch (err) {
    view.innerHTML = `<div class="banner error">Console fault: ${esc(err.message)}</div>`;
  }
}

window.addEventListener("hashchange", route);
route();
