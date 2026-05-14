const OFFICE_SIGNATURES = [
  "urn:schemas-microsoft-com:office",
  "mso-",
  "MsoNormal",
  "docs-internal-guid-",
  "data-pm-slice",
];

export function looksLikeOfficeHtml(html) {
  if (!html) return false;
  return OFFICE_SIGNATURES.some((sig) => html.includes(sig));
}

const ALLOWED_TAGS = new Set([
  "h1", "h2", "h3", "h4", "h5", "h6",
  "p", "br", "hr",
  "strong", "em", "u", "s", "code", "pre",
  "blockquote",
  "ul", "ol", "li",
  "a", "img",
]);

function unwrap(el) {
  while (el.firstChild) el.parentNode.insertBefore(el.firstChild, el);
  el.remove();
}

export function normaliseOfficeHtml(html) {
  const doc = new DOMParser().parseFromString(html, "text/html");

  // Remove never-allowed elements outright.
  doc.querySelectorAll("style, meta, link, script").forEach((n) => n.remove());

  // Office-namespaced tags (<o:p>, <w:foo>) — DOMParser keeps them as unknown
  // elements with localName containing the namespace; match by tagName prefix.
  [...doc.querySelectorAll("*")].forEach((el) => {
    const name = el.tagName.toLowerCase();
    if (name.startsWith("o:") || name.startsWith("w:")) el.remove();
  });

  // Strip presentational attributes from every remaining element.
  [...doc.querySelectorAll("*")].forEach((el) => {
    el.removeAttribute("style");
    el.removeAttribute("class");
    el.removeAttribute("dir");
    el.removeAttribute("lang");
    [...el.attributes].forEach((attr) => {
      if (attr.name.startsWith("mso-") || attr.name.startsWith("data-pm-")) {
        el.removeAttribute(attr.name);
      }
    });
  });

  // Promote <b>/<i> to semantic <strong>/<em>.
  doc.querySelectorAll("b").forEach((b) => {
    const strong = doc.createElement("strong");
    while (b.firstChild) strong.appendChild(b.firstChild);
    b.replaceWith(strong);
  });
  doc.querySelectorAll("i").forEach((i) => {
    const em = doc.createElement("em");
    while (i.firstChild) em.appendChild(i.firstChild);
    i.replaceWith(em);
  });

  // Collapse <font> and <span> into their children (we already stripped style/class).
  doc.querySelectorAll("font, span").forEach(unwrap);

  // Unwrap any element not on the allow-list (keeps its text, drops its identity).
  // Only operate on elements inside body to avoid structural DOM nodes.
  [...doc.body.querySelectorAll("*")].forEach((el) => {
    if (!ALLOWED_TAGS.has(el.tagName.toLowerCase())) unwrap(el);
  });

  return doc.body.innerHTML.trim();
}
