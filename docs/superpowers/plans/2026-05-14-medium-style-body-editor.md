# Medium-style body editor — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the CKEditor 5 body widget at `{{ form.body }}` with a Tiptap-based editor that gives Medium-style UX (bubble toolbar, slash menu, smart paste) and fixes the rich-text-paste + markdown-paste bugs.

**Architecture:** Custom Django form widget (`TiptapWidget`) renders a hidden `<textarea>` plus a Tiptap mount point. A first-party JS bundle (`static/blog/tiptap.js`) initialises Tiptap, mirrors HTML back to the textarea on every change, and handles paste through a smart pipeline. Storage stays HTML. Server-side sanitiser (`blog/templatetags/sanitize.py`) is unchanged and remains the security boundary.

**Tech Stack:** Django 5.2, Tiptap 2 (`@tiptap/core` + StarterKit + extensions), esbuild bundler, vitest + jsdom for JS tests, Django `TestCase` for Python tests, `marked` for markdown→HTML.

**Spec:** `docs/superpowers/specs/2026-05-14-medium-style-body-editor-design.md`

---

## File map (locked from spec)

```
NEW    blog/widgets.py
NEW    blog/templates/blog/widgets/tiptap.html
NEW    blog/tests_tiptap.py
NEW    blog/migrations/0010_alter_blogpost_body.py
NEW    static/blog/tiptap.css
BUILT  static/blog/tiptap.js                 (esbuild output, committed)
NEW    src/tiptap/index.js
NEW    src/tiptap/slash-menu.js
NEW    src/tiptap/paste.js
NEW    src/tiptap/__tests__/paste.test.js
NEW    src/tiptap/__tests__/normalise.test.js
NEW    src/tiptap/__tests__/fixtures/google-docs-paste.html
NEW    src/tiptap/__tests__/fixtures/word-paste.html
NEW    src/tiptap/__tests__/fixtures/notion-paste.html
EDIT   blog/forms.py
EDIT   blog/models.py
EDIT   mysite/settings.py
EDIT   mysite/urls.py
EDIT   requirements.txt
EDIT   package.json
```

---

## Task 1: Bootstrap JS toolchain

**Files:**
- Modify: `package.json`

- [ ] **Step 1: Install runtime dependencies**

Run:
```bash
cd /Users/admin/PycharmProjects/nyasablog
npm install --save \
  @tiptap/core@^2.8.0 \
  @tiptap/starter-kit@^2.8.0 \
  @tiptap/extension-bubble-menu@^2.8.0 \
  @tiptap/extension-link@^2.8.0 \
  @tiptap/extension-underline@^2.8.0 \
  marked@^14.0.0
```

Expected: `package-lock.json` updated; `node_modules/@tiptap/*` populated.

- [ ] **Step 2: Install dev dependencies (bundler + JS test stack)**

Run:
```bash
npm install --save-dev \
  esbuild@^0.24.0 \
  vitest@^2.1.0 \
  jsdom@^25.0.0 \
  @vitest/coverage-v8@^2.1.0
```

Expected: `devDependencies` block in `package.json` includes the four packages.

- [ ] **Step 3: Add build and test scripts to `package.json`**

Update the `scripts` block to:

```json
"scripts": {
  "build:css":    "npx tailwindcss -i static/src/input.css -o static/css/tailwind.min.css --minify",
  "watch:css":    "npx tailwindcss -i static/src/input.css -o static/css/tailwind.min.css --watch",
  "build:editor": "esbuild src/tiptap/index.js --bundle --minify --target=es2020 --outfile=static/blog/tiptap.js",
  "build":        "npm run build:css && npm run build:editor",
  "test:js":      "vitest run --environment jsdom"
}
```

- [ ] **Step 4: Verify build pipeline boots**

Run:
```bash
mkdir -p src/tiptap static/blog
echo "console.log('hello');" > src/tiptap/index.js
npm run build:editor
ls -lh static/blog/tiptap.js
```

Expected: a few-KB minified `static/blog/tiptap.js` exists.

- [ ] **Step 5: Remove the smoke-test stub and commit toolchain setup**

Run:
```bash
rm src/tiptap/index.js static/blog/tiptap.js
git add package.json package-lock.json
git commit -m "Add Tiptap, esbuild, and vitest toolchain"
```

---

## Task 2: Implement `normaliseOfficeHtml`

**Files:**
- Create: `src/tiptap/paste.js`
- Create: `src/tiptap/__tests__/normalise.test.js`
- Create: `src/tiptap/__tests__/fixtures/google-docs-paste.html`
- Create: `src/tiptap/__tests__/fixtures/word-paste.html`
- Create: `src/tiptap/__tests__/fixtures/notion-paste.html`

- [ ] **Step 1: Capture fixture files**

Write the following minimal fixtures (these mimic what each source emits — captured once, used as goldens):

`src/tiptap/__tests__/fixtures/google-docs-paste.html`:
```html
<meta charset="utf-8"><b id="docs-internal-guid-aaaa" style="font-weight:normal">
<p dir="ltr" style="line-height:1.38;margin-top:0pt;margin-bottom:0pt;"><span style="font-size:14pt;font-family:Arial;color:#000000;font-weight:700">Headline</span></p>
<p dir="ltr" style="line-height:1.38;text-align:center"><span style="font-family:Arial">Some <a href="https://example.com" style="color:#1155cc;text-decoration:underline">link</a> here.</span></p>
</b>
```

`src/tiptap/__tests__/fixtures/word-paste.html`:
```html
<html xmlns:o="urn:schemas-microsoft-com:office:office" xmlns:w="urn:schemas-microsoft-com:office:word">
<head><style><!--mso-style-name:"Normal";--></style></head>
<body><!--StartFragment--><p class="MsoNormal" style="mso-margin-top-alt:auto"><b style="mso-bidi-font-weight:normal"><span style="font-family:&quot;Calibri&quot;,sans-serif">Heading</span></b></p>
<p class="MsoNormal"><span style="font-family:&quot;Calibri&quot;,sans-serif">Body text with <a href="https://example.com">a link</a>.</span></p><!--EndFragment--></body></html>
```

`src/tiptap/__tests__/fixtures/notion-paste.html`:
```html
<meta charset='utf-8'><meta charset="utf-8"><div data-pm-slice="1 1 []"><h2>Heading</h2><p>Body with <strong>bold</strong> and <a href="https://example.com">a link</a>.</p></div>
```

- [ ] **Step 2: Write failing tests**

`src/tiptap/__tests__/normalise.test.js`:
```js
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { normaliseOfficeHtml, looksLikeOfficeHtml } from "../paste.js";

const here = dirname(fileURLToPath(import.meta.url));
const fixture = (name) => readFileSync(resolve(here, "fixtures", name), "utf8");

describe("looksLikeOfficeHtml", () => {
  it("detects Google Docs paste via docs-internal-guid", () => {
    expect(looksLikeOfficeHtml(fixture("google-docs-paste.html"))).toBe(true);
  });
  it("detects Word paste via mso- and office namespaces", () => {
    expect(looksLikeOfficeHtml(fixture("word-paste.html"))).toBe(true);
  });
  it("detects Notion paste via data-pm-slice", () => {
    expect(looksLikeOfficeHtml(fixture("notion-paste.html"))).toBe(true);
  });
  it("returns false for plain HTML", () => {
    expect(looksLikeOfficeHtml("<p>hello</p>")).toBe(false);
  });
});

describe("normaliseOfficeHtml", () => {
  it("strips style and class attributes", () => {
    const out = normaliseOfficeHtml(fixture("google-docs-paste.html"));
    expect(out).not.toMatch(/style=/);
    expect(out).not.toMatch(/class=/);
  });
  it("promotes <b> with font-weight:bold context to <strong>", () => {
    const out = normaliseOfficeHtml(fixture("google-docs-paste.html"));
    expect(out).toContain("<strong>");
    expect(out).toContain("Headline");
  });
  it("preserves <a href> targets", () => {
    const out = normaliseOfficeHtml(fixture("google-docs-paste.html"));
    expect(out).toContain('href="https://example.com"');
  });
  it("removes Office namespaced tags from Word paste", () => {
    const out = normaliseOfficeHtml(fixture("word-paste.html"));
    expect(out).not.toMatch(/<o:/);
    expect(out).not.toMatch(/<w:/);
    expect(out).not.toMatch(/MsoNormal/);
  });
  it("removes <style>, <meta>, <link>, <script>", () => {
    const out = normaliseOfficeHtml(fixture("word-paste.html"));
    expect(out).not.toMatch(/<style/);
    expect(out).not.toMatch(/<meta/);
    expect(out).not.toMatch(/<script/);
  });
  it("preserves Notion's already-semantic markup", () => {
    const out = normaliseOfficeHtml(fixture("notion-paste.html"));
    expect(out).toContain("<h2>Heading</h2>");
    expect(out).toContain("<strong>bold</strong>");
  });
});
```

- [ ] **Step 3: Run tests to confirm they fail**

Run:
```bash
npm run test:js
```

Expected: All tests FAIL with `Cannot find module '../paste.js'` or similar.

- [ ] **Step 4: Implement `paste.js` (functions exported in this task only)**

`src/tiptap/paste.js`:
```js
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
  [...doc.querySelectorAll("*")].forEach((el) => {
    if (!ALLOWED_TAGS.has(el.tagName.toLowerCase())) unwrap(el);
  });

  return doc.body.innerHTML.trim();
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run:
```bash
npm run test:js
```

Expected: All `normalise.test.js` tests PASS. Output ends with `✓` lines and no failures.

- [ ] **Step 6: Commit**

Run:
```bash
git add src/tiptap/paste.js src/tiptap/__tests__/normalise.test.js src/tiptap/__tests__/fixtures/
git commit -m "Add Office/Docs/Notion paste normaliser"
```

---

## Task 3: Implement `smartPasteHandler` dispatch

**Files:**
- Modify: `src/tiptap/paste.js`
- Create: `src/tiptap/__tests__/paste.test.js`

- [ ] **Step 1: Write failing tests**

`src/tiptap/__tests__/paste.test.js`:
```js
import { describe, it, expect, vi } from "vitest";
import { smartPasteHandler, looksLikeMarkdown } from "../paste.js";

function pasteEvent({ html, text, files } = {}) {
  const types = [];
  if (html) types.push("text/html");
  if (text) types.push("text/plain");
  return {
    clipboardData: {
      types,
      files: files || [],
      getData: (t) => (t === "text/html" ? html ?? "" : t === "text/plain" ? text ?? "" : ""),
    },
    preventDefault: vi.fn(),
  };
}

function fakeView({ inCodeBlock = false } = {}) {
  return {
    state: {
      selection: {
        $from: {
          parent: { type: { name: inCodeBlock ? "codeBlock" : "paragraph" } },
        },
      },
    },
    inserted: [],
    pasteHTML(html) { this.inserted.push(html); },
  };
}

describe("looksLikeMarkdown", () => {
  it("detects ATX headings", () => {
    expect(looksLikeMarkdown("## Hello")).toBe(true);
  });
  it("detects fenced code blocks", () => {
    expect(looksLikeMarkdown("```\ncode\n```")).toBe(true);
  });
  it("detects bullet lists", () => {
    expect(looksLikeMarkdown("- item one\n- item two")).toBe(true);
  });
  it("detects markdown links", () => {
    expect(looksLikeMarkdown("see [docs](https://x.com)")).toBe(true);
  });
  it("returns false for plain prose", () => {
    expect(looksLikeMarkdown("Just a sentence with no markup.")).toBe(false);
  });
});

describe("smartPasteHandler", () => {
  it("returns false (default paste) inside a code block, even for markdown", () => {
    const view = fakeView({ inCodeBlock: true });
    const ev = pasteEvent({ text: "## not a heading" });
    expect(smartPasteHandler(view, ev)).toBe(false);
    expect(view.inserted).toEqual([]);
  });

  it("normalises and inserts Office HTML when present", () => {
    const view = fakeView();
    const officeHtml = '<p class="MsoNormal" style="font-family:Calibri"><b>Hi</b></p>';
    const ev = pasteEvent({ html: officeHtml });
    expect(smartPasteHandler(view, ev)).toBe(true);
    expect(view.inserted[0]).toContain("<strong>");
    expect(view.inserted[0]).not.toMatch(/style=|class=/);
  });

  it("converts markdown text to HTML and inserts", () => {
    const view = fakeView();
    const ev = pasteEvent({ text: "## Hello\n\n**world**" });
    expect(smartPasteHandler(view, ev)).toBe(true);
    expect(view.inserted[0]).toContain("<h2>");
    expect(view.inserted[0]).toContain("<strong>world</strong>");
  });

  it("drops image-only clipboard (no upload in v1)", () => {
    const view = fakeView();
    const ev = pasteEvent({ files: [new File([""], "x.png", { type: "image/png" })] });
    expect(smartPasteHandler(view, ev)).toBe(true);
    expect(view.inserted).toEqual([]);
    expect(ev.preventDefault).toHaveBeenCalled();
  });

  it("returns false for plain prose without markdown signals", () => {
    const view = fakeView();
    const ev = pasteEvent({ text: "Just a sentence." });
    expect(smartPasteHandler(view, ev)).toBe(false);
    expect(view.inserted).toEqual([]);
  });
});
```

- [ ] **Step 2: Run tests to confirm they fail**

Run:
```bash
npm run test:js
```

Expected: `paste.test.js` tests FAIL with `looksLikeMarkdown is not a function` / `smartPasteHandler is not a function`.

- [ ] **Step 3: Extend `paste.js` with markdown detection + dispatcher**

Append to `src/tiptap/paste.js`:
```js
import { marked } from "marked";

const MARKDOWN_HINTS = /(^|\n)(#{1,6}\s|>\s|[*-]\s|\d+\.\s|```|---|\*\*[^*]+\*\*|__[^_]+__|\[[^\]]+\]\([^)]+\))/;

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
```

The test uses a fake `view.pasteHTML(html)` shim; in the real Tiptap mount we'll wire this to `editor.commands.insertContent(html)` in Task 5 by passing a thin adapter — but the dispatcher itself stays adapter-agnostic.

- [ ] **Step 4: Run tests to verify they pass**

Run:
```bash
npm run test:js
```

Expected: both test files (`normalise.test.js` + `paste.test.js`) PASS.

- [ ] **Step 5: Commit**

Run:
```bash
git add src/tiptap/paste.js src/tiptap/__tests__/paste.test.js
git commit -m "Add smart paste dispatcher (Office HTML + markdown + image drop)"
```

---

## Task 4: Slash menu extension

**Files:**
- Create: `src/tiptap/slash-menu.js`

- [ ] **Step 1: Write the extension**

`src/tiptap/slash-menu.js`:
```js
import { Extension } from "@tiptap/core";
import Suggestion from "@tiptap/suggestion";

const ITEMS = [
  { label: "Heading 2",  command: (e) => e.chain().focus().toggleHeading({ level: 2 }).run() },
  { label: "Heading 3",  command: (e) => e.chain().focus().toggleHeading({ level: 3 }).run() },
  { label: "Quote",      command: (e) => e.chain().focus().toggleBlockquote().run() },
  { label: "Code block", command: (e) => e.chain().focus().toggleCodeBlock().run() },
  { label: "Divider",    command: (e) => e.chain().focus().setHorizontalRule().run() },
];

function createPopup() {
  const el = document.createElement("div");
  el.className = "slash-menu";
  el.setAttribute("role", "listbox");
  document.body.appendChild(el);
  return el;
}

function renderItems(el, items, selected, onPick) {
  el.innerHTML = "";
  items.forEach((item, idx) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.textContent = item.label;
    btn.className = "slash-menu__item" + (idx === selected ? " is-selected" : "");
    btn.addEventListener("mousedown", (e) => { e.preventDefault(); onPick(item); });
    el.appendChild(btn);
  });
}

function positionPopup(el, clientRect) {
  const rect = clientRect();
  if (!rect) { el.style.display = "none"; return; }
  el.style.display = "block";
  el.style.position = "absolute";
  el.style.top  = `${rect.bottom + window.scrollY + 4}px`;
  el.style.left = `${rect.left + window.scrollX}px`;
}

export const SlashMenu = Extension.create({
  name: "slashMenu",
  addOptions() {
    return {
      suggestion: {
        char: "/",
        startOfLine: false,
        command: ({ editor, range, props }) => {
          editor.chain().focus().deleteRange(range).run();
          props.command(editor);
        },
        items: ({ query }) =>
          ITEMS.filter((i) => i.label.toLowerCase().includes(query.toLowerCase())).slice(0, 6),
        render: () => {
          let popup, items = [], selected = 0, clientRect = null, commandPick;
          return {
            onStart: (props) => {
              popup = createPopup();
              items = props.items;
              selected = 0;
              clientRect = props.clientRect;
              commandPick = props.command;
              renderItems(popup, items, selected, commandPick);
              positionPopup(popup, clientRect);
            },
            onUpdate: (props) => {
              items = props.items;
              selected = 0;
              clientRect = props.clientRect;
              commandPick = props.command;
              renderItems(popup, items, selected, commandPick);
              positionPopup(popup, clientRect);
            },
            onKeyDown: ({ event }) => {
              if (event.key === "ArrowDown") {
                selected = (selected + 1) % items.length;
                renderItems(popup, items, selected, commandPick);
                return true;
              }
              if (event.key === "ArrowUp") {
                selected = (selected - 1 + items.length) % items.length;
                renderItems(popup, items, selected, commandPick);
                return true;
              }
              if (event.key === "Enter") {
                if (items[selected]) commandPick(items[selected]);
                return true;
              }
              if (event.key === "Escape") {
                popup.remove();
                return true;
              }
              return false;
            },
            onExit: () => {
              popup?.remove();
            },
          };
        },
      },
    };
  },
  addProseMirrorPlugins() {
    return [Suggestion({ editor: this.editor, ...this.options.suggestion })];
  },
});
```

- [ ] **Step 2: Install the suggestion dependency**

Run:
```bash
npm install --save @tiptap/suggestion@^2.8.0
```

Expected: `@tiptap/suggestion` appears in `package.json` dependencies.

- [ ] **Step 3: Smoke-build the file to catch import errors**

Run:
```bash
npx esbuild src/tiptap/slash-menu.js --bundle --target=es2020 --outfile=/tmp/slash-check.js
ls -lh /tmp/slash-check.js && rm /tmp/slash-check.js
```

Expected: build succeeds; output file size > 0.

- [ ] **Step 4: Commit**

Run:
```bash
git add src/tiptap/slash-menu.js package.json package-lock.json
git commit -m "Add slash menu extension for inserting blocks"
```

---

## Task 5: Editor entry point

**Files:**
- Create: `src/tiptap/index.js`

- [ ] **Step 1: Write the entry point**

`src/tiptap/index.js`:
```js
import { Editor } from "@tiptap/core";
import StarterKit from "@tiptap/starter-kit";
import Underline from "@tiptap/extension-underline";
import Link from "@tiptap/extension-link";
import BubbleMenu from "@tiptap/extension-bubble-menu";
import { SlashMenu } from "./slash-menu.js";
import { smartPasteHandler } from "./paste.js";

function bindBubbleClicks(bubbleEl, editor) {
  bubbleEl.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-cmd]");
    if (!btn) return;
    e.preventDefault();
    const [cmd, arg] = btn.dataset.cmd.split(":");
    const chain = editor.chain().focus();
    if (cmd === "setLink") {
      const url = window.prompt("Link URL");
      if (!url) return;
      chain.setLink({ href: url }).run();
      return;
    }
    if (arg) chain[cmd]({ level: Number(arg) }).run();
    else chain[cmd]().run();
  });
}

function mountEditor(shell) {
  const textarea = shell.querySelector("[data-tiptap-input]");
  const mount    = shell.querySelector("[data-editor]");
  const bubble   = shell.querySelector("[data-bubble]");

  const editor = new Editor({
    element: mount,
    extensions: [
      StarterKit.configure({ heading: { levels: [2, 3] } }),
      Underline,
      Link.configure({ openOnClick: false, autolink: true, HTMLAttributes: { rel: "noopener noreferrer" } }),
      BubbleMenu.configure({ element: bubble }),
      SlashMenu,
    ],
    content: textarea.value,
    editorProps: {
      attributes: { class: "prose prose-lg max-w-none focus:outline-none" },
      handlePaste: (view, event) =>
        smartPasteHandler(
          {
            state: view.state,
            pasteHTML: (html) => editor.commands.insertContent(html),
          },
          event,
        ),
    },
    onUpdate: ({ editor }) => {
      textarea.value = editor.getHTML();
    },
  });

  bindBubbleClicks(bubble, editor);

  // Sync once before form submit in case input event was throttled.
  const form = textarea.closest("form");
  if (form) {
    form.addEventListener("submit", () => { textarea.value = editor.getHTML(); });
  }

  return editor;
}

function init() {
  document.querySelectorAll(".tiptap-shell").forEach(mountEditor);
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
```

- [ ] **Step 2: Build the bundle to verify all imports resolve**

Run:
```bash
npm run build:editor
ls -lh static/blog/tiptap.js
```

Expected: bundle builds with no errors; file size 60–120 KB.

- [ ] **Step 3: Commit**

Run:
```bash
git add src/tiptap/index.js
git commit -m "Add Tiptap editor entry point (StarterKit + bubble + slash + paste)"
```

---

## Task 6: Editor styles

**Files:**
- Create: `static/blog/tiptap.css`

- [ ] **Step 1: Write the stylesheet**

`static/blog/tiptap.css`:
```css
/* Tiptap body editor — bubble toolbar, slash menu, prose typography. */

.tiptap-shell {
  position: relative;
}

[data-tiptap-input] {
  display: none !important;
}

.tiptap-root {
  border: 1px solid var(--md-sys-color-outline-variant, #ccc);
  border-radius: 12px;
  padding: 1.5rem;
  background: var(--md-sys-color-surface, #fff);
}

[data-editor] {
  outline: none;
}

[data-editor] p          { margin: 0 0 1em; line-height: 1.7; }
[data-editor] h1,
[data-editor] h2,
[data-editor] h3         { font-weight: 700; line-height: 1.25; margin: 1.5em 0 0.5em; }
[data-editor] h2         { font-size: 1.75rem; }
[data-editor] h3         { font-size: 1.375rem; }
[data-editor] blockquote {
  border-left: 4px solid var(--md-sys-color-primary, #0f3d3e);
  padding-left: 1em;
  color: var(--md-sys-color-on-surface-variant, #555);
  margin: 1em 0;
  font-style: italic;
}
[data-editor] ul,
[data-editor] ol         { padding-left: 1.5em; margin: 0 0 1em; }
[data-editor] li         { margin-bottom: 0.25em; }
[data-editor] a          { color: var(--md-sys-color-primary, #0f3d3e); text-decoration: underline; }
[data-editor] code       { background: rgba(0,0,0,0.06); padding: 0.1em 0.35em; border-radius: 4px; font-family: ui-monospace, monospace; }
[data-editor] pre        { background: rgba(0,0,0,0.06); padding: 1em; border-radius: 8px; overflow-x: auto; }
[data-editor] hr         { border: 0; border-top: 1px solid var(--md-sys-color-outline-variant, #ccc); margin: 2em 0; }

/* Bubble toolbar */
.bubble-menu {
  display: flex;
  gap: 0.25rem;
  background: #111;
  color: #fff;
  padding: 0.25rem;
  border-radius: 6px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.15);
}
.bubble-menu[aria-hidden="true"] { display: none; }
.bubble-menu button {
  background: transparent;
  color: inherit;
  border: 0;
  padding: 0.35rem 0.6rem;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.875rem;
}
.bubble-menu button:hover,
.bubble-menu button.is-active { background: rgba(255,255,255,0.15); }

/* Slash menu */
.slash-menu {
  z-index: 1000;
  background: #fff;
  color: #111;
  border: 1px solid #ccc;
  border-radius: 8px;
  box-shadow: 0 6px 18px rgba(0,0,0,0.15);
  padding: 0.25rem;
  min-width: 180px;
}
.slash-menu__item {
  display: block;
  width: 100%;
  text-align: left;
  background: transparent;
  border: 0;
  padding: 0.5rem 0.75rem;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.875rem;
}
.slash-menu__item.is-selected,
.slash-menu__item:hover { background: rgba(0,0,0,0.05); }
```

- [ ] **Step 2: Commit**

Run:
```bash
git add static/blog/tiptap.css
git commit -m "Add Tiptap editor stylesheet"
```

---

## Task 7: Widget template

**Files:**
- Create: `blog/templates/blog/widgets/tiptap.html`

- [ ] **Step 1: Write the template**

`blog/templates/blog/widgets/tiptap.html`:
```html
<div class="tiptap-shell">
  <textarea name="{{ widget.name }}"
            {% if widget.attrs.required %}required{% endif %}
            data-tiptap-input
            hidden>{{ widget.value|default_if_none:"" }}</textarea>

  <div data-tiptap-root class="tiptap-root">
    <div data-bubble class="bubble-menu" role="toolbar" aria-hidden="true">
      <button type="button" data-cmd="toggleBold" aria-label="Bold"><b>B</b></button>
      <button type="button" data-cmd="toggleItalic" aria-label="Italic"><i>I</i></button>
      <button type="button" data-cmd="toggleUnderline" aria-label="Underline"><u>U</u></button>
      <button type="button" data-cmd="toggleHeading:2">H2</button>
      <button type="button" data-cmd="toggleHeading:3">H3</button>
      <button type="button" data-cmd="toggleBlockquote">&ldquo;</button>
      <button type="button" data-cmd="setLink">link</button>
    </div>
    <div data-editor class="prose prose-lg max-w-none min-h-[500px]"></div>
  </div>
</div>
```

- [ ] **Step 2: Commit**

Run:
```bash
git add blog/templates/blog/widgets/tiptap.html
git commit -m "Add Tiptap widget template"
```

---

## Task 8: TiptapWidget class + Python tests

**Files:**
- Create: `blog/widgets.py`
- Create: `blog/tests_tiptap.py`

The project uses **tabs** for Python indentation per `pyproject.toml`. All Python code in this task uses tabs.

- [ ] **Step 1: Write failing tests**

`blog/tests_tiptap.py`:
```python
from django.test import TestCase
from django.urls import reverse

from account.models import Account
from blog.forms import CreateBlogPostForm
from blog.models import BlogPost, Category
from blog.widgets import TiptapWidget


class TiptapWidgetRenderTests(TestCase):
	def test_renders_hidden_textarea(self):
		html = TiptapWidget().render('body', '<p>hi</p>')
		self.assertIn('<textarea', html)
		self.assertIn('hidden', html)
		self.assertIn('data-tiptap-input', html)

	def test_renders_editor_mount_and_bubble(self):
		html = TiptapWidget().render('body', '')
		self.assertIn('data-tiptap-root', html)
		self.assertIn('data-bubble', html)
		self.assertIn('data-editor', html)

	def test_preserves_initial_value(self):
		html = TiptapWidget().render('body', '<h2>Hi</h2>')
		self.assertIn('<h2>Hi</h2>', html)

	def test_media_includes_tiptap_assets(self):
		widget = TiptapWidget()
		self.assertIn('blog/tiptap.js', str(widget.media))
		self.assertIn('blog/tiptap.css', str(widget.media))


class TiptapFormRoundtripTests(TestCase):
	def setUp(self):
		self.user = Account.objects.create_user(
			email='t@nyasablog.com', username='t', password='p',
		)
		self.user.email_verified = True
		self.user.save()
		self.category, _ = Category.objects.get_or_create(
			name='Culture', slug='culture', defaults={'description': 'x'},
		)

	def test_form_uses_tiptap_widget_for_body(self):
		form = CreateBlogPostForm()
		self.assertIsInstance(form.fields['body'].widget, TiptapWidget)

	def test_form_roundtrip_preserves_html(self):
		form = CreateBlogPostForm({
			'title': 'T',
			'body': '<h2>X</h2><p>Y</p>',
			'category': self.category.id,
			'status': 'draft',
		})
		self.assertTrue(form.is_valid(), form.errors)
		post = form.save(commit=False)
		post.author = self.user
		post.save()
		form.save_m2m()
		post.refresh_from_db()
		self.assertEqual(post.body, '<h2>X</h2><p>Y</p>')


class SanitiserRegressionTests(TestCase):
	"""The editor swap MUST NOT regress the server-side sanitiser."""

	def setUp(self):
		self.user = Account.objects.create_user(
			email='s@nyasablog.com', username='s', password='p',
		)
		self.user.email_verified = True
		self.user.save()
		self.category, _ = Category.objects.get_or_create(
			name='Tech', slug='tech', defaults={'description': 'x'},
		)

	def test_detail_view_strips_style_attribute(self):
		post = BlogPost.objects.create(
			title='S', slug='s-style',
			body='<p style="color:red">X</p>',
			author=self.user, category=self.category, status='published',
		)
		r = self.client.get(reverse('detail', kwargs={'slug': post.slug}))
		self.assertEqual(r.status_code, 200)
		self.assertNotIn(b'style=', r.content)
		self.assertIn(b'<p>X</p>', r.content)

	def test_detail_view_strips_script(self):
		post = BlogPost.objects.create(
			title='S', slug='s-script',
			body='<p>safe</p><script>alert(1)</script>',
			author=self.user, category=self.category, status='published',
		)
		r = self.client.get(reverse('detail', kwargs={'slug': post.slug}))
		self.assertEqual(r.status_code, 200)
		self.assertNotIn(b'<script>', r.content)
```

- [ ] **Step 2: Run tests to confirm they fail**

Run:
```bash
python manage.py test blog.tests_tiptap -v 2
```

Expected: ImportError on `blog.widgets` — `TiptapWidget` does not exist yet.

- [ ] **Step 3: Implement the widget**

`blog/widgets.py`:
```python
from django import forms


class TiptapWidget(forms.Textarea):
	"""Renders a hidden <textarea> + a Tiptap mount.

	The JS bundle (static/blog/tiptap.js) initialises Tiptap on every
	.tiptap-shell and mirrors editor.getHTML() back to the hidden textarea
	on every input event. Server receives plain text (the HTML string),
	exactly as it did with CKEditor 5.
	"""

	template_name = 'blog/widgets/tiptap.html'

	class Media:
		css = {'all': ['blog/tiptap.css']}
		js = ['blog/tiptap.js']

	def __init__(self, attrs=None):
		defaults = {'hidden': True, 'data-tiptap-input': ''}
		super().__init__({**defaults, **(attrs or {})})
```

- [ ] **Step 4: Run tests to verify they pass**

Tests still need the widget wired into the form (Task 9) for `test_form_uses_tiptap_widget_for_body`. Skip that one for now by running individual tests:

Run:
```bash
python manage.py test blog.tests_tiptap.TiptapWidgetRenderTests -v 2
```

Expected: all four widget-render tests PASS.

The form-roundtrip and sanitiser tests will run green after Task 9 + Task 10.

- [ ] **Step 5: Commit**

Run:
```bash
git add blog/widgets.py blog/tests_tiptap.py
git commit -m "Add TiptapWidget with hidden textarea + mount template"
```

---

## Task 9: Wire widget into forms

**Files:**
- Modify: `blog/forms.py`

- [ ] **Step 1: Update both forms to use TiptapWidget**

Replace the contents of `blog/forms.py` with:

```python
from django import forms

from blog.models import BlogPost, Comment
from blog.widgets import TiptapWidget


class CommentForm(forms.ModelForm):

	class Meta:
		model = Comment
		fields = ['body']
		widgets = {
			'body': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Write a comment...'}),
		}


class CreateBlogPostForm(forms.ModelForm):

	class Meta:
		model = BlogPost
		fields = ['title', 'body', 'image', 'category', 'tags', 'status']
		widgets = {
			'tags': forms.CheckboxSelectMultiple(),
			'body': TiptapWidget(),
		}


class UpdateBlogPostForm(forms.ModelForm):

	class Meta:
		model = BlogPost
		fields = ['title', 'body', 'image', 'category', 'tags', 'status']
		widgets = {
			'tags': forms.CheckboxSelectMultiple(),
			'body': TiptapWidget(),
		}

	def save(self, commit=True):
		if not self.cleaned_data.get('image'):
			self.cleaned_data['image'] = self.instance.image
		return super().save(commit=commit)
```

- [ ] **Step 2: Run the widget-binding test**

Run:
```bash
python manage.py test blog.tests_tiptap.TiptapFormRoundtripTests.test_form_uses_tiptap_widget_for_body -v 2
```

Expected: PASS.

- [ ] **Step 3: Commit**

Run:
```bash
git add blog/forms.py
git commit -m "Use TiptapWidget for BlogPost body in create + update forms"
```

---

## Task 10: Migrate `body` field to TextField

**Files:**
- Modify: `blog/models.py`
- Create: `blog/migrations/0010_alter_blogpost_body.py`

- [ ] **Step 1: Update the model field**

In `blog/models.py`, locate the `BlogPost` class and change:

```python
body = CKEditor5Field(max_length=20000, blank=True, config_name='default')
```

to:

```python
body = models.TextField(max_length=20000, blank=True)
```

Also remove the now-unused import at line 11:
```python
from django_ckeditor_5.fields import CKEditor5Field
```

- [ ] **Step 2: Generate the migration**

Run:
```bash
python manage.py makemigrations blog --name alter_blogpost_body
```

Expected: `blog/migrations/0010_alter_blogpost_body.py` created. It should contain a single `migrations.AlterField` for `body`.

- [ ] **Step 3: Verify the migration is no-op at the column level**

Run:
```bash
python manage.py sqlmigrate blog 0010
```

Expected: SQLite path emits no DDL (or only a comment); the change is metadata-only.

- [ ] **Step 4: Apply the migration**

Run:
```bash
python manage.py migrate blog
```

Expected: `Applying blog.0010_alter_blogpost_body... OK`.

- [ ] **Step 5: Run the form-roundtrip and sanitiser tests**

Run:
```bash
python manage.py test blog.tests_tiptap -v 2
```

Expected: all tests in the file PASS, including the previously skipped ones.

- [ ] **Step 6: Commit**

Run:
```bash
git add blog/models.py blog/migrations/0010_alter_blogpost_body.py
git commit -m "Switch BlogPost.body from CKEditor5Field to TextField"
```

---

## Task 11: Remove CKEditor 5

**Files:**
- Modify: `mysite/settings.py`
- Modify: `mysite/urls.py`
- Modify: `requirements.txt`

- [ ] **Step 1: Remove CKEditor config from `mysite/settings.py`**

In `mysite/settings.py`:

a) In `INSTALLED_APPS` (around line 42), remove the line:
```python
'django_ckeditor_5',
```

b) Delete the block at lines 241–256:
```python
# CKEditor 5
CKEDITOR_5_CONFIGS = {
    'default': {
        'toolbar': [
            'heading', '|',
            'bold', 'italic', 'underline', 'strikethrough', '|',
            'bulletedList', 'numberedList', '|',
            'blockQuote', 'codeBlock', '|',
            'link', 'imageUpload', '|',
            'undo', 'redo',
        ],
        'height': '400px',
        'width': '100%',
    },
}
CK_EDITOR_5_UPLOAD_FILE_VIEW_NAME = "ck_editor_5_upload_file"
```

- [ ] **Step 2: Remove the CKEditor URL include from `mysite/urls.py`**

Delete the two lines around `mysite/urls.py:87-88`:
```python
# CKEditor 5
path('ckeditor5/', include('django_ckeditor_5.urls')),
```

- [ ] **Step 3: Remove `django-ckeditor-5` from `requirements.txt`**

Run:
```bash
grep -v '^django-ckeditor-5' requirements.txt > /tmp/req && mv /tmp/req requirements.txt
```

Verify:
```bash
grep django-ckeditor-5 requirements.txt
```

Expected: no matches.

- [ ] **Step 4: Uninstall the package locally**

Run:
```bash
pip uninstall -y django-ckeditor-5
```

- [ ] **Step 5: Run the full test suite to verify nothing else depends on CKEditor**

Run:
```bash
python manage.py test blog account personal -v 2 --parallel auto --shuffle
```

Expected: all tests PASS.

- [ ] **Step 6: Commit**

Run:
```bash
git add mysite/settings.py mysite/urls.py requirements.txt
git commit -m "Remove django-ckeditor-5 (replaced by Tiptap)"
```

---

## Task 12: Build and commit the editor bundle

**Files:**
- Built: `static/blog/tiptap.js`

The Tiptap JS bundle is a built artefact, committed to git so `collectstatic` can push it to Spaces in production. (Same pattern used for `static/css/tailwind.min.css`.)

- [ ] **Step 1: Build the bundle**

Run:
```bash
npm run build:editor
```

Expected: `static/blog/tiptap.js` written, size 60–120 KB.

- [ ] **Step 2: Inspect the bundle**

Run:
```bash
ls -lh static/blog/tiptap.js
head -c 200 static/blog/tiptap.js
```

Expected: a minified file starting with something like `(()=>{var ` — confirms esbuild bundling worked.

- [ ] **Step 3: Verify it's loaded by the create page**

Run:
```bash
python manage.py runserver
```

In another shell, request the create page:
```bash
curl -s -L -b /tmp/c -c /tmp/c http://localhost:8000/blog/create/ | grep -o 'tiptap\.\(js\|css\)' | sort -u
```

Expected output:
```
tiptap.css
tiptap.js
```

(You'll be redirected to login if not authenticated; the test only checks asset references, which appear on the create page template after login. If 0 matches, log in via the browser at `/login/` then re-run the curl with session cookies.)

Kill the runserver (`Ctrl+C`).

- [ ] **Step 4: Commit the bundle**

Run:
```bash
git add static/blog/tiptap.js
git commit -m "Build Tiptap editor bundle"
```

---

## Task 13: Manual smoke test

This task has no code. Run through the checklist locally before considering the work complete; record results in the PR description.

- [ ] **Step 1: Start the dev server**

Run:
```bash
python manage.py runserver
```

- [ ] **Step 2: Sign in and open the create page**

In a browser, navigate to `http://localhost:8000/blog/create/`.

Expected: the body editor renders as a Tiptap surface (no CKEditor toolbar at the top), not a vanilla `<textarea>`. The bubble toolbar is hidden until text is selected.

- [ ] **Step 3: Run through the checklist**

For each item, observe and tick:

- [ ] Typing `## A heading` and pressing space → becomes `<h2>A heading</h2>`.
- [ ] Selecting the heading → bubble toolbar appears near the selection.
- [ ] Clicking **B** in the bubble → toggles bold on the selection.
- [ ] Clicking **link** → prompts for URL; entering one wraps the selection in `<a>`.
- [ ] On a new empty line, typing `/` → slash menu appears with Heading 2, Heading 3, Quote, Code block, Divider.
- [ ] Arrow keys navigate the slash menu; Enter inserts the chosen block; Escape closes.
- [ ] Pasting from Google Docs (any doc with bold + a link) → headings are preserved as `<h2>`, bold survives as `<strong>`, link `href` survives, but no inline `style=` or `class=c1` attributes appear in the editor's HTML.
- [ ] Pasting a markdown snippet (`## Hello\n\n**world**`) into an empty paragraph → renders as a heading + bold paragraph.
- [ ] Pasting the same markdown snippet inside a code block → appears as literal text `## Hello` etc.
- [ ] Pasting an image file from the clipboard → no upload, no error, the editor ignores it (v1 limitation, documented).
- [ ] Submitting the form → post is saved with the editor's HTML in `body`.
- [ ] Opening the new post's detail page → renders the same HTML, with the sanitiser stripping any inline `style=` you tried to inject.
- [ ] Open an **existing** post created by old CKEditor — Edit → content loads in Tiptap unchanged. Saving without edits round-trips byte-equal.
- [ ] On a 375 px mobile viewport (DevTools), the bubble toolbar fits within the viewport.

- [ ] **Step 4: Capture results in the PR description**

Copy the checklist into the PR description, marking each item with the outcome (✔ / ✘ / N/A).

---

## Task 14: Run final test suites and prepare the PR

**Files:** none (housekeeping)

- [ ] **Step 1: Run Python test suite**

Run:
```bash
python manage.py test blog account personal -v 2 --parallel auto --shuffle
```

Expected: all tests PASS.

- [ ] **Step 2: Run JS test suite**

Run:
```bash
npm run test:js
```

Expected: all `vitest` tests PASS.

- [ ] **Step 3: Run ruff**

Run:
```bash
ruff check . && ruff format --check .
```

Expected: no errors.

- [ ] **Step 4: Push branch**

Run:
```bash
git push -u origin feature/medium-body-editor
```

- [ ] **Step 5: Open PR via gh**

Run:
```bash
gh pr create \
  --base master \
  --title "Replace CKEditor 5 body editor with Tiptap (Medium-style)" \
  --body "$(cat <<'EOF'
## Summary

Replace the CKEditor 5 widget at the body field of `BlogPost` with a Tiptap-based editor that gives Medium-style UX (bubble toolbar on selection, slash menu for blocks) and fixes two paste bugs:

- Rich text from Word / Google Docs / Notion now keeps semantic typography (headings, lists, emphasis, links) while presentational styles are dropped at paste time.
- Pasted markdown text is converted to HTML on paste, not stored literally.

Storage stays HTML. Server-side sanitiser (`blog/templatetags/sanitize.py`) is unchanged and remains the security boundary.

## Scope (locked from spec)

Only `{{ form.body }}` is replaced — the title input, featured image dropzone, sidebar (category/tags/status), and Publish/Save Draft buttons are untouched. Inline image upload inside the body is deferred to v2 (documented limitation).

Spec: `docs/superpowers/specs/2026-05-14-medium-style-body-editor-design.md`

## Test plan

Copy the manual smoke-test checklist results from Task 13 here.

## Deploy

- `rsync` source with `--exclude=settings.ini --exclude=.env`
- `pip install -r requirements.txt` (removes django-ckeditor-5)
- `python manage.py migrate` (applies 0010_alter_blogpost_body)
- `python manage.py collectstatic --noinput` (pushes tiptap.js to Spaces)
- `chown -R ephraim:www-data .`
- `systemctl restart gunicorn`
- Smoke test on prod
EOF
)"
```

Expected: PR URL returned.

---

## Notes for the executor

- **The codebase uses tabs** for Python indentation (per `pyproject.toml [tool.ruff.format] indent-style = "tab"`). Every Python code block in this plan already uses tabs. Do not auto-format to spaces.
- **No `Co-Authored-By: Claude` trailers** in commit messages or the PR body — repo convention (see `~/.claude/CLAUDE.md`).
- **Bundle is committed to git**, like `static/css/tailwind.min.css`. `collectstatic` reads from git-checked-out static files to push to Spaces.
- **Migration 0010 is metadata-only** for both SQLite and Postgres (TEXT ↔ TEXT). Reversible without data loss.
- **Tests must pass before commit at each task** — TDD discipline is not optional. The project's hardening convention is "failing test first, then minimum implementation, then refactor" (see `~/.claude/projects/-Users-admin/memory/core-memories.md`).
