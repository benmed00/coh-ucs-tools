/** Path-based SPA router (History API) with GitHub Pages base-path support. */

/** Known client route names (must match ``routes`` in app.js). */
export const ROUTE_NAMES = new Set([
  "dashboard", "about", "upload", "compare", "merge", "tools", "diff", "ranges",
  "validator", "languages", "merge-wizard", "install", "mt", "glossary", "timeline",
  "depots", "search", "bookmarks", "patch", "sga", "settings", "editor", "verify",
  "translation", "campaigns", "games",
]);

const NON_SPA_PATHS = new Set(["docs", "redoc", "openapi.json"]);

export function basePath() {
  return (window.BASE_PATH || "").replace(/\/$/, "");
}

/** Build an app URL path for route *name* and optional query string / params. */
export function routePath(name, query) {
  const base = basePath();
  let path;
  if (!name || name === "dashboard") {
    path = base ? `${base}/` : "/";
  } else {
    path = base ? `${base}/${name}` : `/${name}`;
  }
  let qs = "";
  if (query instanceof URLSearchParams) {
    qs = query.toString();
  } else if (typeof query === "string" && query) {
    qs = query.startsWith("?") ? query.slice(1) : query;
  } else if (query && typeof query === "object") {
    qs = new URLSearchParams(query).toString();
  }
  return qs ? `${path}?${qs}` : path;
}

/** Navigate without reload; triggers ``coh-route`` event. */
export function navigateRoute(name, query) {
  history.pushState(null, "", routePath(name, query));
  window.dispatchEvent(new Event("coh-route"));
}

/** Parse current location into { name, params }. Migrates legacy ``#/`` hashes. */
export function parseRoute() {
  if (location.hash.startsWith("#/")) {
    const legacy = location.hash.slice(2);
    const slash = legacy.includes("/") ? legacy : legacy.split("?")[0];
    const q = legacy.includes("?") ? legacy.split("?").slice(1).join("?") : "";
    const name = slash.split("/")[0] || "dashboard";
    history.replaceState(null, "", routePath(name, q));
  }

  let pathname = location.pathname;
  const base = basePath();
  if (base && (pathname === base || pathname.startsWith(`${base}/`))) {
    pathname = pathname.slice(base.length) || "/";
  }

  const segment = pathname === "/" ? "dashboard" : pathname.replace(/^\//, "").split("/")[0];
  return { name: segment || "dashboard", params: new URLSearchParams(location.search) };
}

/** Parse an anchor href into { name, params } or null if not an in-app route. */
export function parseRouteFromHref(href) {
  let url;
  try {
    url = new URL(href, location.origin);
  } catch {
    return null;
  }
  if (url.origin !== location.origin) return null;

  let pathname = url.pathname;
  const base = basePath();
  if (base && (pathname === base || pathname.startsWith(`${base}/`))) {
    pathname = pathname.slice(base.length) || "/";
  }

  if (pathname.startsWith("/api/") || pathname.startsWith("/static/")) return null;

  const segment = pathname === "/" ? "dashboard" : pathname.replace(/^\//, "").split("/")[0];
  if (!segment || !ROUTE_NAMES.has(segment) || NON_SPA_PATHS.has(segment)) return null;

  return {
    name: segment,
    params: url.search ? new URLSearchParams(url.search) : new URLSearchParams(),
  };
}

function shouldInterceptClick(e, a) {
  if (!a || e.defaultPrevented || e.button !== 0) return false;
  if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return false;
  if (a.hasAttribute("download")) return false;
  if (a.target && a.target !== "_self") return false;
  return true;
}

/** Set ``href`` on ``a[data-route]`` after DOM ready. */
const NAV_ICONS = {
  dashboard: "dashboard.svg",
  upload: "upload.svg",
  compare: "compare.svg",
  diff: "compare.svg",
  languages: "languages.svg",
  search: "search.svg",
  "merge-wizard": "merge.svg",
  validator: "validate.svg",
  verify: "validate.svg",
};

export function applyNavIcons() {
  const prefix = `${(window.BASE_PATH || "").replace(/\/$/, "")}/static/icons/nav/`;
  document.querySelectorAll("#nav a[data-route]").forEach((a) => {
    if (a.querySelector(".nav-ico")) return;
    const file = NAV_ICONS[a.dataset.route];
    if (!file) return;
    const img = document.createElement("img");
    img.src = `${prefix}${file}`;
    img.className = "nav-ico";
    img.width = 13;
    img.height = 13;
    img.alt = "";
    img.decoding = "async";
    a.prepend(img);
  });
}

export function initNavLinks() {
  document.querySelectorAll("a[data-route]").forEach((a) => {
    a.href = routePath(a.dataset.route);
  });
  applyNavIcons();
}

/** Intercept in-app nav clicks — client-side routing without full reload. */
export function initSpaNav() {
  document.addEventListener("click", (e) => {
    const a = e.target.closest("a[href]");
    if (!shouldInterceptClick(e, a)) return;

    let name;
    let params;
    if (a.dataset.route) {
      name = a.dataset.route;
      const url = new URL(a.href, location.origin);
      params = url.search ? new URLSearchParams(url.search) : undefined;
    } else {
      const parsed = parseRouteFromHref(a.href);
      if (!parsed) return;
      name = parsed.name;
      params = parsed.params.toString() ? parsed.params : undefined;
    }

    e.preventDefault();
    navigateRoute(name, params);
  });
}

/** Scroll main content into view after in-app navigation (avoids hero-only viewport). */
export function scrollToMain() {
  document.getElementById("view")?.scrollIntoView({ behavior: "smooth", block: "start" });
}

/** Canonical URL for SEO (uses ``window.SITE_URL`` when set). */
export function canonicalUrl(routeName) {
  const origin = (window.SITE_URL || window.location.origin + basePath()).replace(/\/$/, "");
  if (!routeName || routeName === "dashboard") {
    return `${origin}/`;
  }
  return `${origin}/${routeName}`;
}
