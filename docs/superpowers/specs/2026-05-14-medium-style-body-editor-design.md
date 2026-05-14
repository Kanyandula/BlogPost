# Medium-style body editor — design

**Date:** 2026-05-14
**Author:** Ephraim Kanyandula
**Status:** Draft — awaiting review

## Problem

Two related bugs report against `https://nyasablog.com/blog/create/`:

1. **Pasted rich text loses typography.** Pasting from Word / Google Docs /
   Notion strips formatting because CKEditor 5's current toolbar configuration
   has no plugins for the inbound features, and the server-side sanitiser
   (`blog/templatetags/sanitize.py`) intentionally drops `style=` attributes.
2. **Pasted markdown renders literally.** Pasting `## Heading` or `**bold**`
   stores `## Heading` / `**bold**` as plain text; the detail page shows the
   syntax characters because nothing converts markdown → HTML.

Both bugs trace to the same root: the current editor has no smart paste
pipeline. Configuring more CKEditor plugins would partly close the first gap
but does not solve the second, and CKEditor is the wrong substrate for a
Medium-style UX (bubble toolbar, slash menu) that the project wants anyway.

## Scope

**In scope:** Replace the `{{ form.body }}` widget — the CKEditor 5 mount on
`create_blog.html:32` and `edit_blog.html` — with a Tiptap-based body editor.

**Out of scope:** Title input, featured image upload (sidebar dropzone), slug
generation, category / tag / status form fields, Publish / Save Draft
buttons, mobile API serialisers.

## Goals

- Pasting from Word / Google Docs / Notion keeps **semantic** typography
  (headings, lists, emphasis, links) while dropping presentational styles.
- Pasting raw markdown text converts to formatted HTML.
- Editor surface looks and feels Medium-like: a floating bubble toolbar on
  text selection, a slash menu for inserting block elements.
- Existing posts (HTML stored by old CKEditor) render unchanged.
- No regression to the sanitiser pipeline, the body-search `body_plain` field,
  or the API `body` field.

## Non-goals

- Inline image upload inside the body. Body images are deferred to v2.
  Existing posts with `<img>` tags continue to render; new posts cannot add
  body images via the editor in v1.
- Auto-save drafts. Worth a separate spec.
- Embed blocks (YouTube, X, gist). Worth a separate spec and a server-side
  oEmbed / iframe-whitelist design.
- Real-time collaboration, inline comments on drafts.
- Redesign of the surrounding page layout.

## Approach

**Custom Django form widget rendering a Tiptap mount point.** The widget is
a `forms.Textarea` subclass that renders a hidden `<textarea>` (for value
serialisation) plus a `<div data-tiptap-root>` container. A first-party JS
bundle (`static/blog/tiptap.js`) initialises a Tiptap editor on every
`data-tiptap-root`, mirrors changes to the hidden textarea, and handles paste
through a smart pipeline.

Storage stays HTML. The `body` model field switches from `CKEditor5Field` to
`models.TextField(max_length=20000, blank=True)` — a metadata-only migration,
no data rewrite. The existing sanitiser (`sanitize_html` in
`blog/templatetags/sanitize.py`) continues to be the security boundary at
render time, unchanged.

### Alternatives considered

- **Template-only swap, no widget.** Rejected: forces duplication across
  `create_blog.html` and `edit_blog.html`, leaves admin on CKEditor, no
  encapsulation.
- **`django-prose-editor` (third-party Tiptap wrapper).** Rejected: their
  toolbar abstractions don't give Medium-style bubble + slash out of the box,
  and a wrapper hides the Tiptap config behind another API surface.
- **Keep CKEditor 5 and configure more plugins.** Rejected: would partly fix
  bug 1 but not bug 2, and CKEditor's balloon build doesn't reach Medium-like
  UX without significant theming work.

## File map

```
blog/
  widgets.py                       NEW   TiptapWidget(forms.Textarea) + Media
  forms.py                         EDIT  CreateBlogPostForm.Meta.widgets["body"] = TiptapWidget()
                                         UpdateBlogPostForm.Meta.widgets["body"] = TiptapWidget()
  models.py                        EDIT  body: CKEditor5Field → TextField(max_length=20000, blank=True)
  migrations/0010_*.py             NEW   AlterField on body (metadata only)
  templates/blog/widgets/
    tiptap.html                    NEW   hidden <textarea> + <div data-tiptap-root> mount

static/
  blog/tiptap.css                  NEW   typography + bubble/slash styles
  blog/tiptap.js                   BUILT esbuild output, committed, collectstatic → Spaces

blog/
  tests_tiptap.py                  NEW   widget render, form roundtrip, integration POST, sanitiser regression

src/tiptap/
  index.js                         NEW   entry point; mounts editor per [data-tiptap-root]
  slash-menu.js                    NEW   custom Tiptap suggestion extension for `/` menu
  paste.js                         NEW   smartPasteHandler + normaliseOfficeHtml + markdown detect
  __tests__/paste.test.js          NEW   vitest + jsdom branch coverage
  __tests__/normalise.test.js      NEW   golden fixtures: word/docs/notion
  __tests__/fixtures/              NEW   captured paste payloads

package.json                       EDIT  +@tiptap/core, @tiptap/starter-kit,
                                         @tiptap/extension-bubble-menu,
                                         @tiptap/extension-link, @tiptap/extension-underline,
                                         marked, esbuild, vitest, jsdom.
                                         scripts: build:editor, test:js
mysite/settings.py                 EDIT  remove CKEDITOR_5_CONFIGS, CK_EDITOR_5_UPLOAD_FILE_VIEW_NAME,
                                         "django_ckeditor_5" from INSTALLED_APPS
mysite/urls.py                     EDIT  remove path("ckeditor5/", include("django_ckeditor_5.urls"))
requirements.txt                   EDIT  remove django-ckeditor-5
```

Unchanged: `blog/templatetags/sanitize.py`, `body_plain` `pre_save` signal,
search query path, API serialisers, detail-page rendering.

## JS bundle structure

### Editor init (`src/tiptap/index.js`)

```js
import { Editor } from "@tiptap/core";
import StarterKit from "@tiptap/starter-kit";
import Underline from "@tiptap/extension-underline";
import Link from "@tiptap/extension-link";
import BubbleMenu from "@tiptap/extension-bubble-menu";
import { SlashMenu } from "./slash-menu.js";
import { smartPasteHandler } from "./paste.js";

document.querySelectorAll(".tiptap-shell").forEach((shell) => {
  const textarea = shell.querySelector("[data-tiptap-input]");
  const root     = shell.querySelector("[data-tiptap-root]");
  const bubble   = shell.querySelector("[data-bubble]");
  const mount    = shell.querySelector("[data-editor]");

  const editor = new Editor({
    element: mount,
    extensions: [
      StarterKit.configure({ heading: { levels: [2, 3] } }),
      Underline,
      Link.configure({ openOnClick: false, autolink: true }),
      BubbleMenu.configure({ element: bubble }),
      SlashMenu,
    ],
    content: textarea.value,
    editorProps: {
      handlePaste: smartPasteHandler,
      attributes: { class: "prose prose-lg max-w-none focus:outline-none" },
    },
    onUpdate: ({ editor }) => { textarea.value = editor.getHTML(); },
  });

  bubble.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-cmd]");
    if (!btn) return;
    const [cmd, arg] = btn.dataset.cmd.split(":");
    const chain = editor.chain().focus();
    if (arg) chain[cmd]({ level: Number(arg) }).run();
    else chain[cmd]().run();
  });
});
```

### Extensions

| Extension | Purpose |
|---|---|
| `@tiptap/starter-kit` | Paragraphs, h1–h6, bold, italic, strike, code, blockquote, lists, code block, horizontal rule, history, **markdown input rules** (typed `## ` → H2, `> ` → quote, `**x**` → bold) |
| `@tiptap/extension-underline` | StarterKit excludes underline |
| `@tiptap/extension-link` | URL prompt invoked from bubble; autolinks on type |
| `@tiptap/extension-bubble-menu` | Floating toolbar on selection |
| `SlashMenu` (first-party) | `/` opens insert menu for Heading 2 / Heading 3 / Quote / Code block / Divider |

### Bundle pipeline

```json
"scripts": {
  "build:css":    "npx tailwindcss -i static/src/input.css -o static/css/tailwind.min.css --minify",
  "watch:css":    "npx tailwindcss -i static/src/input.css -o static/css/tailwind.min.css --watch",
  "build:editor": "esbuild src/tiptap/index.js --bundle --minify --target=es2020 --outfile=static/blog/tiptap.js",
  "build":        "npm run build:css && npm run build:editor",
  "test:js":      "vitest run"
}
```

`build:css` is the project's existing script, kept verbatim. `build:editor`
and `build` are new.

Expected bundle size: ~80–100 KB minified, ~30 KB gzipped.

## Server-side wiring

### Widget (`blog/widgets.py`)

```python
from django import forms


class TiptapWidget(forms.Textarea):
    template_name = "blog/widgets/tiptap.html"

    class Media:
        css = {"all": ["blog/tiptap.css"]}
        js = ["blog/tiptap.js"]

    def __init__(self, attrs=None):
        default = {"hidden": True, "data-tiptap-input": ""}
        super().__init__({**default, **(attrs or {})})
```

### Widget template (`blog/templates/blog/widgets/tiptap.html`)

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
      <button type="button" data-cmd="toggleHeading:2">H2</button>
      <button type="button" data-cmd="toggleHeading:3">H3</button>
      <button type="button" data-cmd="toggleBlockquote">&ldquo;</button>
      <button type="button" data-cmd="setLink">link</button>
    </div>
    <div data-editor class="prose prose-lg max-w-none min-h-[500px]"></div>
  </div>
</div>
```

### Form (`blog/forms.py`)

```python
from blog.widgets import TiptapWidget


class CreateBlogPostForm(forms.ModelForm):
    class Meta:
        model = BlogPost
        fields = ["title", "body", "image", "category", "tags", "status"]
        widgets = {
            "tags": forms.CheckboxSelectMultiple(),
            "body": TiptapWidget(),
        }


class UpdateBlogPostForm(forms.ModelForm):
    class Meta:
        model = BlogPost
        fields = ["title", "body", "image", "category", "tags", "status"]
        widgets = {
            "tags": forms.CheckboxSelectMultiple(),
            "body": TiptapWidget(),
        }

    def save(self, commit=True):
        if not self.cleaned_data.get("image"):
            self.cleaned_data["image"] = self.instance.image
        return super().save(commit=commit)
```

`{{ form.media }}` already lives in `create_blog.html:6`; it pulls
`tiptap.css` + `tiptap.js` automatically. Templates do not change.

### Model (`blog/models.py`)

```python
class BlogPost(models.Model):
    ...
    body = models.TextField(max_length=20000, blank=True)
```

### Migration (`blog/migrations/0010_alter_blogpost_body.py`)

```python
class Migration(migrations.Migration):
    dependencies = [("blog", "0009_alter_blogpost_body")]
    operations = [
        migrations.AlterField(
            model_name="blogpost",
            name="body",
            field=models.TextField(blank=True, max_length=20000),
        ),
    ]
```

Reversible. SQLite and Postgres both treat as no-op at the column level.

### Removing CKEditor

```python
# mysite/settings.py — delete
INSTALLED_APPS = [..., "django_ckeditor_5", ...]   # remove entry
CKEDITOR_5_CONFIGS = {...}                          # remove block
CK_EDITOR_5_UPLOAD_FILE_VIEW_NAME = "..."           # remove line
```

```python
# mysite/urls.py — delete
path("ckeditor5/", include("django_ckeditor_5.urls")),
```

```
# requirements.txt — delete
django-ckeditor-5
```

Existing post HTML is vendor-neutral (`<h2>`, `<strong>`, `<blockquote>`,
`<a>`, `<img>`); CKEditor uninstall does not affect stored content. Verified
against the sanitiser's `ALLOWED_TAGS`.

## Paste handling

### Pipeline

```
clipboard event
      │
      ▼
smartPasteHandler(view, event)        Tiptap editorProps.handlePaste
      │
      ▼ inspect view.state.selection.$from.parent
      │
   in code block? → return false (paste as plain text)
      │
      ▼ inspect clipboardData
      │
   has HTML and looks like Office/Docs/Notion?
      │   yes → normaliseOfficeHtml → insert HTML → return true
      ▼
   plain text only and looks like markdown?
      │   yes → marked.parse → insert HTML → return true
      ▼
   clipboard has image files?
      │   yes → drop (v1: no inline image upload) → return true
      ▼
   else → return false (Tiptap default)
```

### Office / Docs / Notion HTML normalisation

`normaliseOfficeHtml(html)` strips `<style>`, `<meta>`, `<link>`, `<script>`,
Office namespaced tags (`o:p`, `w:*`), all `mso-*` and `data-pm-*` attributes,
all `style` attributes, all `class` attributes. Promotes `<b>` → `<strong>`,
`<i>` → `<em>`. Collapses `<font>` to its children. Keeps: `h1`-`h6`, `p`,
`strong`, `em`, `u`, `s`, `blockquote`, `ul`, `ol`, `li`, `code`, `pre`, `a`,
`img` (existing posts only), `hr`.

The normaliser is intentionally lossy: it preserves *structure* and drops
*presentation*. This matches Medium's behaviour and the server-side
sanitiser's `style`-strip rule — defence in depth, not double-work.

### Markdown detection

```js
const MARKDOWN_HINTS = /(^|\n)(#{1,6}\s|>\s|\*\s|\d+\.\s|```|---|\*\*[^*]+\*\*|__[^_]+__|\[.+\]\(.+\))/;
```

Heuristic: one match anywhere in the pasted text triggers conversion. False
positives are constrained by the in-code-block short-circuit.

### Library choice

`marked` over `markdown-it`: ~30 KB vs ~70 KB, GFM-compatible, simpler API.

### Edge cases

| Case | Behaviour |
|---|---|
| Paste inside code block | Short-circuit: `handlePaste` returns `false`, Tiptap inserts as literal text. |
| Paste of single URL | Falls through; Link extension's autolink wraps it. |
| Paste of image blob from clipboard | v1: dropped (return `true`, no-op). Document as known regression vs CKEditor. |
| Paste from another rich editor (HTML, not Office-flagged) | Falls through; Tiptap schema parser keeps what fits, drops the rest. |
| Paste containing `<script>` / `<style>` | Dropped by Tiptap schema; sanitiser also rejects on render (belt-and-braces). |
| Empty / unknown MIME paste | Falls through; Tiptap default behaviour. |

### Worked example

Google Docs paste of a styled heading + paragraph with a link:

```html
<!-- before normalise -->
<p class="c2" style="font-family:Arial;font-size:14pt">
  <span class="c5" style="font-weight:700">Headline</span>
</p>
<p class="c2 c8" style="text-align:center">
  <span class="c0">Some <a class="c9" href="https://example.com" style="color:#1155cc">link</a> here.</span>
</p>

<!-- after normalise + Tiptap schema parse + getHTML() -->
<p><strong>Headline</strong></p>
<p>Some <a href="https://example.com">link</a> here.</p>
```

That is what is stored, what the sanitiser sees, and what renders. `style`
never reaches the sanitiser, so its `style`-strip rule never has to fire on
normalised paste content.

## Security

The server-side sanitiser remains the **primary** security control. Client-
side normalisation is a UX nicety: it shapes what Tiptap stores so the
sanitiser's allowed-tag/attribute rules are not the only gate.

- `nh3.clean(...)` in `sanitize_html` runs unchanged at render time.
- `style=` attributes remain forbidden server-side (the reason documented at
  `blog/templatetags/sanitize.py:15` still applies).
- Tiptap's schema rejects unknown elements/attributes at parse time; the
  Office normaliser additionally drops `<script>`, `<style>`, namespaced tags.

A regression test asserts the sanitiser still strips `<script>` and `style=`
even when the editor writes them.

## Testing

| Layer | Tool | File | Scope |
|---|---|---|---|
| Python unit | pytest-django | `blog/tests_tiptap.py` | Widget DOM render; form value roundtrip; sanitiser regression |
| Python integration | Django test client | `blog/tests_tiptap.py` (same file) | POST body HTML → save → detail page renders sanitised |
| JS unit | vitest + jsdom | `src/tiptap/__tests__/paste.test.js` | smartPasteHandler branches |
| JS unit | vitest + jsdom | `src/tiptap/__tests__/normalise.test.js` | Office/Docs/Notion golden fixtures |
| E2E smoke | Playwright (new job) | `tests/e2e/test_editor_paste.spec.js` | One real-browser path: login → paste → publish → render |

Python tests live in `blog/tests_tiptap.py` to match the existing flat-file
convention (`blog/tests.py`, `blog/tests_api.py`) rather than introducing a
`blog/tests/` package.

### Representative assertions

```python
def test_widget_renders_hidden_textarea_and_mount():
    html = TiptapWidget().render("body", "<p>hi</p>")
    assert "<textarea" in html and "hidden" in html
    assert "data-tiptap-root" in html
    assert "<p>hi</p>" in html

def test_form_roundtrip_preserves_html(user, category):
    form = CreateBlogPostForm({
        "title": "T", "body": "<h2>X</h2><p>Y</p>",
        "category": category.id, "status": "draft",
    })
    assert form.is_valid()
    post = form.save(commit=False); post.author = user; post.save()
    assert post.body == "<h2>X</h2><p>Y</p>"

def test_detail_view_sanitises_then_renders(client, post_factory):
    post = post_factory(body='<p style="color:red">X</p><script>alert(1)</script>')
    r = client.get(post.get_absolute_url())
    assert b"<p>X</p>" in r.content
    assert b"<script>" not in r.content
    assert b"style=" not in r.content
```

```js
test("Google Docs HTML → semantic HTML, no styles", () => {
  const out = normaliseOfficeHtml(readFixture("google-docs-paste.html"));
  expect(out).toContain("<strong>");
  expect(out).not.toMatch(/style=/);
  expect(out).not.toMatch(/class="c\d+"/);
});

test("Markdown text → HTML when not in code block", () => {
  const handled = smartPasteHandler(viewOutsideCodeBlock,
    pasteEvent({ text: "## Hello\n\n**world**" }));
  expect(handled).toBe(true);
  expect(viewOutsideCodeBlock.lastInsertedHtml)
    .toBe("<h2>Hello</h2>\n<p><strong>world</strong></p>");
});

test("Markdown text inside code block → paste as plain", () => {
  const handled = smartPasteHandler(viewInsideCodeBlock,
    pasteEvent({ text: "## not a heading" }));
  expect(handled).toBe(false);
});

test("Image-only clipboard → drop, no upload", () => {
  const handled = smartPasteHandler(viewOutsideCodeBlock,
    pasteEvent({ files: [imageFile()] }));
  expect(handled).toBe(true);
  expect(viewOutsideCodeBlock.lastInsertedHtml).toBeUndefined();
});
```

### Manual checklist (PR description)

- [ ] Type a heading; toggle it back to paragraph via slash menu
- [ ] Selection bubble appears at expected position near viewport top and bottom
- [ ] `## ` at the start of a line becomes `<h2>` as you type
- [ ] Paste from Word, Google Docs, Notion, and a `.md` README — diff
      resulting HTML against fixtures
- [ ] Edit an existing post created by the old CKEditor — content loads
      identically
- [ ] Detail page renders the same way it does on production for one
      pre-existing post (visual diff vs `nyasablog.com`)
- [ ] Mobile viewport (375 px): bubble toolbar does not overflow

## Rollout

**Hard cutover.** No feature flag — authors are a small set, both editors
would mean shipping 60–100 KB of dead JS, and the change is write-side only
(existing posts render identically before and after).

Sequence:

```
1. Merge PR locally on a branch; run full Python + JS test suites.
2. npm run build  (CSS + editor bundle).
3. Commit static/blog/tiptap.js (and any updated tiptap.css).
4. Push; CI green.
5. Merge to master.
6. Deploy:
   - rsync source with --exclude=settings.ini --exclude=.env
   - pip install -r requirements.txt    (removes django-ckeditor-5)
   - python manage.py migrate           (applies 0010_alter_blogpost_body)
   - python manage.py collectstatic --noinput   (pushes bundle to Spaces)
   - chown -R ephraim:www-data .
   - systemctl restart gunicorn
7. Smoke test on prod: create a draft, paste from Google Docs, save, view,
   delete.
```

`collectstatic` is non-negotiable — without it, browsers load `tiptap.js` 404
from Spaces and the create page is broken in prod after a green deploy.

## Rollback

If the editor breaks in production:

1. Revert the merge commit on master.
2. `pip install django-ckeditor-5==<previous-version>` (recover from
   `requirements.txt` git history).
3. `python manage.py migrate blog 0009` — reverts the AlterField. Metadata
   only; no data change.
4. `python manage.py collectstatic --noinput` to restore old CKEditor assets
   to Spaces.
5. `systemctl restart gunicorn`.

Stored post HTML is unaffected by any rollback step.

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Paste handler misclassifies prose with stray `##` as markdown | Medium | Heuristic requires `##` at line start AND a second markdown signal; in-code-block short-circuit. Tune heuristic if observed. |
| Tiptap schema rejects something old CKEditor stored | Low | StarterKit schema covers everything the old toolbar produced (verified against `CKEDITOR_5_CONFIGS`). |
| `marked` adds ~30 KB even if no one pastes markdown | Low | Acceptable cost. Lazy-load `marked` if bundle size becomes a concern. |
| Admin loses CKEditor UX | Low | `TiptapWidget` is the default form widget via `Meta.widgets`; admin gets the same widget. Verify in manual checklist. |
| Inline image regression — authors who used CKEditor's body image button cannot add body images | Medium | Documented limitation; v2 will restore inline image upload pointing at the existing Spaces endpoint. Existing posts with `<img>` keep rendering. |

## Open questions

None. All scope decisions are recorded above; v2 items are listed in
non-goals.
