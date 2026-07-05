/* Per-route document title, meta description, canonical, and structured data. */

import { canonicalUrl } from "./router.js";

const DEFAULT_TITLE = "CoH UCS Tools — localization command console";
const DEFAULT_DESCRIPTION =
  "Analyze, validate, compare, and merge Company of Heroes .ucs localization files. UTF-16-LE parser, merge wizard, PO/TMX export, and REST API.";

const ROUTE_SEO = window.ROUTE_SEO || {};
const ABOUT_FAQ = window.ABOUT_FAQ || [];
const SITE_LABEL = window.SITE_NAME || "CoH UCS Tools";

const FAQ_SCRIPT_ID = "seo-faq-ld";
const BREADCRUMB_SCRIPT_ID = "seo-breadcrumb-ld";

function upsertMeta(attr, key, content) {
  let el = document.querySelector(`meta[${attr}="${key}"]`);
  if (!el) {
    el = document.createElement("meta");
    el.setAttribute(attr, key);
    document.head.appendChild(el);
  }
  el.setAttribute("content", content);
}

function upsertLink(rel, href) {
  let el = document.querySelector(`link[rel="${rel}"]`);
  if (!el) {
    el = document.createElement("link");
    el.setAttribute("rel", rel);
    document.head.appendChild(el);
  }
  el.setAttribute("href", href);
}

function removeScript(id) {
  document.getElementById(id)?.remove();
}

function injectJsonLd(id, data) {
  removeScript(id);
  const script = document.createElement("script");
  script.id = id;
  script.type = "application/ld+json";
  script.textContent = JSON.stringify(data);
  document.head.appendChild(script);
}

function removeFaqSchema() {
  removeScript(FAQ_SCRIPT_ID);
}

function injectFaqSchema() {
  removeFaqSchema();
  if (!ABOUT_FAQ.length) return;
  injectJsonLd(FAQ_SCRIPT_ID, {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: ABOUT_FAQ.map(({ question, answer }) => ({
      "@type": "Question",
      name: question,
      acceptedAnswer: { "@type": "Answer", text: answer },
    })),
    url: canonicalUrl("about"),
  });
}

function removeBreadcrumbSchema() {
  removeScript(BREADCRUMB_SCRIPT_ID);
}

function injectBreadcrumbSchema(routeName) {
  removeBreadcrumbSchema();
  if (!routeName || routeName === "dashboard") return;
  const meta = ROUTE_SEO[routeName];
  if (!meta?.title) return;
  injectJsonLd(BREADCRUMB_SCRIPT_ID, {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: [
      {
        "@type": "ListItem",
        position: 1,
        name: "Dashboard",
        item: canonicalUrl("dashboard"),
      },
      {
        "@type": "ListItem",
        position: 2,
        name: meta.title,
        item: canonicalUrl(routeName),
      },
    ],
  });
}

export function applyRouteSeo(routeName) {
  const meta = ROUTE_SEO[routeName] || {};
  const pageTitle = meta.title ? `${meta.title} — ${SITE_LABEL}` : DEFAULT_TITLE;
  const description = meta.description || DEFAULT_DESCRIPTION;
  const canonical = canonicalUrl(routeName);

  document.title = pageTitle;

  upsertMeta("name", "description", description);
  upsertMeta("property", "og:title", pageTitle);
  upsertMeta("property", "og:description", description);
  upsertMeta("property", "og:url", canonical);
  upsertMeta("name", "twitter:title", pageTitle);
  upsertMeta("name", "twitter:description", description);

  upsertLink("canonical", canonical);

  if (routeName === "about") {
    injectFaqSchema();
  } else {
    removeFaqSchema();
  }

  injectBreadcrumbSchema(routeName);
}

export { DEFAULT_TITLE, DEFAULT_DESCRIPTION, ROUTE_SEO };
