# Password visibility toggle on auth forms — design

- **Ticket:** NB-1 (Notion: NyasaBlog Tickets)
- **Date:** 2026-05-16
- **Type:** Improvement · Priority P3 · Effort S
- **Constraint:** Template-only. No backend, form, or model changes.

## Problem

Every NyasaBlog auth password field renders a plain `<input type="password">`
with no way to reveal what was typed. On mobile, where mistyping is common,
users cannot verify a password before submitting.

## Goal

Add an accessible show/hide toggle to every password input across the four
auth surfaces, masked by default on every load, with no persistence and no
exposure of the password value beyond a client-side DOM attribute flip.

## Affected surfaces

| Surface | Template | Password fields |
| --- | --- | --- |
| Login | `account/templates/account/partials/login_form.html` | password (1, loop-rendered) |
| Register | `account/templates/account/partials/register_form.html` | password + confirm (loop-rendered) |
| Change password | `templates/registration/password_change.html` | old / new / confirm (3, hardcoded) |
| Reset confirm | `templates/registration/password_reset_confirm.html` | new / confirm (**template does not exist yet**) |

### Reset-confirm scope note

`mysite/urls.py:101` wires `PasswordResetConfirmView.as_view()` with **no
`template_name`**, so the "set a new password" page currently renders Django
admin's unstyled `registration/password_reset_confirm.html` fallback (off-brand,
no `base.html`). `TEMPLATES.DIRS` lists the project `templates/` dir ahead of
`APP_DIRS`, so creating `templates/registration/password_reset_confirm.html`
overrides the admin fallback with **no `urls.py` change**. Per ticket owner
decision (2026-05-16), NB-1 includes building this branded page, modelled on
`password_change.html`. This remains template-only.

## Decisions (resolved, not open)

1. **Icon set:** Material Symbols (`visibility` / `visibility_off`), not
   Bootstrap Icons. Already loaded in `base.html`; `password_change.html` and
   `design_reference/` mockups use it. Overrides the ticket's "Bootstrap Icons
   or inline SVG" suggestion for project consistency.
2. **Toggle markup:** Lifted verbatim from `design_reference/login_mobile.html`
   — an absolutely-positioned `type="button"` inside a `relative` wrapper, with
   `pr-12` on the input to reserve space.
3. **Shared mechanism (approach A1):** one markup include + one delegated
   script, rather than pure-JS injection (A2, risks the no-height-shift AC and
   is fragile across HTMX swaps) or per-template duplication (A3, violates DRY).
4. **No-JS behaviour:** the button renders as static markup and is inert
   without JS. The password stays masked and the form stays fully functional —
   the toggle is a progressive enhancement, not required for the core flow.

## Architecture

### New files

**`templates/snippets/password_toggle.html`** — button markup only:

```html
<button type="button" data-pw-toggle aria-label="Show password"
        class="absolute right-3 top-1/2 -translate-y-1/2 w-10 h-10 flex items-center justify-center text-outline hover:text-primary transition-colors">
  <span class="material-symbols-outlined">visibility</span>
</button>
```

**`templates/snippets/password_toggle_js.html`** — one `<script>`, a single
`document.body`-delegated `click` listener for `[data-pw-toggle]`:

- Resolve the target input as the `<input>` within the button's closest
  `[data-pw-wrapper]` element (no IDs — robust for loop-rendered and
  hardcoded markup). The wrapper carries both `class="relative"` (presentation:
  positioning context for the absolute button) and the `data-pw-wrapper`
  attribute (the explicit behavioral contract the script keys off). Keying
  off the `data-` attribute rather than the `.relative` utility class keeps
  behavior decoupled from presentation, so a later layout change can't break
  the toggle silently.
- Flip `input.type` between `password` and `text`.
- Swap the icon text `visibility` ↔ `visibility_off`.
- Swap `aria-label` "Show password" ↔ "Hide password".
- Idempotent: a `window`-scoped guard (e.g. `window.__pwToggleBound`) gates
  listener attachment, so re-running the script when an HTMX partial
  re-renders never double-binds (a block-scoped flag would not survive
  re-inclusion). Delegation on `document.body` (the idiom `base.html` already
  uses for toasts/CSRF) means the handler survives `hx-swap` form replacement
  with zero re-init.

**`templates/registration/password_reset_confirm.html`** — new branded page,
structurally a copy of `password_change.html`'s card/heading pattern (extends
`base.html`), rendering `form.new_password1` and `form.new_password2`, the
`form.errors` / validlink handling Django's `PasswordResetConfirmView` expects,
each password input wrapped with the toggle, and the JS snippet included once.

### Edited files

**`login_form.html` / `register_form.html`** — inside the existing
`{% for field in ... %}` loop, branch:

```django
{% if field.field.widget.input_type == 'password' %}
  <div class="relative">
    <input type="password" name="{{ field.name }}" ...
           class="<existing classes> pr-12"/>
    {% include 'snippets/password_toggle.html' %}
  </div>
{% else %}
  <input ... />   {# existing markup, unchanged #}
{% endif %}
```

Error rendering and the `<label>` stay as-is. Append
`{% include 'snippets/password_toggle_js.html' %}` once at the end of each
partial (safe under HTMX re-render — script is idempotent).

**`password_change.html`** — wrap each of the 3 hardcoded inputs in
`<div class="relative">`, add `pr-12` to the input class, insert the toggle
include, and add the JS snippet include once.

## Acceptance criteria mapping

- Toggle on every password input (4 surfaces) → include rendered at each.
- Click flips mask/visible + icon updates → delegated handler.
- Masked default, no persistence → server always renders `type="password"`;
  state lives only in transient DOM, never stored/transmitted.
- Keyboard reachable, Enter/Space → native `<button>`, free.
- `aria-label` updates Show/Hide → handler swaps it.
- `type="button"` → never submits.
- Mobile ≥320px, no height shift → absolute overlay button +
  `-translate-y-1/2`; `pr-12` only reserves horizontal space.
- Nothing logged/stored/transmitted → pure client attribute flip.

## Testing

Project discipline is TDD; tests written first, then implementation.

**Django test client (automated):**

- `login`, `register`, `password_change`, and a generated
  `reset/<uidb64>/<token>/` each render a `data-pw-toggle` button with
  `type="button"` and an `aria-label`.
- Password inputs on each page carry the `relative` wrapper and `pr-12`.
- Non-password fields (e.g. login email) are NOT wrapped / get no toggle.
- `password_reset_confirm` uses the branded template: `assertTemplateUsed`
  for `registration/password_reset_confirm.html` **and** `assertContains`
  for a `base.html` marker (e.g. the site header), proving the admin
  fallback is gone.
- Existing `blog/tests.py::test_password_reset_loads` still passes.

**Manual (no JS runner in suite):** in-browser at ≥320px width — confirm
type flip, icon swap, `aria-label` swap, Enter/Space activation, no field
height shift, and that toggling does not submit the form. Verify the
HTMX-swapped login/register partials still toggle after a failed submit.

## Build / deploy constraint

Tailwind is **compiled, not CDN** (`CLAUDE.md`). The new utility classes
(`pr-12` on password inputs and the toggle button's positioning utilities)
must be compiled into the built stylesheet via `npm run build:css`, and in
production the rebuilt CSS must reach DO Spaces via `collectstatic` — a
template/`rsync`-only change ships an unstyled toggle otherwise. `data-pw-*`
are attributes, not classes, so they need no CSS. This is an implementation
step (plan Task 5), recorded here so the constraint isn't lost.

## Out of scope

Password strength meter; "remember password" UI; biometric/autofill changes;
any backend/form/model change.
