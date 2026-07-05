/* Extended SPA sections — diff, languages, search, settings, etc. */

import {
  api, apiUrl, esc, fmt, loadFiles, fileOptions, isHybridUi, toast, destroyCharts, makeChart,
  getChartColors, profileQueryString, profileBarHtml, bindProfileBar, isRouteAbortError,
  getView, renderPaneError,
} from "./core.js";
import { navigateRoute, routePath } from "./router.js";
import { t, setLocale } from "./i18n.js";
import { patchHtml, q, setViewHtml } from "./routeScope.js";

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
  toast(t("msg.copied_clipboard"));
}

/* ------------------------------------------------------------------ diff */
export async function renderDiff(params) {
  if (!setViewHtml(`<div class="loading">${t("msg.loading")}</div>`)) return;
  const files = await loadFiles();
  const a = params.get("a") || "", b = params.get("b") || "", filter = params.get("filter") || "changed";
  if (!setViewHtml(`
    <h2 class="section-title">${t("route.diff")}</h2>
    <p class="section-sub">${t("route.diff.sub")}</p>
    <div class="form-row section">
      <label class="field">${t("label.file_a")}<select id="d-a"><option value="">—</option>${fileOptions(files, a)}</select></label>
      <label class="field">${t("label.file_b")}<select id="d-b"><option value="">—</option>${fileOptions(files, b)}</select></label>
      <label class="field">${t("label.filter")}<select id="d-f">
        ${["changed", "missing", "empty", "token_mismatch"].map(f =>
          `<option value="${f}" ${f === filter ? "selected" : ""}>${t("filter." + f)}</option>`).join("")}
      </select></label>
      <button class="btn" id="d-go">${t("btn.diff")}</button>
    </div>
    <div id="diff-out"></div>`)) return;
  document.getElementById("d-go").onclick = () => {
    const va = document.getElementById("d-a").value, vb = document.getElementById("d-b").value;
    if (!va || !vb) { toast(t("msg.pick_both")); return; }
    navigateRoute("diff", { a: va, b: vb, filter: document.getElementById("d-f").value });
  };
  if (a && b) await runDiff(a, b, filter);
}

async function runDiff(a, b, filter) {
  const out = document.getElementById("diff-out");
  if (!patchHtml(out.id, `<div class="loading">${t("msg.diffing")}</div>`)) return;
  try {
    const d = await api(`/api/files/${a}/diff/${b}?filter=${filter}&limit=200`);
    if (!patchHtml(out.id, `
      <div class="banner">${t("misc.rows_filter", { count: fmt(d.total) })} <code>${esc(filter)}</code>
        <button class="btn ghost small copy-btn copy-btn-inline">${t("btn.copy_table")}</button></div>
      <div class="table-wrap"><table class="data" id="diff-table">
        <thead><tr><th>${t("table.id")}</th><th>${t("table.kind_col")}</th><th>A</th><th>B</th></tr></thead>
        <tbody>${d.rows.map(r => `<tr>
          <td class="num">${r.key}</td><td>${esc(r.kind)}</td>
          <td class="val">${r.a_value != null ? highlightTokens(r.a_value) : "<em>—</em>"}</td>
          <td class="val">${r.b_value != null ? highlightTokens(r.b_value) : "<em>—</em>"}</td>
        </tr>`).join("")}</tbody></table></div>`)) return;
    out.querySelector(".copy-btn")?.addEventListener("click", e => copyTable(e.target, "#diff-table"));
  } catch (err) {
    if (!isRouteAbortError(err)) renderPaneError(err, out.id, { retry: () => runDiff(a, b, filter) });
  }
}

/* --------------------------------------------------------------- ranges */
export async function renderRanges(params) {
  if (!setViewHtml(`<div class="loading">${t("msg.loading")}</div>`)) return;
  const files = await loadFiles();
  const a = params.get("a") || "", b = params.get("b") || "";
  if (!setViewHtml(`
    <h2 class="section-title">${t("route.ranges")}</h2>
    <p class="section-sub">${t("route.ranges.sub")}</p>
    <div class="form-row">
      <label class="field">A<select id="r-a">${fileOptions(files, a)}</select></label>
      <label class="field">B<select id="r-b">${fileOptions(files, b)}</select></label>
      <button class="btn" id="r-go">${t("btn.load")}</button>
    </div>
    <div id="ranges-out"></div>`)) return;
  document.getElementById("r-go").onclick = () => {
    navigateRoute("ranges", { a: document.getElementById("r-a").value, b: document.getElementById("r-b").value });
  };
  if (a && b) await loadRanges(a, b);
}

async function loadRanges(a, b) {
  const out = document.getElementById("ranges-out");
  try {
    const d = await api(`/api/compare/${a}/${b}/ranges`);
    const bar = (segments, label, fileId) => {
      const max = Math.max(...segments.map(s => s.count), 1);
      return `<div class="card"><h3>${t("misc.missing_in", { label: esc(label) })}</h3>
        ${segments.length ? segments.map(s => `
          <div class="range-bar" data-file="${fileId}" data-start="${s.start}" data-end="${s.end}" title="${s.start}–${s.end}: ${s.count}">
            <i style="width:${(100 * s.count / max).toFixed(1)}%"></i>
            <span>${s.start}–${s.end} (${s.count})</span>
          </div>`).join("") : `<p class="keybar-label good-text">${t("misc.full_coverage")}</p>`}
      </div>`;
    };
    if (!patchHtml(out.id, `<div class="grid cols-2">${bar(d.a_missing, "A", a)}${bar(d.b_missing, "B", b)}</div>
      <div id="range-lookup"></div>`)) return;
    out.querySelectorAll(".range-bar").forEach(barEl => barEl.addEventListener("click", async () => {
      try {
        const fid = barEl.dataset.file;
        const p = new URLSearchParams({ search: barEl.dataset.start, limit: 20 });
        const entries = await api(`/api/files/${fid}/entries?${p}`);
        patchHtml("range-lookup", `
          <h3 class="section-title mt-md">${t("misc.lookup", { start: barEl.dataset.start, end: barEl.dataset.end })}</h3>
          <div class="table-wrap"><table class="data"><tbody>
            ${entries.entries.map(e => `<tr><td class="num">${e.key}</td><td class="val">${esc(e.value)}</td></tr>`).join("")}
          </tbody></table></div>`);
      } catch (err) {
        if (!isRouteAbortError(err)) renderPaneError(err, "range-lookup");
      }
    }));
  } catch (err) {
    if (!isRouteAbortError(err)) renderPaneError(err, out.id, { retry: () => loadRanges(a, b) });
  }
}

/* ------------------------------------------------------------ validator */
export async function renderValidator(params) {
  const files = await loadFiles();
  const fid = params.get("file") || "";
  if (!setViewHtml(`
    <h2 class="section-title">${t("route.validator")}</h2>
    <p class="section-sub">${t("route.validator.sub")}</p>
    <label class="field">${t("label.file")}<select id="v-file"><option value="">—</option>${fileOptions(files, fid)}</select></label>
    <div id="v-out"></div>`)) return;
  document.getElementById("v-file").onchange = () => {
    const v = document.getElementById("v-file").value;
    if (v) navigateRoute("validator", { file: v });
  };
  if (fid) await loadValidator(fid);
}

async function loadValidator(fid) {
  const out = document.getElementById("v-out");
  if (!patchHtml(out.id, `<div class="loading">${t("msg.validating")}</div>`)) return;
  try {
    const [val, lint, issues] = await Promise.all([
      api(`/api/files/${fid}/validate`),
      api(`/api/files/${fid}/lint`),
      api(`/api/files/${fid}/issues`),
    ]);
    if (!patchHtml(out.id, `
      <div class="grid cols-2">
        <div class="card"><h3>${t("stat.validation")}</h3>
          <div class="stat-row"><span class="k">${t("stat.status")}</span><span class="v ${val.ok ? "good" : "bad"}">${val.ok ? t("status.ok") : t("status.failed")}</span></div>
          <div class="stat-row"><span class="k">${t("stat.errors")}</span><span class="v">${val.errors}</span></div>
          <div class="stat-row"><span class="k">${t("stat.warnings")}</span><span class="v">${val.warnings}</span></div>
          <a class="btn ghost small" href="${apiUrl(`/api/files/${fid}/issues.csv`)}">${t("btn.export_csv")}</a>
        </div>
        <div class="card"><h3>${t("stat.lint")}</h3>
          <div class="stat-row"><span class="k">${t("stat.token_issues")}</span><span class="v">${lint.token_issue_count}</span></div>
          <div class="stat-row"><span class="k">${t("stat.script_findings")}</span><span class="v">${lint.script_finding_count}</span></div>
          <div class="stat-row"><span class="k">${t("stat.entries_issues")}</span><span class="v">${lint.entries_with_issues}</span></div>
        </div>
      </div>
      <div class="table-wrap mt-sm"><table class="data">
        <thead><tr><th>${t("table.type")}</th><th>${t("table.id")}</th><th>${t("table.detail")}</th></tr></thead>
        <tbody>
          ${issues.duplicates.map(d => `<tr><td>${t("table.duplicate")}</td><td class="num">${d.key}</td><td>${t("misc.lines_detail", {lines: d.lines.join(", ")})}</td></tr>`).join("")}
          ${issues.invalid_lines.map(l => `<tr><td>${t("table.invalid")}</td><td>${l.line}</td><td>${esc(l.reason)}</td></tr>`).join("")}
        </tbody></table></div>`)) return;
  } catch (err) {
    if (!isRouteAbortError(err)) renderPaneError(err, out.id, { retry: () => loadValidator(fid) });
  }
}

/* ------------------------------------------------------------- languages */
export async function renderLanguages() {
  if (!setViewHtml(`<div class="loading">${t("msg.loading")}</div>`)) return;
  try {
    const [d, cov] = await Promise.all([api("/api/languages"), api("/api/languages/coverage")]);
    const covMap = Object.fromEntries((cov.locales || []).map(r => [r.code, r]));
    if (!setViewHtml(`
      <h2 class="section-title">${t("route.languages")}</h2>
      <p class="section-sub">${t("route.languages.sub", { keys: fmt(d.reference_keys) })}
        <a href="${apiUrl("/api/languages/coverage.csv")}" class="btn ghost small ml-sm">${t("btn.export_csv")}</a>
      </p>
      ${!(covMap.FR && covMap.FR.found) ? `
      <div class="banner mb-md">
        <strong>${t("banner.french_title")}</strong>
        ${t("banner.french_body")}
      </div>` : ""}
      <div class="card mb-md">
        <h3 class="card-heading-sm">${t("misc.coverage_comparison")}</h3>
        <div class="chart-box chart-h-md"><canvas id="cov-bar"></canvas></div>
      </div>
      <div class="table-wrap mb-md">
        <table class="data"><thead><tr>
          <th>${t("table.code")}</th><th>${t("table.found")}</th><th>${t("table.keys")}</th><th>${t("table.coverage")}</th>
          <th>${t("table.missing")}</th><th>${t("table.placeholders")}</th><th>${t("table.gaps")}</th>
        </tr></thead><tbody>
          ${(cov.locales || []).map(r => `<tr>
            <td>${esc(r.code)}</td>
            <td>${r.found ? t("misc.yes") : "—"}</td>
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
          <div class="chart-box chart-h-sm"><canvas id="donut-${l.code}"></canvas></div>
          <div class="stat-row"><span class="k">${t("stat.keys")}</span><span class="v">${fmt(l.keys)}</span></div>
          <div class="stat-row"><span class="k">${t("stat.coverage")}</span><span class="v">${l.coverage_percent}%</span></div>
          ${extra && extra.found ? `<div class="stat-row"><span class="k">${t("stat.missing_vs_ru")}</span><span class="v">${fmt(extra.missing_vs_reference)}</span></div>
          <div class="stat-row"><span class="k">${t("table.placeholders")}</span><span class="v">${fmt(extra.placeholders)}</span></div>` : ""}
          <p class="text-dim-sm">${esc(l.notes)}</p>
          ${l.download_url ? `<a class="btn ghost small" href="${l.download_url}">${t("btn.download")}</a>` : ""}
        </div>`;
      }).join("")}</div>`)) return;
    destroyCharts();
    const colors = getChartColors();
    try {
      const labels = (cov.locales || []).filter(r => r.found).map(r => r.code);
      const data = (cov.locales || []).filter(r => r.found).map(r => r.coverage_percent);
      const bar = document.getElementById("cov-bar");
      if (bar && labels.length) {
        await makeChart(bar, {
          type: "bar",
          data: { labels, datasets: [{ label: t("misc.coverage_pct"), data, backgroundColor: colors.olive }] },
          options: { maintainAspectRatio: false, scales: { y: { max: 100, beginAtZero: true } }, plugins: { legend: { display: false } } },
        });
      }
      for (const l of d.languages) {
        const ctx = document.getElementById(`donut-${l.code}`);
        if (!ctx) continue;
        await makeChart(ctx, {
          type: "doughnut",
          data: {
            labels: [t("misc.covered"), t("misc.gap")],
            datasets: [{ data: [l.coverage_percent, 100 - l.coverage_percent],
              backgroundColor: [colors.green, colors.dim], borderColor: "transparent" }],
          },
          options: { maintainAspectRatio: false, plugins: { legend: { display: false } }, cutout: "65%" },
        });
      }
    } catch { /* Chart.js unavailable offline */ }
  } catch (err) {
    if (!isRouteAbortError(err)) {
      const view = getView();
      if (view?.id) renderPaneError(err, view.id);
    }
  }
}

/* ---------------------------------------------------------- merge wizard */
export async function renderMergeWizard(params) {
  const files = await loadFiles();
  const tab = params.get("tab") || "twoway";
  if (!setViewHtml(`
    <h2 class="section-title">${t("route.merge_wizard")}</h2>
    <p class="section-sub">${t("route.merge_wizard.sub")}</p>
    ${profileBarHtml()}
    <div class="form-row mb-sm">
      <a class="btn ghost small ${tab === "twoway" ? "active" : ""}" href="${routePath("merge-wizard", { tab: "twoway" })}">${t("tab.twoway")}</a>
      <a class="btn ghost small ${tab === "threeway" ? "active" : ""}" href="${routePath("merge-wizard", { tab: "threeway" })}">${t("tab.threeway")}</a>
    </div>
    <div id="mw-panel"></div>`)) return;
  bindProfileBar(getView());
  if (tab === "threeway") await renderThreewayPanel(files, params);
  else await renderTwowayPanel(files, params);
}

async function renderTwowayPanel(files, params) {
  patchHtml("mw-panel", `
    <div class="card max-w-card">
      <div class="form-row">
        <label class="field">1. ${t("label.target")}<select id="mw-t">${fileOptions(files, params.get("target") || "")}</select></label>
        <label class="field">2. ${t("label.source")}<select id="mw-s">${fileOptions(files, params.get("source") || "")}</select></label>
      </div>
      <div class="form-row">
        <label class="toggle"><input type="radio" name="mw-m" value="placeholder" checked> ${t("tab.placeholders")}</label>
        <label class="toggle"><input type="radio" name="mw-m" value="fill_from_source"> ${t("tab.fill_verbatim")}</label>
        <button class="btn ghost" id="mw-preview">${t("btn.preview")}</button>
        <button class="btn" id="mw-run">${t("btn.merge")}</button>
      </div>
      <div id="mw-out"></div>
    </div>`);
  document.getElementById("mw-preview").onclick = async () => {
    const out = document.getElementById("mw-out");
    if (!patchHtml(out.id, `<div class="loading">${t("misc.preview")}</div>`)) return;
    try {
      const mode = document.querySelector('input[name="mw-m"]:checked').value;
      const r = await api(`/api/merge/preview?${profileQueryString()}`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          target_id: document.getElementById("mw-t").value,
          source_id: document.getElementById("mw-s").value,
          mode, limit: 30,
        }),
      });
      if (!patchHtml(out.id, `<div class="banner">${t("misc.would_add", { count: fmt(r.total_would_add) })}</div>
        <div class="table-wrap"><table class="data"><thead><tr><th>${t("table.id")}</th><th>${t("table.source_col")}</th><th>${t("table.result")}</th></tr></thead>
        <tbody>${r.preview.map(p => `<tr><td class="num">${p.key}</td><td class="val">${esc(p.source_value || "")}</td><td class="val">${esc(p.result_value)}</td></tr>`).join("")}</tbody></table></div>`)) return;
    } catch (err) {
      if (!isRouteAbortError(err)) renderPaneError(err, out.id);
    }
  };
  document.getElementById("mw-run").onclick = async () => {
    try {
      const mode = document.querySelector('input[name="mw-m"]:checked').value;
      const r = await api(`/api/merge?${profileQueryString()}`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          target_id: document.getElementById("mw-t").value,
          source_id: document.getElementById("mw-s").value,
          mode,
        }),
      });
      toast(t("msg.merge_complete"));
      patchHtml("mw-out", `<div class="banner"><a href="${r.download_url}">${t("misc.download_filename", { name: esc(r.filename) })}</a></div>`);
    } catch (err) {
      if (!isRouteAbortError(err)) renderPaneError(err, "mw-out");
    }
  };
}

async function renderThreewayPanel(files, params) {
  patchHtml("mw-panel", `
    <div class="card max-w-card">
      <p class="section-sub">${t("misc.threeway_desc")}</p>
      <div class="form-row">
        <label class="field">${t("label.base")}<select id="3w-b">${fileOptions(files, params.get("base") || "")}</select></label>
        <label class="field">${t("label.branch_a")}<select id="3w-a">${fileOptions(files, params.get("a") || "")}</select></label>
        <label class="field">${t("label.branch_b")}<select id="3w-b2">${fileOptions(files, params.get("b") || "")}</select></label>
      </div>
      <div class="form-row">
        <label class="field">${t("label.strategy")}<select id="3w-s">
          <option value="prefer_a">${t("tab.prefer_a")}</option>
          <option value="prefer_b">${t("tab.prefer_b")}</option>
          <option value="manual_conflicts">${t("tab.manual_conflicts")}</option>
        </select></label>
        <button class="btn" id="3w-go">${t("misc.threeway_merge")}</button>
      </div>
      <div id="3w-out"></div>
    </div>`);
  document.getElementById("3w-go").onclick = async () => {
    const out = document.getElementById("3w-out");
    if (!patchHtml(out.id, `<div class="loading">${t("misc.merging")}</div>`)) return;
    const body = {
      base_id: document.getElementById("3w-b").value,
      a_id: document.getElementById("3w-a").value,
      b_id: document.getElementById("3w-b2").value,
      strategy: document.getElementById("3w-s").value,
    };
    if (!body.base_id || !body.a_id || !body.b_id) { toast(t("msg.pick_three")); return; }
    try {
      const r = await api("/api/merge/threeway", { method: "POST", body: JSON.stringify(body) });
      if (!patchHtml(out.id, `
        <div class="banner"><a href="${r.download_url}">${t("misc.download_merged", { keys: fmt(r.keys) })}</a>
          · ${t("misc.conflicts", { count: r.conflicts.length })}</div>
        ${r.conflicts.length ? `<div class="table-wrap"><table class="data"><thead><tr><th>${t("table.id")}</th><th>${t("label.base")}</th><th>A</th><th>B</th></tr></thead>
          <tbody>${r.conflicts.slice(0, 50).map(c => `<tr><td class="num">${c.key}</td>
            <td class="val">${esc(c.base || "—")}</td><td class="val">${esc(c.a || "—")}</td><td class="val">${esc(c.b || "—")}</td></tr>`).join("")}
          </tbody></table></div>` : ""}`)) return;
    } catch (err) {
      if (!isRouteAbortError(err)) renderPaneError(err, out.id);
    }
  };
}

/* --------------------------------------------------------------- install */
export async function renderInstall() {
  if (!setViewHtml(`<h2 class="section-title">${t("route.install")}</h2>
    <button class="btn" id="inst-go">${t("btn.scan")}</button><div id="inst-out"></div>`)) return;
  document.getElementById("inst-go").onclick = async () => {
    try {
      const d = await api("/api/install/detect");
      patchHtml("inst-out", `
        <div class="grid cols-2 mt-sm">${d.candidates.map(c => `
          <div class="card"><h3>${esc(c.install_type)}</h3>
            <div class="stat-row"><span class="k">${t("stat.found")}</span><span class="v ${c.exists ? "good" : "bad"}">${c.exists ? t("misc.yes") : t("misc.no")}</span></div>
            ${c.ucs_path ? `<div class="stat-row"><span class="k">ucs</span><span class="v text-dim-sm">${esc(c.ucs_path)}</span></div>` : ""}
          </div>`).join("")}</div>
        <div class="card mt-sm"><h3>${t("misc.powershell")}</h3>
          <pre class="mono-block">${esc(d.backup_command)}\n${esc(d.copy_command)}</pre>
          <button class="btn ghost small" id="copy-ps">${t("btn.copy")}</button></div>`);
      document.getElementById("copy-ps").onclick = () => {
        navigator.clipboard.writeText(`${d.backup_command}\n${d.copy_command}`);
        toast(t("msg.copied"));
      };
    } catch (err) {
      if (!isRouteAbortError(err)) renderPaneError(err, "inst-out");
    }
  };
}

/* ---------------------------------------------------------------- mt lab */
export async function renderMtLab() {
  const files = await loadFiles();
  if (!setViewHtml(`
    <h2 class="section-title">${t("route.mt")}</h2>
    <p class="section-sub">${t("route.mt.sub")}</p>
    <div class="form-row">
      <label class="field">${t("label.source")}<select id="mt-s">${fileOptions(files, "")}</select></label>
      <label class="field">sl<input id="mt-sl" value="ru"></label>
      <label class="field">tl<input id="mt-tl" value="en"></label>
      <label class="field">limit<input id="mt-lim" type="number" value="20"></label>
      <button class="btn" id="mt-q">${t("btn.queue")}</button>
    </div>
    <div id="mt-status"></div><div id="mt-report"></div>`)) return;
  async function poll() {
    try {
      const s = await api("/api/mt/status");
      patchHtml("mt-status", `
        <div class="banner">${esc(s.status)} — ${s.progress}/${s.total} ${esc(s.message)}</div>
        <div class="keybar"><i style="width:${s.total ? 100 * s.progress / s.total : 0}%"></i></div>`);
      if (s.status === "done") {
        const r = await api("/api/mt/report");
        patchHtml("mt-report", `
          <div class="table-wrap"><table class="data"><thead><tr>
            <th>${t("table.id")}</th><th>${t("table.source_col")}</th><th>${t("table.mt")}</th><th>${t("table.ref")}</th>
          </tr></thead>
          <tbody>${(r.rows || []).slice(0, 50).map(row => `<tr>
            <td class="num">${row.key}</td><td class="val">${esc(row.source)}</td>
            <td class="val">${esc(row.mt)}</td><td class="val">${esc(row.reference)}</td></tr>`).join("")}
          </tbody></table></div>`);
      } else if (s.status === "running") setTimeout(poll, 2000);
    } catch (err) {
      if (!isRouteAbortError(err)) renderPaneError(err, "mt-status");
    }
  }
  document.getElementById("mt-q").onclick = async () => {
    try {
      await api("/api/mt/queue", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          source_id: document.getElementById("mt-s").value,
          sl: document.getElementById("mt-sl").value,
          tl: document.getElementById("mt-tl").value,
          limit: +document.getElementById("mt-lim").value,
        }),
      });
      poll();
    } catch (err) {
      if (!isRouteAbortError(err)) renderPaneError(err, "mt-status");
    }
  };
  poll();
}

/* -------------------------------------------------------------- glossary */
export async function renderGlossary() {
  const d = await api("/api/glossary");
  const rows = Object.entries(d.terms);
  if (!setViewHtml(`
    <h2 class="section-title">${t("route.glossary")}</h2>
    <p class="section-sub">${t("route.glossary.sub")}</p>
    <div class="table-wrap"><table class="data" id="gl-table">
      <thead><tr><th>${t("table.term")}</th><th>${t("table.fixed_translation")}</th><th></th></tr></thead>
      <tbody>${rows.map(([k, v]) => `<tr><td><input value="${esc(k)}" class="gl-k"></td>
        <td><input value="${esc(v)}" class="gl-v"></td><td><button class="btn ghost small gl-rm">×</button></td></tr>`).join("")}
      </tbody></table></div>
    <button class="btn ghost" id="gl-add">${t("btn.add_row")}</button>
    <button class="btn" id="gl-save">${t("btn.save")}</button>`)) return;
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
    await api("/api/glossary", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ terms }) });
    toast(t("msg.glossary_saved"));
  };
  document.getElementById("gl-table").addEventListener("click", e => {
    if (e.target.classList.contains("gl-rm")) e.target.closest("tr").remove();
  });
}

/* -------------------------------------------------------------- timeline */
export async function renderTimeline() {
  const d = await api("/api/versions/timeline");
  if (!setViewHtml(`
    <h2 class="section-title">${t("route.timeline")}</h2>
    <p class="section-sub">${t("route.timeline.sub")}</p>
    <div class="timeline">${d.entries.map(e => `
      <div class="timeline-item ${e.available ? "" : "dim"}">
        <div class="tl-era">${esc(e.era)}</div>
        <h3>${esc(e.name)}</h3>
        <div class="stat-row"><span class="k">${t("stat.keys")}</span><span class="v">${fmt(e.keys)}</span></div>
        <p class="text-dim-sm">${esc(e.notes)}</p>
      </div>`).join("")}</div>`)) return;
}

/* -------------------------------------------------------- depots/sources */
export async function renderDepots() {
  const [dep, src] = await Promise.all([api("/api/depots"), api("/api/sources")]);
  const dd = dep.depotdownloader
    ? t("misc.depot_found", { path: esc(dep.depotdownloader) })
    : t("misc.depot_not_path");
  if (!setViewHtml(`
    <h2 class="section-title">${t("route.depots")}</h2>
    <p class="section-sub">${t("route.depots.sub")}</p>
    <p class="muted mb-sm">${dd}. ${t("misc.depot_env")}</p>
    <div class="grid cols-2">
      <div><h3 class="section-heading-sm">${t("misc.depots_heading")}</h3>
        ${dep.depots.map(d => `<div class="card" data-lang="${esc(d.language.toLowerCase())}"><h3>${esc(d.language)} (app ${d.app_id})</h3>
          <p>${esc(d.description)}</p><pre class="mono-block">${esc(d.command_template)}</pre>
          <p class="muted text-dim-sm">→ ${esc(d.expected_file || "")}</p>
          <div class="form-row mt-sm">
            <button class="btn small depot-dl" ${dep.depotdownloader ? "" : "disabled"}>${t("btn.download")}</button>
            <button class="btn ghost small depot-build" ${d.build_script ? "" : "disabled"}>${t("btn.import_build")}</button>
          </div>
          <div class="depot-out" id="depot-out-${esc(d.language.toLowerCase())}"></div></div>`).join("")}
      </div>
      <div><h3 class="section-heading-sm">${t("misc.sources_heading")}</h3>
        ${src.sources.map(s => `<div class="card tool-card"><span class="cat">${esc(s.trust)}</span>
          <h3><a href="${esc(s.url)}" target="_blank">${esc(s.name)}</a></h3><p>${esc(s.description)}</p></div>`).join("")}
      </div>
    </div>`)) return;
  document.querySelectorAll(".depot-dl").forEach(btn => {
    btn.onclick = async () => {
      const card = btn.closest(".card");
      const lang = card.dataset.lang;
      const out = card.querySelector(".depot-out");
      out.textContent = t("misc.downloading");
      try {
        const r = await api("/api/depot/download", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ language: lang, build: true }),
        });
        if (r.download && r.download.success) {
          if (!patchHtml(out.id, t("misc.depot_ok", {path: `<code>${esc(r.download.dest)}</code>`, bytes: r.download.bytes}))) return;
          if (r.build) out.innerHTML += r.build.built ? " · build OK" : ` · ${t("misc.build_failed")}`;
        } else {
          out.textContent = r.error || r.stderr_tail || t("misc.download_failed");
        }
      } catch (e) {
        if (!isRouteAbortError(e)) renderPaneError(e, out.id);
      }
    };
  });
  document.querySelectorAll(".depot-build").forEach(btn => {
    btn.onclick = async () => {
      const card = btn.closest(".card");
      const lang = card.dataset.lang;
      const out = card.querySelector(".depot-out");
      out.textContent = t("misc.building");
      try {
        const r = await api("/api/depot/import", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ language: lang }),
        });
        out.textContent = r.built ? t("misc.build_ok", {version: r.version_id || lang}) : (r.stderr || t("misc.build_failed"));
      } catch (e) {
        if (!isRouteAbortError(e)) renderPaneError(e, out.id);
      }
    };
  });
}

/* ---------------------------------------------------------------- search */
export async function renderSearch(params) {
  const query = params.get("q") || "";
  if (!setViewHtml(`
    <h2 class="section-title">${t("route.search")}</h2>
    <p class="section-sub">${t("route.search.sub")}</p>
    <div class="form-row">
      <label class="field field-flex-2"><input id="sq" value="${esc(query)}" placeholder="${t("placeholder.query")}"></label>
      <label class="toggle"><input type="checkbox" id="sq-fuzzy"> ${t("misc.fuzzy")}</label>
      <label class="toggle"><input type="checkbox" id="sq-regex"> ${t("misc.regex")}</label>
      <button class="btn" id="sq-go">${t("btn.search")}</button>
    </div>
    <div id="search-out"></div>
    <div id="xref-out"></div>`)) return;
  document.getElementById("sq-go").onclick = () => runSearch();
  if (query) runSearch();
  async function runSearch() {
    const qVal = document.getElementById("sq").value;
    navigateRoute("search", { q: qVal });
    const p = new URLSearchParams({ q: qVal });
    if (document.getElementById("sq-fuzzy").checked) p.set("fuzzy", "true");
    if (document.getElementById("sq-regex").checked) p.set("regex", "true");
    try {
      const d = await api(`/api/search/global?${p}`);
      patchHtml("search-out", `
        <div class="table-wrap"><table class="data"><thead><tr>
          <th>${t("table.file")}</th><th>${t("table.id")}</th><th>${t("table.text")}</th><th>${t("table.score")}</th>
        </tr></thead>
        <tbody>${d.hits.map(h => `<tr data-key="${h.key}">
          <td>${esc(h.file_name)}</td><td class="num"><a href="#" class="xref-link">${h.key}</a></td>
          <td class="val">${esc(h.value)}</td><td>${h.score ?? ""}</td></tr>`).join("")}
        </tbody></table></div>`);
      document.querySelectorAll(".xref-link").forEach(a => a.addEventListener("click", async e => {
        e.preventDefault();
        const key = a.textContent;
        try {
          const x = await api(`/api/crossref/${key}`);
          patchHtml("xref-out", `
            <h3>${t("misc.crossref", { key })}</h3><div class="table-wrap"><table class="data"><thead><tr>
              <th>${t("table.file")}</th><th>${t("table.value")}</th><th>${t("table.sim")}</th>
            </tr></thead>
            <tbody>${x.versions.map(v => `<tr><td>${esc(v.file_name)}</td><td class="val">${esc(v.value || "")}</td><td>${v.similarity}</td></tr>`).join("")}
            </tbody></table></div>`);
        } catch (err) {
          if (!isRouteAbortError(err)) renderPaneError(err, "xref-out");
        }
      }));
    } catch (err) {
      if (!isRouteAbortError(err)) renderPaneError(err, "search-out", { retry: runSearch });
    }
  }
}

/* ------------------------------------------------------------- bookmarks */
export async function renderBookmarks() {
  const d = await api("/api/bookmarks");
  if (!setViewHtml(`
    <h2 class="section-title">${t("route.bookmarks")}</h2>
    <p class="section-sub">${t("route.bookmarks.sub")}</p>
    <div class="form-row">
      <input id="bm-add" placeholder="${t("label.numeric_id")}">
      <button class="btn" id="bm-go">${t("btn.add")}</button>
    </div>
    <ul class="bm-list">${d.ids.map(id => `<li>${id} <button data-rm="${id}" class="btn ghost small">${t("btn.remove")}</button></li>`).join("")}</ul>`)) return;
  document.getElementById("bm-go").onclick = async () => {
    const id = +document.getElementById("bm-add").value;
    if (!id) return;
    await api("/api/bookmarks", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ids: [id] }) });
    renderBookmarks();
  };
  (getView() || document).querySelectorAll("[data-rm]").forEach(b => b.onclick = async () => {
    await api(`/api/bookmarks/${b.dataset.rm}`, { method: "DELETE" });
    renderBookmarks();
  });
}

/* ---------------------------------------------------------- patch builder */
export async function renderPatch(params) {
  const files = await loadFiles();
  const mode = params.get("mode") || "build";
  if (!setViewHtml(`
    <h2 class="section-title">${t("route.patch")}</h2>
    <p class="section-sub">${t("route.patch.sub")}</p>
    <div class="form-row mb-sm">
      <a class="btn ghost small ${mode === "build" ? "active" : ""}" href="${routePath("patch", { mode: "build" })}">${t("tab.build_subset")}</a>
      <a class="btn ghost small ${mode === "apply" ? "active" : ""}" href="${routePath("patch", { mode: "apply" })}">${t("tab.apply_patch")}</a>
    </div>
    <div id="pb-panel"></div>`)) return;
  if (mode === "apply") {
    patchHtml("pb-panel", `
      <p class="section-sub">${t("misc.patch_apply_sub")}</p>
      <div class="form-row">
        <label class="field">${t("label.base")}<select id="pa-b">${fileOptions(files, params.get("base") || "")}</select></label>
        <label class="field">${t("label.patch")}<select id="pa-p">${fileOptions(files, params.get("patch") || "")}</select></label>
        <button class="btn" id="pa-go">${t("btn.apply")}</button>
      </div>
      <div id="pa-out"></div>`);
    document.getElementById("pa-go").onclick = async () => {
      try {
        const r = await api("/api/patch/apply", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ base_id: document.getElementById("pa-b").value, patch_id: document.getElementById("pa-p").value }),
        });
        patchHtml("pa-out", `<div class="banner">
          <a href="${r.download_url}">${t("misc.download_patched", { keys: r.keys })}</a>
          · ${t("misc.changed_added", { changed: r.changed, added: r.added })}</div>`);
      } catch (err) {
        if (!isRouteAbortError(err)) renderPaneError(err, "pa-out");
      }
    };
    return;
  }
  patchHtml("pb-panel", `
    <div class="form-row">
      <label class="field">${t("label.file")}<select id="pb-f">${fileOptions(files, params.get("file") || "")}</select></label>
      <label class="field">${t("label.ranges")}<input id="pb-r" placeholder="${t("placeholder.ranges")}" value="${esc(params.get("ranges") || "")}"></label>
      <button class="btn" id="pb-go">${t("btn.build_subset")}</button>
    </div>
    <div id="pb-out"></div>`);
  document.getElementById("pb-go").onclick = async () => {
    try {
      const r = await api("/api/patch/build", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          file_id: document.getElementById("pb-f").value,
          ranges: document.getElementById("pb-r").value.split(/[,\s]+/).filter(Boolean),
        }),
      });
      patchHtml("pb-out", `<div class="banner"><a href="${r.download_url}">${t("misc.download_patch", { keys: r.keys })}</a></div>`);
    } catch (err) {
      if (!isRouteAbortError(err)) renderPaneError(err, "pb-out");
    }
  };
}

/* ---------------------------------------------------------- campaign map */
export async function renderCampaigns() {
  const d = await api("/api/campaigns/ranges");
  if (!setViewHtml(`
    <h2 class="section-title">${t("route.campaigns")}</h2>
    <p class="section-sub">${t("route.campaigns.sub")}</p>
    <div class="grid cols-2">${Object.entries(d.campaigns).map(([pack, ranges]) => `
      <div class="card"><h3>${esc(pack.replace(/_/g, " "))}</h3>
        <div class="table-wrap"><table class="data"><thead><tr>
          <th>${t("table.name_col")}</th><th>${t("table.range")}</th><th></th>
        </tr></thead>
        <tbody>${ranges.map(r => `<tr>
          <td>${esc(r.name)}</td><td class="num">${r.start}–${r.end}</td>
          <td><a href="${routePath("patch", { mode: "build", ranges: `${r.start}-${r.end}` })}">${t("misc.patch_link")}</a></td>
        </tr>`).join("")}</tbody></table></div>
      </div>`).join("")}
    </div>`)) return;
}

/* ----------------------------------------------------------- game profiles */
export async function renderGames(params) {
  const files = await loadFiles();
  const fid = params.get("file") || "";
  const [profiles, classify] = await Promise.all([
    api("/api/games"),
    fid ? api(`/api/files/${fid}/game-profile`) : Promise.resolve(null),
  ]);
  if (!setViewHtml(`
    <h2 class="section-title">${t("route.games")}</h2>
    <p class="section-sub">${t("route.games.sub")}</p>
    <label class="field">${t("label.classify_upload")}<select id="gp-file"><option value="">—</option>${fileOptions(files, fid)}</select></label>
    <div class="grid cols-2 mt-sm">
      ${profiles.profiles.map(p => `<div class="card"><h3>${esc(p.name)}</h3>
        <div class="stat-row"><span class="k">${t("stat.id")}</span><span class="v">${esc(p.id)}</span></div>
        <div class="stat-row"><span class="k">${t("stat.bom")}</span><span class="v">${p.bom_required ? t("misc.required") : t("misc.optional")}</span></div>
        <div class="stat-row"><span class="k">${t("stat.typical_max_key")}</span><span class="v">${fmt(p.typical_max_key)}</span></div>
        <p class="text-dim-sm">${esc(p.notes)}</p></div>`).join("")}
    </div>
    <div id="gp-out"></div>`)) return;
  document.getElementById("gp-file").onchange = e => {
    if (e.target.value) navigateRoute("games", { file: e.target.value });
  };
  if (classify) {
    patchHtml("gp-out", `
      <h3 class="section-title mt-md">${t("misc.classification")}</h3>
      <div class="banner">${t("misc.best_match", { match: esc(classify.classification.best_match), pct: (classify.classification.confidence * 100).toFixed(0) })}</div>
      <div class="table-wrap"><table class="data"><thead><tr><th>${t("table.profile")}</th><th>${t("table.score")}</th></tr></thead>
      <tbody>${classify.classification.candidates.map(c => `<tr><td>${esc(c.name)}</td><td class="num">${c.score}</td></tr>`).join("")}
      </tbody></table></div>
      ${classify.classification.warnings.length ? `<p class="section-sub">${t("misc.warnings_list", { list: classify.classification.warnings.map(esc).join("; ") })}</p>` : ""}`);
  }
}

/* ------------------------------------------------------------- sga browser */
export async function renderSga() {
  if (!setViewHtml(`
    <h2 class="section-title">${t("route.sga")}</h2>
    <p class="section-sub">${t("route.sga.sub")}</p>
    <div class="form-row">
      <label class="field field-flex-2">${t("label.install_path")}<input id="sga-p" placeholder="${t("placeholder.install")}"></label>
      <button class="btn" id="sga-go">${t("misc.scan_archives")}</button>
      <button class="btn ghost" id="sga-locale">${t("misc.locale_scan")}</button>
      <button class="btn" id="sga-extract-all">${t("misc.extract_all_ucs")}</button>
    </div>
    <div id="sga-out"></div>`)) return;
  document.getElementById("sga-locale").onclick = async () => {
    const install = document.getElementById("sga-p").value;
    if (!install) { toast(t("msg.enter_path")); return; }
    try {
      const d = await api(`/api/sga/locale-scan?install_path=${encodeURIComponent(install)}`);
      patchHtml("sga-out", `
        <div class="banner">${t("misc.archives_locale", { count: d.count })}</div>
        ${d.archives.map(a => `<div class="card mt-sm"><h3>${esc(a.relative)}</h3>
          <p>${esc(a.locale_hint || "locale")} · ${a.locale_ucs.length} file(s)</p>
          <ul>${a.locale_ucs.map(u => `<li>${esc(u.path)} (${fmt(u.size)} B)</li>`).join("")}</ul></div>`).join("")}`);
    } catch (err) {
      if (!isRouteAbortError(err)) renderPaneError(err, "sga-out");
    }
  };
  document.getElementById("sga-extract-all").onclick = async () => {
    const install = document.getElementById("sga-p").value;
    if (!install) { toast(t("msg.enter_path")); return; }
    try {
      const d = await api("/api/sga/extract-locales", { method: "POST", body: JSON.stringify({ install_path: install }) });
      toast(t("msg.extracted_ucs", { count: d.uploaded }));
      patchHtml("sga-out", `
        <div class="banner">${t("misc.uploaded_errors", { uploaded: d.uploaded, errors: d.errors?.length || 0 })}</div>
        <ul>${(d.files || []).map(f => `<li><a href="${routePath("upload", { file: f.file_id })}">${esc(f.internal_path)}</a></li>`).join("")}</ul>`);
    } catch (err) {
      if (!isRouteAbortError(err)) renderPaneError(err, "sga-out");
    }
  };
  document.getElementById("sga-go").onclick = async () => {
    const p = encodeURIComponent(document.getElementById("sga-p").value);
    try {
      const d = await api(`/api/sga/scan?install_path=${p}`);
      patchHtml("sga-out", `
        <div class="table-wrap"><table class="data"><thead><tr>
          <th>${t("table.archive")}</th><th>${t("table.size")}</th><th>${t("table.stub")}</th><th></th>
        </tr></thead>
        <tbody>${d.files.map(f => `<tr>
          <td><a href="#" class="sga-open" data-path="${esc(document.getElementById("sga-p").value)}\\${esc(f.path)}">${esc(f.path)}</a></td>
          <td>${fmt(f.size)}</td><td>${f.likely_stub ? t("misc.yes") : t("misc.no")}</td>
          <td><button class="btn ghost small sga-open" data-path="${esc(document.getElementById("sga-p").value)}\\${esc(f.path)}">${t("misc.browse")}</button></td>
        </tr>`).join("")}
        </tbody></table></div>
        <div id="sga-detail"></div>`);
      document.querySelectorAll(".sga-open").forEach(btn => btn.onclick = async e => {
        e.preventDefault();
        const path = btn.dataset.path.replace(/\\\\/g, "\\");
        try {
          const c = await api(`/api/sga/${encodeURIComponent(path)}/contents`);
          const detail = document.getElementById("sga-detail");
          if (c.error) { renderPaneError(new Error(c.error), "sga-detail"); return; }
          const locale = (c.locale_ucs || []).slice(0, 20);
          detail.innerHTML = `
            <h3 class="section-title mt-md">${esc(c.archive_name)} · ${t("misc.files_count", { count: fmt(c.file_count) })}
              ${c.locale_hint ? `· locale: ${esc(c.locale_hint)}` : ""}</h3>
            ${locale.length ? `<p class="section-sub">${t("misc.locale_ucs_list", { list: locale.map(esc).join(", ") })}</p>` : ""}
            <div class="table-wrap"><table class="data"><thead><tr><th>${t("table.path")}</th><th>${t("table.size")}</th><th></th></tr></thead>
            <tbody>${(c.files || []).filter(f => !f.likely_stub).slice(0, 100).map(f => `<tr>
              <td>${esc(f.path)}</td><td>${fmt(f.size)}</td>
              <td>${f.path.toLowerCase().endsWith(".ucs") ? `<button class="btn ghost small sga-ex" data-arch="${esc(path)}" data-int="${esc(f.path)}">${t("misc.extract")}</button>` : ""}</td>
            </tr>`).join("")}
            </tbody></table></div>`;
          detail.querySelectorAll(".sga-ex").forEach(b => b.onclick = async () => {
            try {
              const r = await api(`/api/sga/${encodeURIComponent(b.dataset.arch)}/extract`, {
                method: "POST", headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ internal_path: b.dataset.int }),
              });
              sessionStorage.setItem("coh-sga-inject", JSON.stringify({
                arch: b.dataset.arch, internal: b.dataset.int, file_id: r.file_id || "",
              }));
              toast(r.file_id ? t("msg.extracted_upload", { id: r.file_id }) : t("msg.extracted_bytes", { bytes: r.bytes }));
              if (r.file_id) navigateRoute("upload", { file: r.file_id });
            } catch (err) {
              if (!isRouteAbortError(err)) toast(err.message);
            }
          });
          await renderSgaInjectPanel(detail, path, c.files || []);
        } catch (err) {
          if (!isRouteAbortError(err)) renderPaneError(err, "sga-detail");
        }
      });
    } catch (err) {
      if (!isRouteAbortError(err)) renderPaneError(err, "sga-out");
    }
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
    <div class="card mt-md" id="sga-inject">
      <h3 class="card-heading-sm">${t("misc.inject_sga")}</h3>
      <p class="section-sub">${t("misc.inject_sga_sub")}</p>
      <div class="form-row">
        <label class="field">${t("label.internal_path")}
          <select id="sga-in-path">${ucsPaths.map(f =>
            `<option value="${esc(f.path)}" ${f.path === prePath ? "selected" : ""}>${esc(f.path)}</option>`
          ).join("")}</select>
        </label>
        <label class="field">${t("label.modified_ucs")}
          <select id="sga-in-file"><option value="">—</option>${fileOptions(files, preFile)}</select>
        </label>
        <button class="btn" id="sga-in-go">${t("misc.inject_sga_btn")}</button>
      </div>
      <div id="sga-in-out"></div>
    </div>`);
  document.getElementById("sga-in-go").onclick = async () => {
    const internal = document.getElementById("sga-in-path").value;
    const ucsId = document.getElementById("sga-in-file").value;
    if (!ucsId) { toast(t("misc.pick_modified_ucs")); return; }
    const out = document.getElementById("sga-in-out");
    if (!patchHtml(out.id, `<div class="loading">${t("misc.packing")}</div>`)) return;
    try {
      const r = await api(`/api/sga/${encodeURIComponent(archPath)}/inject-ucs`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ internal_path: internal, ucs_id: ucsId }),
      });
      if (!patchHtml(out.id, `<div class="banner"><a href="${r.download_url}">${t("misc.download_filename", { name: esc(r.output.split(/[/\\\\]/).pop()) })}</a>
        · ${fmt(r.bytes)} bytes</div>`)) return;
      toast(t("misc.sga_packed"));
    } catch (err) {
      if (!isRouteAbortError(err)) renderPaneError(err, out.id);
    }
  };
}

/* -------------------------------------------------------- verify checklist */
export async function renderVerify(params) {
  const files = await loadFiles();
  const fid = params.get("file") || "";
  if (!setViewHtml(`
    <h2 class="section-title">${t("route.verify")}</h2>
    <p class="section-sub">${t("route.verify.sub")}</p>
    <label class="field">${t("label.file")}<select id="vf-file"><option value="">—</option>${fileOptions(files, fid)}</select></label>
    <button class="btn" id="vf-go">${t("btn.run_checklist")}</button>
    <div id="vf-out"></div>`)) return;
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
  if (!patchHtml(out.id, `<div class="loading">${t("misc.checking")}</div>`)) return;
  try {
    const d = await api(`/api/files/${fid}/verify`);
    const row = r => `<tr class="${r.status}">
      <td class="num">${r.key}</td><td>${esc(r.category)}</td><td>${esc(r.label)}</td>
      <td class="${r.status === "pass" ? "good" : r.status === "fail" ? "bad" : ""}">${esc(r.status)}</td>
      <td>${esc(r.message)}</td><td class="val">${r.value != null ? esc(r.value) : "—"}</td></tr>`;
    if (!patchHtml(out.id, `
      <div class="banner ${d.ok ? "" : "error"}">${t("misc.verify_summary", { passed: d.passed, total: d.total, failed: d.failed, warned: d.warned })}
        ${d.ok ? t("misc.verify_ok") : t("misc.verify_fail")}</div>
      <div class="table-wrap"><table class="data"><thead><tr>
        <th>${t("table.id")}</th><th>${t("table.cat")}</th><th>${t("table.label")}</th><th>${t("table.status")}</th><th>${t("table.message")}</th><th>${t("table.value")}</th>
      </tr></thead>
      <tbody>${d.items.map(row).join("")}</tbody></table></div>
      <div class="card mt-sm"><h3>${t("misc.in_game_steps")}</h3><ul>
        ${(d.install_tips || []).map(tip => `<li>${esc(tip)}</li>`).join("")}
      </ul></div>`)) return;
  } catch (err) {
    if (!isRouteAbortError(err)) renderPaneError(err, out.id, { retry: () => loadVerify(fid) });
  }
}

/* ---------------------------------------------------------- translation I/O */
export async function renderTranslation(params) {
  const files = await loadFiles();
  const fid = params.get("file") || "";
  if (!setViewHtml(`
    <h2 class="section-title">${t("route.translation")}</h2>
    <p class="section-sub">${t("route.translation.sub")}</p>
    <label class="field">${t("label.template_ucs")}<select id="tr-file"><option value="">—</option>${fileOptions(files, fid)}</select></label>
    <div class="form-row mt-sm">
      <a class="btn ghost" id="tr-po-dl" href="#">${t("misc.download_po")}</a>
      <a class="btn ghost" id="tr-tmx-dl" href="#">${t("misc.download_tmx")}</a>
    </div>
    <div class="card mt-md">
      <h3>${t("misc.import_po_tmx")}</h3>
      <label class="field">${t("label.format")}<select id="tr-fmt"><option value="po">${t("po_format")}</option><option value="tmx">${t("tmx_format")}</option></select></label>
      <textarea id="tr-text" rows="12" placeholder="${t("placeholder.po_tmx")}"></textarea>
      <button class="btn mt-sm" id="tr-import">${t("btn.import_ucs")}</button>
      <div id="tr-out"></div>
    </div>`)) return;
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
    if (!id || !text) { toast(t("msg.pick_file_paste")); return; }
    const fmtVal = document.getElementById("tr-fmt").value;
    const body = fmtVal === "tmx" ? { tmx: text } : { po: text };
    const path = fmtVal === "tmx" ? "tmx" : "po";
    try {
      const r = await api(`/api/files/${id}/${path}`, { method: "POST", body: JSON.stringify(body) });
      patchHtml("tr-out", `<div class="banner"><a href="${routePath("upload", { file: r.file_id })}">${t("misc.imported_keys", { keys: r.keys, id: r.file_id })}</a></div>`);
    } catch (err) {
      if (!isRouteAbortError(err)) renderPaneError(err, "tr-out");
    }
  };
  if (fid) { document.getElementById("tr-file").value = fid; syncLinks(); }
}

/* --------------------------------------------------------------- editor */
export async function renderEditor(params) {
  const files = await loadFiles();
  const fid = params.get("file") || "";
  if (!setViewHtml(`
    <h2 class="section-title">${t("route.editor")}</h2>
    <p class="section-sub">${t("route.editor.sub")}</p>
    <label class="field">${t("label.file")}<select id="ed-file"><option value="">—</option>${fileOptions(files, fid)}</select></label>
    <div id="monaco" class="editor-pane"></div>
    <button class="btn" id="ed-save">${t("btn.save_upload")}</button>
    <div id="ed-sga" class="mt-sm"></div>
    <div id="ed-lint" class="banner mt-sm"></div>`)) return;
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
    try {
      const page = await api(`/api/files/${id}/entries?limit=500`);
      const text = page.entries.map(e => `${e.key}\t${e.value}`).join("\n");
      await loadMonaco();
      if (!editor) {
        editor = monaco.editor.create(document.getElementById("monaco"), {
          value: text, language: "plaintext", theme: editorTheme(), automaticLayout: true,
        });
        window.__cohMonacoEditor = editor;
      } else editor.setValue(text);
      const lint = await api(`/api/files/${id}/lint`);
      document.getElementById("ed-lint").textContent =
        t("misc.lint_summary", { entries: lint.entries_with_issues, tokens: lint.token_issue_count });
    } catch (err) {
      if (!isRouteAbortError(err)) renderPaneError(err, "ed-lint");
    }
  }
  document.getElementById("ed-file").onchange = e => loadFile(e.target.value);
  function showSgaInject(fileId) {
    const box = document.getElementById("ed-sga");
    let sga = null;
    try { sga = JSON.parse(sessionStorage.getItem("coh-sga-inject") || "null"); } catch { /* ignore */ }
    if (!sga?.arch) { box.innerHTML = ""; return; }
    box.innerHTML = `
      <div class="card">
        <h3 class="card-heading-sm">${t("misc.inject_into_sga")}</h3>
        <p class="section-sub">${esc(sga.internal)} in ${esc(sga.arch.split(/[/\\\\]/).pop())}</p>
        <button class="btn small" id="ed-inject">${t("misc.inject_saved")}</button>
        <div id="ed-inject-out"></div>
      </div>`;
    document.getElementById("ed-inject").onclick = async () => {
      const out = document.getElementById("ed-inject-out");
      if (!patchHtml(out.id, `<div class="loading">${t("misc.packing")}</div>`)) return;
      try {
        const r = await api(`/api/sga/${encodeURIComponent(sga.arch)}/inject-ucs`, {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ internal_path: sga.internal, ucs_id: fileId }),
        });
        if (!patchHtml(out.id, `<div class="banner"><a href="${r.download_url}">${t("misc.download_patched_sga")}</a></div>`)) return;
        toast(t("misc.sga_packed"));
      } catch (err) {
        if (!isRouteAbortError(err)) renderPaneError(err, out.id);
      }
    };
  }
  document.getElementById("ed-save").onclick = async () => {
    const id = document.getElementById("ed-file").value;
    if (!id || !editor) { toast(t("msg.load_file_first")); return; }
    const entries = editor.getValue().split(/\r?\n/).filter(Boolean).map(line => {
      const tab = line.indexOf("\t");
      return tab < 0 ? null : { key: parseInt(line.slice(0, tab), 10), value: line.slice(tab + 1) };
    }).filter(Boolean);
    try {
      const r = await api(`/api/files/${id}/save`, { method: "POST", body: JSON.stringify({ entries }) });
      toast(t("misc.saved_as", { id: r.file_id }));
      try {
        const cur = JSON.parse(sessionStorage.getItem("coh-sga-inject") || "null");
        if (cur) sessionStorage.setItem("coh-sga-inject", JSON.stringify({ ...cur, file_id: r.file_id }));
      } catch { /* ignore */ }
      showSgaInject(r.file_id);
    } catch (err) {
      if (!isRouteAbortError(err)) toast(err.message);
    }
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
      return `<p class="bad text-dim-sm">${t("misc.session_expired")}</p>`;
    }
    if (auth.session_expires_in_s != null && auth.session_expires_in_s < 3600 && auth.authenticated) {
      const mins = Math.ceil(auth.session_expires_in_s / 60);
      return `<p class="muted text-dim-sm">${t("misc.session_expires_soon", { mins })}</p>`;
    }
    if (auth.session_expires_in_s != null && auth.authenticated) {
      const hrs = Math.floor(auth.session_expires_in_s / 3600);
      const mins = Math.ceil((auth.session_expires_in_s % 3600) / 60);
      return `<p class="muted text-dim-sm">${t("misc.session_valid", { time: `${hrs ? `${hrs}h ` : ""}${mins}m` })}</p>`;
    }
    return "";
  };
  if (!setViewHtml(`
    <h2 class="section-title">${t("route.settings")}</h2>
    <p class="section-sub">${t("route.settings.sub")}</p>
    <div class="card max-w-card mb-md">
      <h3 class="card-heading-sm">${t("settings.auth")}</h3>
      ${isHybridUi() ? `<p class="muted text-dim-sm mb-sm">${t("misc.hybrid_ui")}</p>` : ""}
      ${auth.authenticated
        ? `<p>${t("settings.signed_in")} <strong>${esc(auth.user || "")}</strong> (${esc(auth.method || "")})</p>
           ${sessionHint()}
           <button type="button" class="btn ghost small" id="auth-logout">${t("btn.sign_out")}</button>`
        : auth.auth_enabled
          ? `<form id="auth-form" class="settings-form" autocomplete="on">
             <p class="muted text-dim-sm">${t("settings.auth_required")}</p>
             <label class="field">${t("label.username")}<input id="auth-user" name="username" autocomplete="username"></label>
             <label class="field mt-sm">${t("label.password")}<input type="password" id="auth-pass" name="password" autocomplete="current-password"></label>
             <button type="submit" class="btn small mt-sm" id="auth-login">${t("btn.sign_in")}</button>
             ${auth.oauth_configured ? `<a class="btn ghost small ml-sm" href="${apiUrl("/api/auth/oauth/login")}">${t("btn.oauth")}</a>` : ""}
             </form>`
          : `<p class="muted text-dim-sm">${t("settings.auth_none")}</p>`}
    </div>
    <form id="prefs-form" class="card max-w-card settings-form" autocomplete="on">
      <label class="toggle"><input type="checkbox" id="theme-t" ${theme === "light" ? "checked" : ""}> ${t("settings.theme_light")}</label>
      <label class="field mt-md">${t("settings.language")}
        <select id="ui-lang" name="ui-lang"><option value="en">English</option><option value="fr">Français</option><option value="ar">العربية</option></select>
      </label>
      <label class="field mt-md">${t("settings.api_key")}
        <input type="password" id="api-key" name="api-key" class="input-block" placeholder="${t("placeholder.api_key")}" autocomplete="off">
      </label>
      <p class="muted text-dim-sm mt-sm">${t("misc.api_key_storage")}</p>
      <p class="mt-md"><a href="${apiUrl("/docs")}" target="_blank">${t("misc.openapi_docs")}</a> ·
        <a href="${apiUrl("/api/export/openapi-client")}" target="_blank">${t("misc.client_snippets")}</a></p>
      <button type="button" class="btn ghost small mt-sm" id="dup-probe">${t("btn.dup_probe")}</button>
      <div id="dup-out"></div>
    </form>
    <div class="card max-w-card mt-md">
      <h3 class="card-heading-sm">${t("misc.webhook_log")}</h3>
      <button type="button" class="btn ghost small mb-sm" id="wh-retry">${t("misc.retry_dead_letters")}</button>
      <div id="wh-log"><div class="loading">${t("msg.loading")}</div></div>
    </div>`)) return;
  const renderWhLog = async () => {
    try {
      const wh = await api("/api/webhooks/deliveries?limit=25");
      const rows = wh.deliveries || [];
      patchHtml("wh-log", rows.length ? `
        <div class="table-wrap"><table class="data"><thead><tr><th>${t("table.event")}</th><th>${t("table.url")}</th><th>${t("table.ok")}</th><th>${t("table.try")}</th><th>${t("table.detail")}</th></tr></thead>
        <tbody>${rows.map(d => `<tr>
          <td>${esc(d.event)}</td><td class="text-dim-sm text-ellipsis">${esc(d.url)}</td>
          <td class="${d.success ? "good" : "bad"}">${d.success ? t("misc.yes") : t("misc.no")}</td>
          <td>${d.attempt || 1}${d.dead_letter ? " DL" : ""}</td>
          <td class="text-dim-sm">${d.success ? esc(String(d.status_code || "")) : esc(d.error || "")}</td>
        </tr>`).join("")}</tbody></table></div>`
        : `<p class="muted">${t("misc.no_webhooks")}</p>`);
    } catch (e) {
      if (isRouteAbortError(e)) return;
      renderPaneError(e, "wh-log", { retry: renderWhLog });
    }
  };
  await renderWhLog();
  q("wh-retry")?.addEventListener("click", async () => {
    try {
      const r = await api("/api/webhooks/retry-dead-letters", { method: "POST" });
      toast(t("msg.retried_webhooks", { retried: r.retried, ok: r.succeeded, failed: r.failed }));
      await renderWhLog();
    } catch (e) { if (!isRouteAbortError(e)) toast(e.message); }
  });
  q("auth-form")?.addEventListener("submit", async e => {
    e.preventDefault();
    try {
      await api("/api/auth/login", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username: q("auth-user")?.value,
          password: q("auth-pass")?.value,
        }),
      });
      toast(t("msg.signed_in"));
      renderSettings();
    } catch (err) { if (!isRouteAbortError(err)) toast(err.message); }
  });
  q("auth-logout")?.addEventListener("click", async () => {
    await api("/api/auth/logout", { method: "POST" });
    toast(t("msg.signed_out"));
    renderSettings();
  });
  q("dup-probe")?.addEventListener("click", async () => {
    const r = await api("/api/tools/duplicate-probe", { method: "POST" });
    patchHtml("dup-out", `
      <div class="banner mt-sm"><a href="${r.download_url}">${t("misc.download_probe")}</a></div>
      <ul class="text-dim-sm mt-sm">${(r.instructions || []).map(i => `<li>${esc(i)}</li>`).join("")}</ul>`);
  });
  q("theme-t")?.addEventListener("change", e => {
    const light = e.target.checked;
    document.documentElement.dataset.theme = light ? "light" : "dark";
    localStorage.setItem("coh-theme", light ? "light" : "dark");
    applyColorScheme(light ? "light" : "dark");
    window.dispatchEvent(new CustomEvent("coh-theme-changed"));
    if (window.__cohMonacoEditor && window.monaco) {
      monaco.editor.setTheme(editorTheme());
    }
  });
  const langSelect = q("ui-lang");
  if (langSelect) {
    langSelect.value = lang;
    langSelect.addEventListener("change", async e => {
      await setLocale(e.target.value);
      toast(t("msg.language_saved"));
    });
  }
  const keyInput = q("api-key");
  if (keyInput) {
    keyInput.value = localStorage.getItem("coh-api-key") || "";
    keyInput.addEventListener("change", e => {
      const v = e.target.value.trim();
      if (v) localStorage.setItem("coh-api-key", v);
      else localStorage.removeItem("coh-api-key");
      toast(t("msg.api_key_saved"));
    });
  }
}

/* --------------------------------------------------------------- about */
export async function renderAbout() {
  const faqHtml = [];
  for (let i = 0; i <= 5; i++) {
    faqHtml.push(`
      <details class="faq-item">
        <summary>${esc(t(`faq.${i}.q`))}</summary>
        <p>${esc(t(`faq.${i}.a`))}</p>
      </details>`);
  }
  if (!setViewHtml(`
    <article class="about-page">
      <h2 class="section-title">${t("route.about")}</h2>
      <p class="section-sub">${t("about.sub")}</p>

      <div class="card about-lead">
        <p>${t("about.lead1")}</p>
        <p>${t("about.lead2")}</p>
      </div>

      <h3 class="about-heading">${t("about.what_heading")}</h3>
      <ul class="about-list">
        <li>${t("about.feature_upload")}</li>
        <li>${t("about.feature_compare")}</li>
        <li>${t("about.feature_merge")}</li>
        <li>${t("about.feature_validator")}</li>
        <li>${t("about.feature_translation")}</li>
        <li>${t("about.feature_languages")}</li>
      </ul>

      <h3 class="about-heading">${t("about.who_heading")}</h3>
      <p>${t("about.who_body")}</p>

      <h3 class="about-heading">${t("about.faq_heading")}</h3>
      <div class="faq-list">${faqHtml.join("")}</div>

      <p class="about-footer">MIT licensed · <a href="https://github.com/benmed00/coh-ucs-tools" target="_blank" rel="noopener">${t("about.source_github")}</a>
        · <a href="${routePath("upload")}">${t("about.open_console")}</a></p>
    </article>`)) return;
}

function editorTheme() {
  return document.documentElement.dataset.theme === "light" ? "vs" : "vs-dark";
}

/* apply saved theme on load */
function applyColorScheme(theme) {
  document.documentElement.style.colorScheme = theme === "light" ? "light" : "dark";
}

export function initTheme() {
  const theme = localStorage.getItem("coh-theme");
  if (theme === "light") document.documentElement.dataset.theme = "light";
  applyColorScheme(theme === "light" ? "light" : "dark");
}
