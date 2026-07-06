/** CSS + vanilla JS motion helpers for the SPA. */

const STAGGER_SEL = ".card, .tool-card, .grid > *, .banner, .empty";
const STAGGER_MAX = 12;

export function prefersReducedMotion() {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/** Wrap DOM update in View Transitions API when available. */
export function viewTransition(updateFn) {
  if (prefersReducedMotion() || typeof document.startViewTransition !== "function") {
    updateFn();
    return Promise.resolve();
  }
  try {
    const vt = document.startViewTransition(() => updateFn());
    return vt.finished.catch((err) => {
      const msg = String(err?.message || err);
      if (err?.name === "AbortError" || msg.includes("skipped")) return;
    });
  } catch {
    updateFn();
    return Promise.resolve();
  }
}

/** Apply enter animation class; returns cleanup promise. */
export function enter(el, className = "motion-panel-enter") {
  if (!el || prefersReducedMotion()) return Promise.resolve();
  el.classList.remove(className);
  void el.offsetWidth;
  el.classList.add(className);
  return new Promise(resolve => {
    const done = () => {
      el.classList.remove(className);
      el.removeEventListener("animationend", done);
      resolve();
    };
    el.addEventListener("animationend", done, { once: true });
    setTimeout(done, 600);
  });
}

/** Set --stagger-i on children for staggered CSS delays. */
export function stagger(parent, childSel = STAGGER_SEL, max = STAGGER_MAX) {
  if (!parent || prefersReducedMotion()) return;
  const items = parent.querySelectorAll(childSel);
  items.forEach((child, i) => {
    child.style.setProperty("--stagger-i", String(Math.min(i, max)));
  });
}

function isLoadingOnly(html) {
  const t = String(html).trim();
  return /^<div class="loading[^"]*">/.test(t) && !t.includes("</div><");
}

/** Build a shimmer skeleton loading block with optional message. */
export function loadingSkeleton(msg = "") {
  const text = msg ? `<span class="loading-radar">${msg}</span>` : "";
  return `<div class="loading-skeleton" aria-busy="true"><i></i><i></i><i></i>${text}</div>`;
}

/** Animate #view after full HTML swap. */
export function animateViewEnter(viewEl) {
  if (!viewEl || prefersReducedMotion()) return;
  viewEl.classList.remove("motion-enter");
  void viewEl.offsetWidth;
  viewEl.classList.add("motion-enter");
  stagger(viewEl);
  const cleanup = () => viewEl.classList.remove("motion-enter");
  viewEl.addEventListener("animationend", cleanup, { once: true });
  setTimeout(cleanup, 800);
}

/** Animate a patched panel after innerHTML swap. */
export function animatePanelEnter(el, html) {
  if (!el || prefersReducedMotion() || isLoadingOnly(html)) return;
  stagger(el);
  if (el.querySelector(".banner, .empty")) {
    el.querySelectorAll(".banner, .empty").forEach(b => {
      b.classList.add("motion-banner-in");
    });
  }
  enter(el, "motion-panel-enter");
}

let toastTimer = 0;
let toastExitTimer = 0;

/** Animated toast show/hide. */
export function showToast(el, msg, ms = 3200) {
  if (!el) return;
  clearTimeout(toastTimer);
  clearTimeout(toastExitTimer);

  const hide = () => {
    if (prefersReducedMotion()) {
      el.hidden = true;
      return;
    }
    el.classList.remove("motion-toast-in");
    el.classList.add("motion-toast-out");
    toastExitTimer = setTimeout(() => {
      el.hidden = true;
      el.classList.remove("motion-toast-out");
    }, 160);
  };

  el.textContent = msg;
  el.hidden = false;
  el.classList.remove("motion-toast-out");
  if (!prefersReducedMotion()) {
    el.classList.remove("motion-toast-in");
    void el.offsetWidth;
    el.classList.add("motion-toast-in");
  }
  toastTimer = setTimeout(hide, ms);
}
