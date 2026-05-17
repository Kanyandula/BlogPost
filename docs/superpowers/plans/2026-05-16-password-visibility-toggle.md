# Password Visibility Toggle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an accessible show/hide toggle to every password input on NyasaBlog's four auth surfaces (login, register, password change, password reset confirm), template-only.

**Architecture:** One shared markup include (`snippets/password_toggle.html`) + one shared `document.body`-delegated script (`snippets/password_toggle_js.html`, idempotent via a `window` guard so it survives HTMX form swaps). Each password input is wrapped in a `relative` div with `pr-12`; login/register branch inside their existing Django field loop on `field.field.widget.input_type == 'password'`; `password_reset_confirm.html` is created as a branded page (it does not exist today — the view falls back to Django admin's unstyled template).

**Tech Stack:** Django 5.2 templates, Tailwind utility classes (project design tokens), Material Symbols icon font (already loaded in `base.html`), vanilla JS. Tests: Django test runner (`python manage.py test`).

**Spec:** `docs/superpowers/specs/2026-05-16-password-visibility-toggle-design.md`

**Conventions observed:**
- `account/tests.py` uses **4-space** indentation — match it.
- Templates use **2-space** indentation — match it.
- Run all test/manage commands with the venv interpreter: **`.venv/bin/python manage.py ...`** (every `python manage.py` below means `.venv/bin/python manage.py`).
- CI runs `python manage.py test blog account personal` + `ruff check .`. New tests go in `account/tests.py`. Keep the test class lint-clean (no unused imports — F401/I001 fail CI).
- User model: `account.models.Account`, `create_user(email, username, password)`, `email_verified` flag, `USERNAME_FIELD='email'`.
- **Tailwind is compiled, not CDN** (`CLAUDE.md`). New utility classes (`pr-12`, the toggle button's positioning classes) only take effect in the built CSS after `npm run build:css`. The `data-pw-wrapper` attribute and Django logic work without it, but the feature renders unstyled until the CSS is rebuilt — see Task 5.

---

### Task 1: Login toggle — create shared snippets + wire login form

**Files:**
- Create: `templates/snippets/password_toggle.html`
- Create: `templates/snippets/password_toggle_js.html`
- Modify: `account/templates/account/partials/login_form.html`
- Test: `account/tests.py` (append new class; add one import)

- [ ] **Step 1: Write the failing tests**

Do NOT add any new import in this task. `TestCase`, `reverse`, and `Account` are already imported at the top of `account/tests.py`. (`default_token_generator` is added later, in Task 4, where it is first used — adding it here would be an unused import and fail `ruff` F401/I001.)

Append this class to the end of `account/tests.py` (4-space indentation):

```python
class PasswordToggleTests(TestCase):
    def setUp(self):
        self.user = Account.objects.create_user(
            email='toggle@nyasablog.com', username='toggleuser',
            password='Str0ngPass!9',  # pragma: allowlist secret
        )
        self.user.email_verified = True
        self.user.save()

    def test_login_page_has_exactly_one_password_toggle(self):
        resp = self.client.get(reverse('login'))
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        # Count the rendered toggle button by its aria-label attribute.
        # NOT `data-pw-toggle`: that literal also appears inside the
        # delegated script's `closest('[data-pw-toggle]')` selector, so
        # counting it would double-count. The JS sets the label via
        # setAttribute with bare 'Show password' (no `aria-label="`
        # prefix), so this token only matches rendered markup.
        self.assertEqual(body.count('aria-label="Show password"'), 1)
        self.assertIn('data-pw-toggle', body)
        self.assertIn('type="button"', body)

    def test_login_htmx_partial_swap_has_toggle_and_script(self):
        # Failed credentials with the HX-Request header make login_view
        # return the swapped-in partial (account/partials/login_form.html),
        # not the full page. This is the path where the script's
        # window.__pwToggleBound guard matters, so assert the toggle AND
        # the script are present in the fragment. (If django-htmx is not
        # active the full page is returned instead — the assertions still
        # hold, since the page includes the same partial.)
        resp = self.client.post(
            reverse('login'),
            {'email': 'toggle@nyasablog.com', 'password': 'wrong-password'},  # pragma: allowlist secret
            HTTP_HX_REQUEST='true',
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertEqual(body.count('aria-label="Show password"'), 1)
        self.assertIn('__pwToggleBound', body)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ~/PycharmProjects/nyasablog && .venv/bin/python manage.py test account.tests.PasswordToggleTests -v 2`
Expected: FAIL — both tests fail (no toggle markup / no script in the rendered login page or partial yet).

- [ ] **Step 3: Create the shared snippets**

Create `templates/snippets/password_toggle.html` (2-space indentation):

```html
<button type="button" data-pw-toggle aria-label="Show password"
        class="absolute right-3 top-1/2 -translate-y-1/2 w-10 h-10 flex items-center justify-center text-outline hover:text-primary transition-colors">
  <span class="material-symbols-outlined">visibility</span>
</button>
```

Create `templates/snippets/password_toggle_js.html`:

```html
<script>
(function () {
  if (window.__pwToggleBound) return;
  window.__pwToggleBound = true;
  document.body.addEventListener('click', function (e) {
    var btn = e.target.closest('[data-pw-toggle]');
    if (!btn) return;
    var wrapper = btn.closest('[data-pw-wrapper]');
    if (!wrapper) return;
    var input = wrapper.querySelector('input');
    if (!input) return;
    var reveal = input.type === 'password';
    input.type = reveal ? 'text' : 'password';
    btn.setAttribute('aria-label', reveal ? 'Hide password' : 'Show password');
    var icon = btn.querySelector('.material-symbols-outlined');
    if (icon) icon.textContent = reveal ? 'visibility_off' : 'visibility';
  });
})();
</script>
```

- [ ] **Step 4: Wire the login form partial**

In `account/templates/account/partials/login_form.html`, replace the entire field loop block. The CURRENT block is:

```django
  {% for field in login_form %}
  <div>
    <label class="block text-sm font-medium text-on-surface mb-1">{{ field.label }}</label>
    <input type="{{ field.field.widget.input_type|default:'text' }}"
           name="{{ field.name }}"
           value="{{ field.value|default:'' }}"
           placeholder="{{ field.label }}"
           class="w-full bg-surface-container-lowest border border-outline-variant/20 rounded-lg py-3 px-4 text-sm focus:ring-2 focus:ring-secondary/20 focus:border-secondary"/>
    {% for error in field.errors %}
    <p class="text-xs text-error mt-1">{{ error }}</p>
    {% endfor %}
  </div>
  {% endfor %}
```

Replace it with:

```django
  {% for field in login_form %}
  <div>
    <label class="block text-sm font-medium text-on-surface mb-1">{{ field.label }}</label>
    {% if field.field.widget.input_type == 'password' %}
    <div class="relative" data-pw-wrapper>
      <input type="password"
             name="{{ field.name }}"
             value="{{ field.value|default:'' }}"
             placeholder="{{ field.label }}"
             class="w-full bg-surface-container-lowest border border-outline-variant/20 rounded-lg py-3 px-4 pr-12 text-sm focus:ring-2 focus:ring-secondary/20 focus:border-secondary"/>
      {% include 'snippets/password_toggle.html' %}
    </div>
    {% else %}
    <input type="{{ field.field.widget.input_type|default:'text' }}"
           name="{{ field.name }}"
           value="{{ field.value|default:'' }}"
           placeholder="{{ field.label }}"
           class="w-full bg-surface-container-lowest border border-outline-variant/20 rounded-lg py-3 px-4 text-sm focus:ring-2 focus:ring-secondary/20 focus:border-secondary"/>
    {% endif %}
    {% for error in field.errors %}
    <p class="text-xs text-error mt-1">{{ error }}</p>
    {% endfor %}
  </div>
  {% endfor %}
```

The `data-pw-wrapper` attribute is the explicit contract the script keys off
(`btn.closest('[data-pw-wrapper]')`). It must be on the same `div` as
`class="relative"` (the `relative` class still provides the positioning
context for the absolutely-placed button). Do not key the script off the
`.relative` class — that couples behavior to a presentation utility and
fails silently if the layout changes.

Then add the script include as the LAST line of the file, after the closing `</form>`:

```django
{% include 'snippets/password_toggle_js.html' %}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd ~/PycharmProjects/nyasablog && .venv/bin/python manage.py test account.tests.PasswordToggleTests -v 2`
Expected: PASS (2 tests OK).

- [ ] **Step 6: Commit**

```bash
cd ~/PycharmProjects/nyasablog
git add templates/snippets/password_toggle.html templates/snippets/password_toggle_js.html account/templates/account/partials/login_form.html account/tests.py
git commit -m "feat: password visibility toggle on login form

Shared toggle include + delegated script; login password field
wrapped with the toggle. NB-1."
```

---

### Task 2: Register form toggle

**Files:**
- Modify: `account/templates/account/partials/register_form.html`
- Test: `account/tests.py` (add method to `PasswordToggleTests`)

- [ ] **Step 1: Write the failing test**

Add this method to `PasswordToggleTests` in `account/tests.py`:

```python
    def test_register_page_has_two_password_toggles(self):
        resp = self.client.get(reverse('register'))
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        # RegistrationForm exposes password1 + password2. Count by
        # aria-label (markup-only token), not `data-pw-toggle` which
        # also appears in the delegated script's selector.
        self.assertEqual(body.count('aria-label="Show password"'), 2)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/PycharmProjects/nyasablog && python manage.py test account.tests.PasswordToggleTests.test_register_page_has_two_password_toggles -v 2`
Expected: FAIL — `0 != 2`.

- [ ] **Step 3: Wire the register form partial**

In `account/templates/account/partials/register_form.html`, replace the CURRENT field loop block:

```django
  {% for field in registration_form %}
  <div>
    <label class="block text-sm font-medium text-on-surface mb-1">{{ field.label }}</label>
    <input type="{{ field.field.widget.input_type|default:'text' }}"
           name="{{ field.name }}"
           value="{{ field.value|default:'' }}"
           placeholder="{{ field.label }}"
           class="w-full bg-surface-container-lowest border border-outline-variant/20 rounded-lg py-3 px-4 text-sm focus:ring-2 focus:ring-secondary/20 focus:border-secondary"/>
    {% for error in field.errors %}
    <p class="text-xs text-error mt-1">{{ error }}</p>
    {% endfor %}
  </div>
  {% endfor %}
```

with:

```django
  {% for field in registration_form %}
  <div>
    <label class="block text-sm font-medium text-on-surface mb-1">{{ field.label }}</label>
    {% if field.field.widget.input_type == 'password' %}
    <div class="relative" data-pw-wrapper>
      <input type="password"
             name="{{ field.name }}"
             value="{{ field.value|default:'' }}"
             placeholder="{{ field.label }}"
             class="w-full bg-surface-container-lowest border border-outline-variant/20 rounded-lg py-3 px-4 pr-12 text-sm focus:ring-2 focus:ring-secondary/20 focus:border-secondary"/>
      {% include 'snippets/password_toggle.html' %}
    </div>
    {% else %}
    <input type="{{ field.field.widget.input_type|default:'text' }}"
           name="{{ field.name }}"
           value="{{ field.value|default:'' }}"
           placeholder="{{ field.label }}"
           class="w-full bg-surface-container-lowest border border-outline-variant/20 rounded-lg py-3 px-4 text-sm focus:ring-2 focus:ring-secondary/20 focus:border-secondary"/>
    {% endif %}
    {% for error in field.errors %}
    <p class="text-xs text-error mt-1">{{ error }}</p>
    {% endfor %}
  </div>
  {% endfor %}
```

Then add as the LAST line of the file, after the closing `</form>`:

```django
{% include 'snippets/password_toggle_js.html' %}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/PycharmProjects/nyasablog && python manage.py test account.tests.PasswordToggleTests.test_register_page_has_two_password_toggles -v 2`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd ~/PycharmProjects/nyasablog
git add account/templates/account/partials/register_form.html account/tests.py
git commit -m "feat: password visibility toggle on register form

Both password fields wrapped with the shared toggle. NB-1."
```

---

### Task 3: Password change toggle

**Files:**
- Modify: `templates/registration/password_change.html`
- Test: `account/tests.py` (add method to `PasswordToggleTests`)

- [ ] **Step 1: Write the failing test**

Add this method to `PasswordToggleTests`:

```python
    def test_password_change_page_has_three_toggles(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse('password_change'))
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        # Count by aria-label (markup-only token), not `data-pw-toggle`.
        self.assertEqual(body.count('aria-label="Show password"'), 3)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/PycharmProjects/nyasablog && python manage.py test account.tests.PasswordToggleTests.test_password_change_page_has_three_toggles -v 2`
Expected: FAIL — `0 != 3`.

- [ ] **Step 3: Wire the password change template**

In `templates/registration/password_change.html`, replace the three field `<div>` blocks. The CURRENT markup is:

```django
      <div>
        <label class="block text-sm font-medium text-on-surface mb-1">Current password</label>
        <input name="old_password" type="password" required
               class="w-full bg-surface-container-lowest border border-outline-variant/20 rounded-lg py-3 px-4 text-sm focus:ring-2 focus:ring-secondary/20 focus:border-secondary"/>
      </div>
      <div>
        <label class="block text-sm font-medium text-on-surface mb-1">New password</label>
        <input name="new_password1" type="password" required
               class="w-full bg-surface-container-lowest border border-outline-variant/20 rounded-lg py-3 px-4 text-sm focus:ring-2 focus:ring-secondary/20 focus:border-secondary"/>
      </div>
      <div>
        <label class="block text-sm font-medium text-on-surface mb-1">Confirm new password</label>
        <input name="new_password2" type="password" required
               class="w-full bg-surface-container-lowest border border-outline-variant/20 rounded-lg py-3 px-4 text-sm focus:ring-2 focus:ring-secondary/20 focus:border-secondary"/>
      </div>
```

Replace with:

```django
      <div>
        <label class="block text-sm font-medium text-on-surface mb-1">Current password</label>
        <div class="relative" data-pw-wrapper>
          <input name="old_password" type="password" required
                 class="w-full bg-surface-container-lowest border border-outline-variant/20 rounded-lg py-3 px-4 pr-12 text-sm focus:ring-2 focus:ring-secondary/20 focus:border-secondary"/>
          {% include 'snippets/password_toggle.html' %}
        </div>
      </div>
      <div>
        <label class="block text-sm font-medium text-on-surface mb-1">New password</label>
        <div class="relative" data-pw-wrapper>
          <input name="new_password1" type="password" required
                 class="w-full bg-surface-container-lowest border border-outline-variant/20 rounded-lg py-3 px-4 pr-12 text-sm focus:ring-2 focus:ring-secondary/20 focus:border-secondary"/>
          {% include 'snippets/password_toggle.html' %}
        </div>
      </div>
      <div>
        <label class="block text-sm font-medium text-on-surface mb-1">Confirm new password</label>
        <div class="relative" data-pw-wrapper>
          <input name="new_password2" type="password" required
                 class="w-full bg-surface-container-lowest border border-outline-variant/20 rounded-lg py-3 px-4 pr-12 text-sm focus:ring-2 focus:ring-secondary/20 focus:border-secondary"/>
          {% include 'snippets/password_toggle.html' %}
        </div>
      </div>
```

(Each password input is in its own `<div class="relative" data-pw-wrapper>` —
`data-pw-wrapper` is the contract the shared script uses to find the input;
`relative` provides positioning for the absolute button.)

Then add the script include just before the `{% endblock content %}` line at the bottom of the file:

```django
{% include 'snippets/password_toggle_js.html' %}
{% endblock content %}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/PycharmProjects/nyasablog && python manage.py test account.tests.PasswordToggleTests.test_password_change_page_has_three_toggles -v 2`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd ~/PycharmProjects/nyasablog
git add templates/registration/password_change.html account/tests.py
git commit -m "feat: password visibility toggle on change-password form

All three password fields wrapped with the shared toggle. NB-1."
```

---

### Task 4: Branded password_reset_confirm page with toggle

**Files:**
- Create: `templates/registration/password_reset_confirm.html`
- Test: `account/tests.py` (add method to `PasswordToggleTests`)

Context: `mysite/urls.py:101` wires `PasswordResetConfirmView.as_view()` with no `template_name`; `TEMPLATES.DIRS` lists `templates/` before `APP_DIRS`, so creating this file overrides the Django-admin fallback with no `urls.py` change. The view redirects a valid `reset/<uidb64>/<token>/` link (302) to a session URL that renders this template with `validlink=True` and `form` (`SetPasswordForm`: `new_password1`, `new_password2`).

- [ ] **Step 1: Write the failing test**

First add the `default_token_generator` import. It must be **isort-ordered**: `django.contrib` sorts after `django.conf` and before `django.core`. Insert it immediately after the `from django.conf import settings` line (and before `from django.core ...`):

```python
from django.contrib.auth.tokens import default_token_generator
```

`urlsafe_base64_encode` (`django.utils.http`) and `force_bytes` (`django.utils.encoding`) are already imported at the top of `account/tests.py`. After adding the import, run `ruff check account/tests.py` and confirm zero errors (no F401 — it is now used by the test below; no I001 — it is correctly sorted).

Add this method to `PasswordToggleTests`:

```python
    def test_password_reset_confirm_is_branded_with_two_toggles(self):
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = default_token_generator.make_token(self.user)
        resp = self.client.get(
            reverse('password_reset_confirm', kwargs={'uidb64': uid, 'token': token}),
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'registration/password_reset_confirm.html')
        body = resp.content.decode()
        # Branded: extends base.html, so the site name is present (admin
        # fallback would not contain it).
        self.assertIn('NyasaBlog', body)
        # Count by aria-label (markup-only token), not `data-pw-toggle`.
        self.assertEqual(body.count('aria-label="Show password"'), 2)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/PycharmProjects/nyasablog && python manage.py test account.tests.PasswordToggleTests.test_password_reset_confirm_is_branded_with_two_toggles -v 2`
Expected: FAIL — currently renders Django admin's template: `assertTemplateUsed` fails, or `'NyasaBlog'` / `data-pw-toggle` count assertion fails.

- [ ] **Step 3: Create the branded template**

Create `templates/registration/password_reset_confirm.html` (2-space indentation), modelled on `password_change.html`:

```django
{% extends 'base.html' %}

{% block title %}Set New Password | NyasaBlog{% endblock %}

{% block content %}
<div class="min-h-[60vh] flex items-center justify-center px-6">
  <div class="w-full max-w-md bg-surface-container-lowest rounded-xl p-8 md:p-10">
    <div class="text-center mb-6">
      <span class="material-symbols-outlined text-4xl text-primary mb-2">lock_reset</span>
      <h1 class="text-2xl font-bold text-primary">Set a new password</h1>
    </div>

    {% if validlink %}
    <form method="POST" class="space-y-4">
      {% csrf_token %}
      <div>
        <label class="block text-sm font-medium text-on-surface mb-1">New password</label>
        <div class="relative" data-pw-wrapper>
          <input name="new_password1" type="password" required
                 class="w-full bg-surface-container-lowest border border-outline-variant/20 rounded-lg py-3 px-4 pr-12 text-sm focus:ring-2 focus:ring-secondary/20 focus:border-secondary"/>
          {% include 'snippets/password_toggle.html' %}
        </div>
      </div>
      <div>
        <label class="block text-sm font-medium text-on-surface mb-1">Confirm new password</label>
        <div class="relative" data-pw-wrapper>
          <input name="new_password2" type="password" required
                 class="w-full bg-surface-container-lowest border border-outline-variant/20 rounded-lg py-3 px-4 pr-12 text-sm focus:ring-2 focus:ring-secondary/20 focus:border-secondary"/>
          {% include 'snippets/password_toggle.html' %}
        </div>
      </div>

      {% for field in form %}
        {% for error in field.errors %}
        <p class="text-xs text-error">{{ error }}</p>
        {% endfor %}
      {% endfor %}

      <button type="submit" class="w-full bg-primary-container text-on-primary py-3 rounded-lg font-semibold hover:opacity-90 transition-opacity">Set Password</button>
    </form>
    {% else %}
    <p class="text-sm text-on-surface-variant text-center">
      This password reset link is invalid or has expired. Please
      <a href="{% url 'password_reset' %}" class="text-secondary font-medium hover:underline">request a new one</a>.
    </p>
    {% endif %}

    {% include 'snippets/password_toggle_js.html' %}
  </div>
</div>
{% endblock content %}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/PycharmProjects/nyasablog && python manage.py test account.tests.PasswordToggleTests.test_password_reset_confirm_is_branded_with_two_toggles -v 2`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd ~/PycharmProjects/nyasablog
git add templates/registration/password_reset_confirm.html account/tests.py
git commit -m "feat: branded password_reset_confirm page with toggle

Replaces the Django-admin fallback with a base.html-styled page;
both new-password fields wrapped with the shared toggle. NB-1."
```

---

### Task 5: Full-suite regression, lint, and manual verification

**Files:** none modified (verification only; commit any lint fix if needed)

- [ ] **Step 1: Run the full account + blog suite**

Run: `cd ~/PycharmProjects/nyasablog && .venv/bin/python manage.py test account blog -v 1`
Expected: all tests pass, including the pre-existing `blog.tests.test_password_reset_loads` and the 5 new `PasswordToggleTests` (login ×1, login-HTMX-partial ×1, register, password-change, reset-confirm). Baseline before this branch was 251 passing. If `test_password_reset_loads` or any auth test fails, stop and investigate before proceeding.

- [ ] **Step 2: Lint (must be CI-clean)**

Run: `cd ~/PycharmProjects/nyasablog && ruff check .`
Expected: the lint job passes with no NEW findings attributable to this branch. In particular `account/tests.py` must have zero F401 (unused import) and zero I001 (import order) — the `default_token_generator` import is added in Task 4 where it is used and must be isort-ordered (after `django.conf`, before `django.core`). Templates are not linted. If ruff reports a NEW issue from this branch, fix it and re-run; do not "fix" pre-existing repo findings unrelated to this change.

- [ ] **Step 3: Rebuild the compiled Tailwind CSS**

The new utility classes (`pr-12` on password inputs, the toggle button's `absolute right-3 top-1/2 -translate-y-1/2 w-10 h-10 ...`) only exist in the production stylesheet after a rebuild — Tailwind is compiled, not CDN (`CLAUDE.md`). `data-pw-wrapper` is an attribute, not a class, so it needs no CSS.

Run: `cd ~/PycharmProjects/nyasablog && npm run build:css`
Then `git status` — if `static/css/tailwind.min.css` (or the project's built CSS output) changed, stage and commit it:

```bash
git add static/css/tailwind.min.css
git commit -m "chore: rebuild Tailwind CSS for password toggle classes

NB-1 adds pr-12 and the toggle button positioning utilities; compile
them into the built stylesheet so the feature is styled in prod."
```

If `npm run build:css` is unavailable in this environment, STOP and report it — note explicitly that the CSS rebuild + `collectstatic` to DO Spaces is a required deploy step for this feature (per `CLAUDE.md`), so a reviewer/deployer does not ship an unstyled toggle.

- [ ] **Step 4: Manual in-browser verification**

Run the dev server: `cd ~/PycharmProjects/nyasablog && .venv/bin/python manage.py runserver` and, at a viewport width of 320px and a normal desktop width, verify on `/login/`, `/register/`, `/password_change/` (logged in), and a live password-reset-confirm link:

- Clicking the eye icon flips the field between dots and plaintext; icon swaps `visibility` ↔ `visibility_off`.
- Tabbing reaches the button; Enter and Space both toggle it.
- `aria-label` flips between "Show password" and "Hide password" (inspect element / screen reader).
- The button does NOT submit the form.
- Field height does not change when toggled; layout holds at 320px.
- On `/login/` and `/register/`, submit with a bad value to force the HTMX partial re-render, then confirm the toggle still works on the swapped-in form (delegated handler survives the swap).
- Reload each page: every field is masked again (no persisted visible state).

Document the outcome of each check in the task notes. There is no JS test runner in the suite, so this manual pass is the verification of record for the JS behavior.

- [ ] **Step 5: Final commit (only if Step 2 produced a lint fix)**

If Step 2 required editing `account/tests.py` to clear a NEW ruff finding:

```bash
cd ~/PycharmProjects/nyasablog
git add account/tests.py
git commit -m "chore: lint fixes for password toggle tests"
```

If Step 2 was clean, skip — no empty commit. (The CSS commit, if any, was already made in Step 3.)

---

## Self-Review

**Spec coverage:**
- Toggle on all 4 surfaces → Tasks 1 (login), 2 (register), 3 (change), 4 (reset confirm). ✓
- Shared markup include + single delegated script (A1) → created in Task 1, reused thereafter. ✓
- Branded `password_reset_confirm.html` overriding admin fallback, no `urls.py` change → Task 4. ✓
- Material Symbols `visibility`/`visibility_off` → in `password_toggle.html` + JS swap. ✓
- Masked default / no persistence → server always renders `type="password"`; state only in transient DOM (verified Step 3, Task 5). ✓
- `type="button"`, keyboard reachable, `aria-label` flip → asserted in Task 1 test + manual Task 5. ✓
- No height shift at ≥320px → absolute overlay + `pr-12`; manual Task 5. ✓
- Nothing logged/stored/transmitted → pure client attribute flip; no backend touched. ✓
- `window`-scoped idempotency guard, HTMX-swap safe → `password_toggle_js.html` + `test_login_htmx_partial_swap_has_toggle_and_script` (Task 1) + manual swap check Task 5. ✓
- Compiled-Tailwind constraint (`pr-12` etc. need a CSS rebuild for prod) → Task 5 Step 3 (`npm run build:css`). ✓
- Existing `test_password_reset_loads` still green → Task 5 Step 1. ✓

**Placeholder scan:** No TBD/TODO/"handle edge cases"/uncoded steps. Every code step shows complete, runnable code; every command step shows the exact command and expected output. ✓

**Type/name consistency:** `data-pw-toggle` (button marker), `data-pw-wrapper` (wrapper marker the script keys off — NOT the `.relative` class), `relative` + `pr-12` (presentation only), `window.__pwToggleBound`, icon text `visibility`/`visibility_off`, `aria-label` "Show password"/"Hide password", class `PasswordToggleTests`, and `snippets/password_toggle.html` / `snippets/password_toggle_js.html` paths are identical across every task. The `default_token_generator` import is introduced once, in Task 4, isort-ordered. ✓

**Test-token note (correction):** Toggle-count assertions count `aria-label="Show password"`, NOT `data-pw-toggle`. The `data-pw-toggle` literal also appears inside the delegated script's `closest('[data-pw-toggle]')` selector, so counting it double-counts. The JS sets the label via `setAttribute('aria-label', ... 'Show password')` — bare string, no `aria-label="` prefix — so the chosen token matches only rendered button markup. The JS keeps the clean spec selector `closest('[data-pw-toggle]')`; do NOT split that string as a test workaround.
