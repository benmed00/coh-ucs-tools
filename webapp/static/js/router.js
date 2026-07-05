/** Path-based SPA router (History API) with GitHub Pages base-path support. */

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

/** Set ``href`` on ``a[data-route]`` after DOM ready. */
export function initNavLinks() {
  document.querySelectorAll("a[data-route]").forEach((a) => {
    a.href = routePath(a.dataset.route);
  });
}

/** Canonical URL for SEO (uses ``window.SITE_URL`` when set). */
export function canonicalUrl(routeName) {
  const origin = (window.SITE_URL || window.location.origin + basePath()).replace(/\/$/, "");
  if (!routeName || routeName === "dashboard") {
    return `${origin}/`;
  }
  return `${origin}/${routeName}`;
}
