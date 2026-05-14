import { marked } from "marked";

// Match common typed-markdown signals. The line-anchored alternatives are
// block-level (heading, list, quote, fence, rule, bold/italic at line start);
// the trailing [text](url) is hoisted out so inline links match mid-sentence.
const MARKDOWN_HINTS = /(^|\n)(#{1,6}\s|>\s|[*-]\s|\d+\.\s|```|---|\*\*[^*]+\*\*|__[^_]+__)|\[[^\]]+\]\([^)]+\)/;

export function looksLikeMarkdown(text) {
  if (!text) return false;
  return MARKDOWN_HINTS.test(text);
}

function insertHtml(view, html) {
  view.pasteHTML(html);
}

export function smartPasteHandler(view, event) {
  // In a code block: always paste as plain text — Tiptap default.
  const parentType = view.state?.selection?.$from?.parent?.type?.name;
  if (parentType === "codeBlock") return false;

  const data = event.clipboardData;
  if (!data) return false;

  const html  = data.getData("text/html");
  const text  = data.getData("text/plain");
  const files = data.files || [];

  // Office / Docs / Notion HTML — normalise and insert.
  if (html && looksLikeOfficeHtml(html)) {
    insertHtml(view, normaliseOfficeHtml(html));
    event.preventDefault();
    return true;
  }

  // Plain-text markdown — render to HTML and insert.
  if (!html && text && looksLikeMarkdown(text)) {
    insertHtml(view, marked.parse(text, { breaks: true, gfm: true }).trim());
    event.preventDefault();
    return true;
  }

  // Image clipboard — drop in v1 (no inline upload).
  if (!html && !text && files.length > 0 && files[0].type?.startsWith("image/")) {
    event.preventDefault();
    return true;
  }

  return false;
}

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
