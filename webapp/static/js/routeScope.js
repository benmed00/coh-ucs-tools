/**
 * Route lifecycle for the SPA: abort in-flight work and block stale DOM writes
 * when the user navigates away before async handlers finish.
 */

export class RouteAbortError extends Error {
  constructor() {
    super("Route superseded by navigation");
    this.name = "RouteAbortError";
  }
}

/** @type {{ abort(): void, signal: AbortSignal, get alive(): boolean } | null} */
let active = null;

/** Start a new route; aborts the previous route's signal and DOM guards. */
export function beginRoute() {
  active?.abort();
  const controller = new AbortController();
  const scope = {
    _controller: controller,
    _aborted: false,
    get signal() {
      return controller.signal;
    },
    abort() {
      if (this._aborted) return;
      this._aborted = true;
      controller.abort();
    },
    get alive() {
      return !this._aborted && active === this;
    },
  };
  active = scope;
  return scope;
}

export function routeAlive() {
  return active?.alive ?? false;
}

export function routeSignal() {
  return active?.signal;
}

/** Throw if this route was superseded (after await boundaries). */
export function guardRoute() {
  if (!routeAlive()) throw new RouteAbortError();
}

export function isRouteAbortError(err) {
  return err instanceof RouteAbortError
    || err?.name === "RouteAbortError"
    || err?.name === "AbortError";
}

/** Replace #view markup when the current route is still active. */
export function setViewHtml(html) {
  if (!routeAlive()) return false;
  const el = document.getElementById("view");
  if (!el) return false;
  el.innerHTML = html;
  return true;
}

/** Replace innerHTML on an element by id when the route is still active. */
export function patchHtml(id, html) {
  if (!routeAlive()) return false;
  const el = document.getElementById(id);
  if (!el) return false;
  el.innerHTML = html;
  return true;
}

/** getElementById that returns null when the route is no longer active. */
export function q(id) {
  if (!routeAlive()) return null;
  return document.getElementById(id);
}

/** Run fn only if route is still active; no-op otherwise. */
export function ifAlive(fn) {
  if (!routeAlive()) return;
  fn();
}
