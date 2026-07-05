/* Shell UI translations (en / fr / ar). */

let strings = {};
let locale = "en";

function i18nUrl(code) {
  const base = (window.BASE_PATH || "").replace(/\/$/, "");
  if (base) return `${base}/i18n/${code}.json`;
  return `/static/i18n/${code}.json`;
}

async function loadLocale(code) {
  const res = await fetch(i18nUrl(code));
  if (!res.ok) throw new Error(`i18n ${code}: ${res.status}`);
  return res.json();
}

export function t(key, fallback) {
  if (Object.prototype.hasOwnProperty.call(strings, key)) return strings[key];
  return fallback !== undefined ? fallback : key;
}

export function getLocale() {
  return locale;
}

export function applyShellI18n() {
  document.querySelectorAll("[data-i18n]").forEach(el => {
    const key = el.dataset.i18n;
    const val = t(key);
    if (val !== key) el.textContent = val;
  });
  document.querySelectorAll("[data-i18n-html]").forEach(el => {
    const key = el.dataset.i18nHtml;
    el.innerHTML = t(key).replace(/\n/g, "<br>");
  });
  document.documentElement.lang = locale;
  document.documentElement.dir = locale === "ar" ? "rtl" : "ltr";
}

export async function setLocale(code, { notify = true } = {}) {
  locale = code || "en";
  localStorage.setItem("coh-ui-lang", locale);
  try {
    strings = await loadLocale(locale);
  } catch {
    strings = locale !== "en" ? await loadLocale("en").catch(() => ({})) : {};
  }
  if (locale !== "en") {
    try {
      const en = await loadLocale("en");
      strings = { ...en, ...strings };
    } catch { /* en fallback optional */ }
  }
  applyShellI18n();
  if (notify) window.dispatchEvent(new Event("coh-i18n-changed"));
}

export async function initI18n() {
  const saved = localStorage.getItem("coh-ui-lang") || "en";
  await setLocale(saved, { notify: false });
}
