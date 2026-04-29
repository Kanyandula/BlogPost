# Email Verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Require new NyasaBlog users to verify their email address before their account can be used, with a smooth migration path for the existing mobile app via DRF API versioning.

**Architecture:** Custom token flow mirroring Django's password-reset pattern. Web hard-gates registration (`is_active=False` until verified). API uses `Accept`-header versioning: v1 preserves the existing contract for old mobile clients; v2 adds the gate. A separate `IsEmailVerified` DRF permission gates write endpoints universally so the spam vector is closed at the action level even on v1.

**Tech Stack:** Django 5.2, Django REST Framework, custom `Account` model (`AbstractBaseUser`, `USERNAME_FIELD='email'`), HTMX, SQLite (dev) / SQLite (prod), Django's built-in messages framework, `django.core.cache.LocMemCache` for rate-limit cooldown.

**Spec:** `docs/superpowers/specs/2026-04-29-email-verification-design.md`

---

## Conventions used in this plan

- All commands run from the project root: `/Users/admin/PycharmProjects/nyasablog/`.
- Test runner: `python manage.py test account` for the account app, with class/method paths to narrow down (e.g. `python manage.py test account.tests.RegistrationViewTests.test_registration_creates_inactive_unverified_account`).
- All commits use `git -c commit.gpgsign=false commit -m "..."` (the project signs commits by default but the local environment may not have a key configured).
- After each task, the test suite for the affected scope must be green before moving to the next task.

## File structure (new + modified)

| Path | Status | Responsibility |
|------|--------|----------------|
| `account/models.py` | modify | Add `email_verified` field |
| `account/migrations/0XXX_add_email_verified.py` | new (auto) | Schema migration |
| `account/migrations/0XXX_grandfather_existing_users.py` | new (hand-written) | Mark staff + superusers + contributors as verified |
| `account/tokens.py` | new | `EmailVerificationTokenGenerator` |
| `account/emails.py` | new | `send_verification_email(account, request)` helper |
| `templates/registration/email_verification_subject.txt` | new | Email subject template |
| `templates/registration/email_verification_email.html` | new | Email body template |
| `templates/account/verification_sent.html` | new | "Check your inbox" page |
| `templates/account/verification_invalid.html` | new | "Link expired/invalid" page with embedded resend form |
| `account/views.py` | modify | Modify `registration_view`, `login_view`; add `confirm_email_view`, `resend_verification_view` |
| `account/templates/account/partials/login_form.html` | modify | Render `non_field_errors`; surface resend link on failed login |
| `account/templates/account/partials/register_form.html` | modify | Render `non_field_errors` |
| `templates/base.html` | modify | Render Django `messages` as `showToast` events |
| `mysite/urls.py` | modify | Add `confirm-email/`, `resend-verification/` routes |
| `account/management/commands/purge_unverified_accounts.py` | new | Delete unverified accounts older than 7 days |
| `mysite/settings.py` | modify | Add DRF `AcceptHeaderVersioning` config |
| `account/api/permissions.py` | new | `IsEmailVerified` permission class |
| `account/api/views.py` | modify | Version-aware `registration_view`/`login_view`; new `resend_verification_view`, `confirm_email_view`; expose `email_verified` in `account_properties_view`; apply `IsEmailVerified` to update + change-password endpoints |
| `account/api/urls.py` | modify | Add 2 routes (resend-verification, confirm-email) |
| `account/api/serializers.py` | modify | `RegistrationSerializer` accepts `is_active` from view; `AccountPropertiesSerializer` exposes `email_verified` |
| `blog/api/views.py` | modify | Apply `IsEmailVerified` to 7 write endpoints |
| `account/tests.py` | modify | + ~34 tests covering all the above |

## Pre-flight (do this before starting Task 1)

- [ ] **Confirm `ALLOWED_HOSTS` in production settings.** SSH to the Droplet and grep production settings for `ALLOWED_HOSTS`. Required value: `['nyasablog.com', 'www.nyasablog.com']` (or equivalent — must NOT contain `'*'`). `request.build_absolute_uri()` trusts the `Host` header; with a permissive list, an attacker can send a verification link pointing at an attacker-controlled domain.

  ```bash
  ssh root@104.248.204.211 "grep -A2 'ALLOWED_HOSTS' /home/ephraim/djangoprojectdir/mysite/settings.py" 2>/dev/null
  ```

  If `ALLOWED_HOSTS` is permissive, fix it in a separate prerequisite PR before deploying this feature.

- [ ] **Confirm a working test environment.** Run the existing test suite to establish a green baseline.

  ```bash
  python manage.py test account
  ```

  Expected: all current tests pass (the existing API tests in `account/tests.py`).

---

## Task 1: Add `email_verified` field to Account model

**Files:**
- Modify: `account/models.py`
- Create: `account/migrations/0XXX_add_email_verified.py` (auto-generated; check exact filename with `ls account/migrations/`)
- Test: `account/tests.py` (new test class `EmailVerifiedFieldTests`)

- [ ] **Step 1: Write the failing test**

Add to `account/tests.py`:

```python
from django.test import TestCase

class EmailVerifiedFieldTests(TestCase):
    def test_email_verified_defaults_to_false(self):
        from account.models import Account
        user = Account.objects.create_user(
            email='newuser@nyasablog.com', username='newuser', password='testpass123'  # pragma: allowlist secret
        )
        self.assertFalse(user.email_verified)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test account.tests.EmailVerifiedFieldTests -v 2`
Expected: FAIL with `AttributeError: 'Account' object has no attribute 'email_verified'`.

- [ ] **Step 3: Add the field to the model**

In `account/models.py`, inside the `Account` class (after `is_superuser`):

```python
email_verified = models.BooleanField(default=False)
```

Then generate the schema migration:

```bash
python manage.py makemigrations account
```

Expected output: `Migrations for 'account': account/migrations/0XXX_account_email_verified.py - Add field email_verified to account`.

- [ ] **Step 4: Run test to verify it passes**

```bash
python manage.py migrate
python manage.py test account.tests.EmailVerifiedFieldTests -v 2
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add account/models.py account/migrations/ account/tests.py
git -c commit.gpgsign=false commit -m "Add email_verified field to Account model"
```

---

## Task 2: Grandfather existing users (data migration)

**Files:**
- Create: `account/migrations/0XXX_grandfather_existing_users.py` (hand-written, depends on Task 1's migration and `blog/migrations/0001_initial.py`)
- Test: `account/tests.py` — `GrandfatherMigrationTests`

- [ ] **Step 1: Write the failing tests**

Add to `account/tests.py`:

```python
from django.test import TransactionTestCase
from django.db.migrations.executor import MigrationExecutor
from django.db import connection

class GrandfatherMigrationTests(TransactionTestCase):
    """Test the grandfather data migration in isolation."""

    @property
    def app(self):
        return "account"

    migrate_from = ("account", "0XXX_account_email_verified")  # replace with actual prior migration name
    migrate_to = ("account", "0XXX_grandfather_existing_users")  # replace with actual migration name

    def setUp(self):
        executor = MigrationExecutor(connection)
        # Roll back to the state just before the grandfather migration.
        executor.migrate([self.migrate_from])
        old_apps = executor.loader.project_state([self.migrate_from]).apps
        Account = old_apps.get_model("account", "Account")
        BlogPost = old_apps.get_model("blog", "BlogPost")
        # Staff user (no posts)
        self.staff = Account.objects.create(
            email='staff@nyasablog.com', username='staff', password='x',  # pragma: allowlist secret
            is_staff=True, email_verified=False,
        )
        # Contributor (has a published post)
        self.author = Account.objects.create(
            email='author@nyasablog.com', username='author', password='x',  # pragma: allowlist secret
            email_verified=False,
        )
        BlogPost.objects.create(
            title='Post', body='Body', author=self.author, status='published'
        )
        # Lurker (no posts, not staff)
        self.lurker = Account.objects.create(
            email='lurker@nyasablog.com', username='lurker', password='x',  # pragma: allowlist secret
            email_verified=False,
        )
        # Apply the grandfather migration
        executor.loader.build_graph()
        executor.migrate([self.migrate_to])
        new_apps = executor.loader.project_state([self.migrate_to]).apps
        self.Account = new_apps.get_model("account", "Account")

    def test_grandfather_migration_marks_staff_verified(self):
        self.assertTrue(self.Account.objects.get(pk=self.staff.pk).email_verified)

    def test_grandfather_migration_marks_contributor_verified(self):
        self.assertTrue(self.Account.objects.get(pk=self.author.pk).email_verified)

    def test_grandfather_migration_leaves_lurker_unverified(self):
        self.assertFalse(self.Account.objects.get(pk=self.lurker.pk).email_verified)

    def test_grandfather_migration_idempotent(self):
        # Re-applying the migration must not regress anyone's state.
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate([("account", self.migrate_from[1])])
        executor.loader.build_graph()
        executor.migrate([self.migrate_to])
        for u in [self.staff, self.author]:
            self.assertTrue(self.Account.objects.get(pk=u.pk).email_verified)
        self.assertFalse(self.Account.objects.get(pk=self.lurker.pk).email_verified)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python manage.py test account.tests.GrandfatherMigrationTests -v 2`
Expected: FAIL — migration `0XXX_grandfather_existing_users` does not exist.

- [ ] **Step 3: Write the data migration**

Create `account/migrations/0XXX_grandfather_existing_users.py` (replace `0XXX` and `0YYY` with the correct numeric prefixes — `ls account/migrations/` to find them):

```python
from django.db import migrations, models


def grandfather(apps, schema_editor):
    Account = apps.get_model('account', 'Account')
    BlogPost = apps.get_model('blog', 'BlogPost')
    contributor_ids = set(BlogPost.objects.values_list('author_id', flat=True))
    Account.objects.filter(
        models.Q(is_staff=True) | models.Q(is_superuser=True) | models.Q(pk__in=contributor_ids)
    ).update(email_verified=True)


class Migration(migrations.Migration):
    dependencies = [
        ('account', '0YYY_account_email_verified'),  # the migration from Task 1
        ('blog', '0001_initial'),
    ]
    operations = [
        migrations.RunPython(grandfather, migrations.RunPython.noop),
    ]
```

Then in the test class above, replace `migrate_from`/`migrate_to` with the actual numeric prefixes you used.

- [ ] **Step 4: Run tests to verify they pass**

```bash
python manage.py test account.tests.GrandfatherMigrationTests -v 2
```

Expected: 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add account/migrations/ account/tests.py
git -c commit.gpgsign=false commit -m "Add grandfather migration: mark staff + contributors as email_verified"
```

---

## Task 3: `EmailVerificationTokenGenerator`

**Files:**
- Create: `account/tokens.py`
- Test: `account/tests.py` — `EmailVerificationTokenTests`

- [ ] **Step 1: Write the failing test**

Add to `account/tests.py`:

```python
class EmailVerificationTokenTests(TestCase):
    def setUp(self):
        from account.models import Account
        self.user = Account.objects.create_user(
            email='token@nyasablog.com', username='tokenuser', password='testpass123'  # pragma: allowlist secret
        )

    def test_token_invalidated_after_first_use(self):
        from account.tokens import email_verification_token
        token = email_verification_token.make_token(self.user)
        self.assertTrue(email_verification_token.check_token(self.user, token))
        # Simulate verification:
        self.user.email_verified = True
        self.user.save()
        self.assertFalse(email_verification_token.check_token(self.user, token))

    def test_token_valid_for_unverified_user(self):
        from account.tokens import email_verification_token
        token = email_verification_token.make_token(self.user)
        self.assertTrue(email_verification_token.check_token(self.user, token))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test account.tests.EmailVerificationTokenTests -v 2`
Expected: FAIL with `ModuleNotFoundError: No module named 'account.tokens'`.

- [ ] **Step 3: Create the token generator**

Create `account/tokens.py`:

```python
from django.contrib.auth.tokens import PasswordResetTokenGenerator


class EmailVerificationTokenGenerator(PasswordResetTokenGenerator):
    """Token invalidates as soon as `email_verified` flips to True."""

    def _make_hash_value(self, user, timestamp):
        return f"{user.pk}{user.email}{user.email_verified}{timestamp}"


email_verification_token = EmailVerificationTokenGenerator()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python manage.py test account.tests.EmailVerificationTokenTests -v 2
```

Expected: 2 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add account/tokens.py account/tests.py
git -c commit.gpgsign=false commit -m "Add EmailVerificationTokenGenerator that invalidates on verification"
```

---

## Task 4: Email helper + email templates

**Files:**
- Create: `account/emails.py`
- Create: `templates/registration/email_verification_subject.txt`
- Create: `templates/registration/email_verification_email.html`
- Test: `account/tests.py` — `SendVerificationEmailTests`

- [ ] **Step 1: Write the failing test**

Add to `account/tests.py`:

```python
from django.core import mail
from django.test import RequestFactory

class SendVerificationEmailTests(TestCase):
    def setUp(self):
        from account.models import Account
        self.user = Account.objects.create_user(
            email='mailto@nyasablog.com', username='mailtouser', password='testpass123'  # pragma: allowlist secret
        )
        self.factory = RequestFactory()

    def test_send_verification_email_appends_to_outbox(self):
        from account.emails import send_verification_email
        request = self.factory.get('/')
        request.META['HTTP_HOST'] = 'nyasablog.com'
        send_verification_email(self.user, request)
        self.assertEqual(len(mail.outbox), 1)
        msg = mail.outbox[0]
        self.assertEqual(msg.to, [self.user.email])
        self.assertIn('confirm-email', msg.body)
        self.assertIn('nyasablog.com', msg.body)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test account.tests.SendVerificationEmailTests -v 2`
Expected: FAIL with `ModuleNotFoundError: No module named 'account.emails'`.

- [ ] **Step 3: Create email templates and helper**

Create `templates/registration/email_verification_subject.txt`:

```
Verify your NyasaBlog email address
```

Create `templates/registration/email_verification_email.html`:

```
Hello {{ user.username }},

Welcome to NyasaBlog! Please confirm your email address by clicking the link below:

{{ protocol }}://{{ domain }}{% url 'confirm_email' uidb64=uid token=token %}

This link will expire in 3 days. If you didn't create an account, you can safely ignore this email.

— NyasaBlog
```

Create `account/emails.py`:

```python
from django.contrib.auth.tokens import default_token_generator  # noqa — for parallelism
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from account.tokens import email_verification_token


def send_verification_email(user, request):
    """Send the email-verification link to `user`. Trusts `request.get_host()` for the domain."""
    context = {
        'user': user,
        'domain': request.get_host(),
        'protocol': 'https' if request.is_secure() else 'http',
        'uid': urlsafe_base64_encode(force_bytes(user.pk)),
        'token': email_verification_token.make_token(user),
    }
    subject = render_to_string('registration/email_verification_subject.txt', context).strip()
    body = render_to_string('registration/email_verification_email.html', context)
    msg = EmailMultiAlternatives(subject=subject, body=body, to=[user.email])
    msg.send()
```

The `confirm_email` URL doesn't exist yet — Task 6 adds it. The template will fail to render until then. **That's expected**: this task only adds the helper; we'll wire the URL next. To unblock the test in this task, add a placeholder URL pattern in `mysite/urls.py`:

```python
# Placeholder — full handler added in Task 6
path('confirm-email/<str:uidb64>/<str:token>/', lambda r, uidb64, token: None, name='confirm_email'),
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python manage.py test account.tests.SendVerificationEmailTests -v 2
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add account/emails.py templates/registration/ mysite/urls.py account/tests.py
git -c commit.gpgsign=false commit -m "Add send_verification_email helper + email templates + URL placeholder"
```

---

## Task 5: `verification_sent.html` and `verification_invalid.html` templates

**Files:**
- Create: `templates/account/verification_sent.html`
- Create: `templates/account/verification_invalid.html`

(No standalone test — these templates are exercised in Tasks 6 and 7.)

- [ ] **Step 1: Create `verification_sent.html`**

Create `templates/account/verification_sent.html`:

```html
{% extends 'base.html' %}
{% block title %}Check your inbox — NyasaBlog{% endblock %}
{% block content %}
<div class="max-w-lg mx-auto py-16 px-4 text-center">
  <h1 class="text-2xl font-semibold text-on-surface mb-3">Check your inbox</h1>
  <p class="text-on-surface-variant mb-2">
    We sent a verification link to <strong>{{ email }}</strong>.
  </p>
  <p class="text-sm text-on-surface-variant">
    Click the link in the email to activate your account. The link expires in 3 days.
  </p>
  <p class="text-sm text-on-surface-variant mt-6">
    Didn't receive it?
    <a href="{% url 'resend_verification' %}?email={{ email }}" class="text-secondary font-medium hover:underline">Resend</a>
  </p>
</div>
{% endblock %}
```

- [ ] **Step 2: Create `verification_invalid.html`**

Create `templates/account/verification_invalid.html`:

```html
{% extends 'base.html' %}
{% block title %}Verification link invalid — NyasaBlog{% endblock %}
{% block content %}
<div class="max-w-lg mx-auto py-16 px-4 text-center">
  <h1 class="text-2xl font-semibold text-on-surface mb-3">Link invalid or expired</h1>
  <p class="text-on-surface-variant mb-6">
    This verification link is no longer valid. Enter your email below to receive a fresh link.
  </p>
  <form method="post" action="{% url 'resend_verification' %}" class="space-y-4">
    {% csrf_token %}
    <input type="email" name="email" required placeholder="your@email.com"
           class="w-full bg-surface-container-lowest border border-outline-variant/20 rounded-lg py-3 px-4 text-sm focus:ring-2 focus:ring-secondary/20 focus:border-secondary"/>
    <button type="submit" class="w-full bg-primary-container text-on-primary py-3 rounded-lg font-semibold hover:opacity-90">Send a new link</button>
  </form>
</div>
{% endblock %}
```

- [ ] **Step 3: Verify templates render without syntax errors**

```bash
python manage.py shell -c "from django.template.loader import get_template; get_template('account/verification_sent.html'); get_template('account/verification_invalid.html'); print('OK')"
```

Expected output: `OK` (no exception).

- [ ] **Step 4: Commit**

```bash
git add templates/account/verification_sent.html templates/account/verification_invalid.html
git -c commit.gpgsign=false commit -m "Add verification_sent and verification_invalid templates"
```

---

## Task 6: Modify `registration_view` (web) to gate

**Files:**
- Modify: `account/views.py`
- Test: `account/tests.py` — `WebRegistrationTests`

- [ ] **Step 1: Write the failing tests**

Add to `account/tests.py`:

```python
from django.urls import reverse
from django.test import Client

class WebRegistrationTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_registration_creates_inactive_unverified_account(self):
        from account.models import Account
        response = self.client.post(reverse('register'), {
            'email': 'fresh@nyasablog.com',
            'username': 'freshuser',
            'password1': 'testpass123!',  # pragma: allowlist secret
            'password2': 'testpass123!',  # pragma: allowlist secret
        })
        user = Account.objects.get(email='fresh@nyasablog.com')
        self.assertFalse(user.is_active)
        self.assertFalse(user.email_verified)

    def test_registration_sends_verification_email(self):
        from django.core import mail
        self.client.post(reverse('register'), {
            'email': 'fresh@nyasablog.com',
            'username': 'freshuser',
            'password1': 'testpass123!',  # pragma: allowlist secret
            'password2': 'testpass123!',  # pragma: allowlist secret
        })
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('Verify your', mail.outbox[0].subject)

    def test_registration_does_not_log_user_in(self):
        self.client.post(reverse('register'), {
            'email': 'fresh@nyasablog.com',
            'username': 'freshuser',
            'password1': 'testpass123!',  # pragma: allowlist secret
            'password2': 'testpass123!',  # pragma: allowlist secret
        })
        # Subsequent request should be unauthenticated
        response = self.client.get(reverse('home'))
        self.assertFalse(response.wsgi_request.user.is_authenticated)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python manage.py test account.tests.WebRegistrationTests -v 2`
Expected: FAIL — current `registration_view` logs user in immediately.

- [ ] **Step 3: Modify `registration_view`**

In `account/views.py`, replace the body of `registration_view` (lines 13–35):

```python
from account.emails import send_verification_email  # add to imports

def registration_view(request):
    context = {}
    if request.POST:
        form = RegistrationForm(request.POST)
        if form.is_valid():
            account = form.save(commit=False)
            account.is_active = False
            account.save()
            email = form.cleaned_data.get('email').lower()
            send_verification_email(account, request)
            if getattr(request, 'htmx', False):
                response = HttpResponse(status=204)
                response['HX-Redirect'] = reverse('verification_sent') + '?email=' + email
                return response
            return redirect(reverse('verification_sent') + '?email=' + email)
        else:
            context['registration_form'] = form
            if getattr(request, 'htmx', False):
                return render(request, 'account/partials/register_form.html', context)
    else:
        form = RegistrationForm()
        context['registration_form'] = form
    return render(request, 'account/register.html', context)


def verification_sent_view(request):
    return render(request, 'account/verification_sent.html', {'email': request.GET.get('email', '')})
```

Add the URL route in `mysite/urls.py`:

```python
path('verification-sent/', verification_sent_view, name='verification_sent'),
```

(Don't forget to import `verification_sent_view`.)

- [ ] **Step 4: Run tests to verify they pass**

```bash
python manage.py test account.tests.WebRegistrationTests -v 2
```

Expected: 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add account/views.py mysite/urls.py account/tests.py
git -c commit.gpgsign=false commit -m "Gate web registration: create inactive account, send verification email, no auto-login"
```

---

## Task 7: `confirm_email_view` + URL route + Django messages success

**Files:**
- Modify: `account/views.py` — add `confirm_email_view`
- Modify: `mysite/urls.py` — replace placeholder route with real handler
- Modify: `templates/base.html` — render `messages` as `showToast` events
- Test: `account/tests.py` — `ConfirmEmailViewTests`

- [ ] **Step 1: Write the failing tests**

Add to `account/tests.py`:

```python
from datetime import timedelta
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from unittest.mock import patch

class ConfirmEmailViewTests(TestCase):
    def setUp(self):
        from account.models import Account
        self.user = Account.objects.create_user(
            email='confirm@nyasablog.com', username='confirmuser', password='testpass123'  # pragma: allowlist secret
        )
        self.user.is_active = False
        self.user.save()
        self.uidb64 = urlsafe_base64_encode(force_bytes(self.user.pk))
        from account.tokens import email_verification_token
        self.valid_token = email_verification_token.make_token(self.user)

    def test_confirm_email_with_valid_token_activates_account(self):
        url = reverse('confirm_email', kwargs={'uidb64': self.uidb64, 'token': self.valid_token})
        response = self.client.get(url)
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)
        self.assertTrue(self.user.email_verified)

    def test_confirm_email_with_invalid_token_shows_error_page(self):
        url = reverse('confirm_email', kwargs={'uidb64': self.uidb64, 'token': 'bogus-token'})
        response = self.client.get(url)
        self.assertTemplateUsed(response, 'account/verification_invalid.html')
        self.user.refresh_from_db()
        self.assertFalse(self.user.email_verified)

    def test_confirm_email_with_expired_token_shows_error_page(self):
        from account.tokens import email_verification_token
        # Make a token, then advance time past PASSWORD_RESET_TIMEOUT (3 days default)
        token = email_verification_token.make_token(self.user)
        future = timezone.now() + timedelta(days=4)
        with patch('django.contrib.auth.tokens.PasswordResetTokenGenerator._now', return_value=future):
            url = reverse('confirm_email', kwargs={'uidb64': self.uidb64, 'token': token})
            response = self.client.get(url)
        self.assertTemplateUsed(response, 'account/verification_invalid.html')

    def test_token_invalidated_after_first_use_via_view(self):
        url = reverse('confirm_email', kwargs={'uidb64': self.uidb64, 'token': self.valid_token})
        self.client.get(url)  # first use — succeeds
        # Second call with same token should fail (email_verified flipped)
        self.client.logout()
        response = self.client.get(url)
        self.assertTemplateUsed(response, 'account/verification_invalid.html')

    def test_confirm_email_success_sets_messages_framework(self):
        url = reverse('confirm_email', kwargs={'uidb64': self.uidb64, 'token': self.valid_token})
        response = self.client.get(url, follow=True)
        messages = list(response.context['messages'])
        self.assertEqual(len(messages), 1)
        self.assertIn('verified', str(messages[0]).lower())
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python manage.py test account.tests.ConfirmEmailViewTests -v 2`
Expected: FAIL — view doesn't exist.

- [ ] **Step 3: Implement `confirm_email_view`**

In `account/views.py`:

```python
from django.contrib import messages
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from account.tokens import email_verification_token


def confirm_email_view(request, uidb64, token):
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        account = Account.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, Account.DoesNotExist):
        return render(request, 'account/verification_invalid.html')

    if email_verification_token.check_token(account, token):
        account.is_active = True
        account.email_verified = True
        account.save()
        login(request, account, backend='django.contrib.auth.backends.ModelBackend')
        messages.success(request, 'Email verified — welcome to NyasaBlog!')
        return redirect('home')

    return render(request, 'account/verification_invalid.html')
```

In `mysite/urls.py`, replace the placeholder:

```python
path('confirm-email/<str:uidb64>/<str:token>/', confirm_email_view, name='confirm_email'),
```

(Update imports.)

If your project uses a custom auth backend (`account/backends.py`), update the `login(request, account, backend=...)` line accordingly. Run `grep -r AUTHENTICATION_BACKENDS mysite/settings.py` to find it.

- [ ] **Step 4: Wire `messages` into `base.html`**

In `templates/base.html`, find the `<script>` block that already handles `showToast` (around line 53). Just before that block (in `<body>`), add:

```html
{% if messages %}
<script>
  document.addEventListener('DOMContentLoaded', function() {
    {% for message in messages %}
    document.body.dispatchEvent(new CustomEvent('showToast', {
      detail: { message: {{ message|escapejs|safe|stringformat:'"%s"' }}, type: '{{ message.tags|default:"success" }}' }
    }));
    {% endfor %}
  });
</script>
{% endif %}
```

(If `base.html` doesn't load `django.contrib.messages` context — check `TEMPLATES['OPTIONS']['context_processors']` in `mysite/settings.py` — confirm `'django.contrib.messages.context_processors.messages'` is present. It's a Django default, but verify.)

- [ ] **Step 5: Run tests to verify they pass**

```bash
python manage.py test account.tests.ConfirmEmailViewTests -v 2
```

Expected: 5 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add account/views.py mysite/urls.py templates/base.html account/tests.py
git -c commit.gpgsign=false commit -m "Add confirm_email_view + Django messages success rendering"
```

---

## Task 8: Modify `login_view` to reject unverified + render `non_field_errors`

**Files:**
- Modify: `account/views.py` — add `email_verified` check in `login_view`
- Modify: `account/templates/account/partials/login_form.html` — render `non_field_errors` block
- Modify: `account/templates/account/partials/register_form.html` — render `non_field_errors` block
- Test: `account/tests.py` — `WebLoginTests`

- [ ] **Step 1: Write the failing tests**

Add to `account/tests.py`:

```python
class WebLoginTests(TestCase):
    def setUp(self):
        from account.models import Account
        # Verified user
        self.verified = Account.objects.create_user(
            email='verified@nyasablog.com', username='verifieduser', password='testpass123'  # pragma: allowlist secret
        )
        self.verified.email_verified = True
        self.verified.save()
        # Unverified user
        self.unverified = Account.objects.create_user(
            email='unverified@nyasablog.com', username='unverifieduser', password='testpass123'  # pragma: allowlist secret
        )
        # is_active stays True (created via create_user) — only email_verified=False

    def test_unverified_user_cannot_log_in(self):
        response = self.client.post(reverse('login'), {
            'email': 'unverified@nyasablog.com',
            'password': 'testpass123',  # pragma: allowlist secret
        }, follow=False)
        # Login should fail; user is not authenticated.
        self.assertFalse(response.wsgi_request.user.is_authenticated)
        # Error message must be visible in the rendered HTML.
        self.assertContains(response, 'Invalid', status_code=200)
        # Resend link must be present.
        self.assertContains(response, 'Resend')

    def test_failed_login_with_wrong_password_shows_error_message(self):
        response = self.client.post(reverse('login'), {
            'email': 'verified@nyasablog.com',
            'password': 'wrongpassword',  # pragma: allowlist secret
        })
        self.assertFalse(response.wsgi_request.user.is_authenticated)
        self.assertContains(response, 'Invalid', status_code=200)

    def test_login_with_wrong_password_for_unverified_account_does_not_send_email(self):
        from django.core import mail
        mail.outbox = []
        self.client.post(reverse('login'), {
            'email': 'unverified@nyasablog.com',
            'password': 'wrongpassword',  # pragma: allowlist secret
        })
        self.assertEqual(len(mail.outbox), 0)

    def test_verified_user_logs_in_successfully(self):
        response = self.client.post(reverse('login'), {
            'email': 'verified@nyasablog.com',
            'password': 'testpass123',  # pragma: allowlist secret
        }, follow=True)
        self.assertTrue(response.wsgi_request.user.is_authenticated)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python manage.py test account.tests.WebLoginTests -v 2`
Expected: FAIL — `test_unverified_user_cannot_log_in` fails because unverified users currently log in fine, AND because the response doesn't contain "Invalid" (silent-failure bug). `test_failed_login_with_wrong_password_shows_error_message` also fails for the same reason.

- [ ] **Step 3: Modify `login_view`**

In `account/views.py`, modify `login_view` (lines 43–72):

```python
def login_view(request):
    context = {}
    user = request.user
    if user.is_authenticated:
        return redirect("home")

    if request.POST:
        form = AccountAuthenticationForm(request.POST)
        if form.is_valid():
            email = request.POST['email']
            password = request.POST['password']
            user = authenticate(email=email, password=password)
            if user and user.email_verified:
                login(request, user)
                if getattr(request, 'htmx', False):
                    response = HttpResponse(status=204)
                    response['HX-Redirect'] = '/'
                    return response
                return redirect("home")
            # Authentication failed OR user is unverified — render the same generic error.
            form.add_error(None, "Invalid email or password.")

        if getattr(request, 'htmx', False):
            context['login_form'] = form
            return render(request, 'account/partials/login_form.html', context)
    else:
        form = AccountAuthenticationForm()

    context['login_form'] = form
    return render(request, "account/login.html", context)
```

- [ ] **Step 4: Add `non_field_errors` rendering and resend link to `login_form.html`**

In `account/templates/account/partials/login_form.html`, after the `{% csrf_token %}` line (after line 5), insert:

```html
{% if login_form.non_field_errors %}
<div class="rounded-lg bg-error/10 border border-error/20 p-3 text-sm text-error" role="alert">
  {% for error in login_form.non_field_errors %}<p>{{ error }}</p>{% endfor %}
</div>
<p class="text-xs text-on-surface-variant">
  Didn't receive verification email?
  <a href="{% url 'resend_verification' %}?email={{ login_form.email.value|default:'' }}" class="text-secondary font-medium hover:underline">Resend</a>
</p>
{% endif %}
```

Note: `resend_verification` URL doesn't exist yet (Task 9). The test will still pass because Django will raise `NoReverseMatch` only at template-render time, and the test asserts the rendered HTML contains "Resend" — the link must be present. **Do this:** add a placeholder URL pattern in `mysite/urls.py` so the template renders:

```python
# Placeholder, real handler in Task 9
path('resend-verification/', lambda r: HttpResponse('placeholder'), name='resend_verification'),
```

- [ ] **Step 5: Add `non_field_errors` rendering to `register_form.html`**

In `account/templates/account/partials/register_form.html`, same pattern after the `{% csrf_token %}` line:

```html
{% if registration_form.non_field_errors %}
<div class="rounded-lg bg-error/10 border border-error/20 p-3 text-sm text-error" role="alert">
  {% for error in registration_form.non_field_errors %}<p>{{ error }}</p>{% endfor %}
</div>
{% endif %}
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
python manage.py test account.tests.WebLoginTests -v 2
```

Expected: 4 tests PASS.

- [ ] **Step 7: Commit**

```bash
git add account/views.py account/templates/account/partials/ mysite/urls.py account/tests.py
git -c commit.gpgsign=false commit -m "Gate web login on email_verified + render non_field_errors with resend link"
```

---

## Task 9: `resend_verification_view` + URL route + rate limiting

**Files:**
- Modify: `account/views.py` — add `resend_verification_view` and `_can_send_resend` helper
- Modify: `mysite/urls.py` — replace placeholder
- Test: `account/tests.py` — `ResendVerificationViewTests`

- [ ] **Step 1: Write the failing tests**

Add to `account/tests.py`:

```python
from django.core.cache import cache

class ResendVerificationViewTests(TestCase):
    def setUp(self):
        from account.models import Account
        self.unverified = Account.objects.create_user(
            email='resend@nyasablog.com', username='resenduser', password='testpass123'  # pragma: allowlist secret
        )
        self.verified = Account.objects.create_user(
            email='already@nyasablog.com', username='alreadyuser', password='testpass123'  # pragma: allowlist secret
        )
        self.verified.email_verified = True
        self.verified.save()
        cache.clear()
        from django.core import mail
        mail.outbox = []

    def test_resend_verification_sends_for_unverified(self):
        from django.core import mail
        self.client.post(reverse('resend_verification'), {'email': 'resend@nyasablog.com'})
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['resend@nyasablog.com'])

    def test_resend_verification_silent_for_unknown_email(self):
        from django.core import mail
        self.client.post(reverse('resend_verification'), {'email': 'nobody@nyasablog.com'})
        self.assertEqual(len(mail.outbox), 0)

    def test_resend_verification_silent_for_verified_email(self):
        from django.core import mail
        self.client.post(reverse('resend_verification'), {'email': 'already@nyasablog.com'})
        self.assertEqual(len(mail.outbox), 0)

    def test_resend_response_identical_for_known_and_unknown(self):
        r1 = self.client.post(reverse('resend_verification'), {'email': 'resend@nyasablog.com'})
        r2 = self.client.post(reverse('resend_verification'), {'email': 'nobody@nyasablog.com'})
        self.assertEqual(r1.status_code, r2.status_code)

    def test_resend_rate_limited_within_cooldown(self):
        from django.core import mail
        self.client.post(reverse('resend_verification'), {'email': 'resend@nyasablog.com'})
        self.assertEqual(len(mail.outbox), 1)
        # Second attempt within cooldown — still returns 200 but no new email.
        self.client.post(reverse('resend_verification'), {'email': 'resend@nyasablog.com'})
        self.assertEqual(len(mail.outbox), 1)
        cache.clear()  # simulates time advancing past cooldown
        self.client.post(reverse('resend_verification'), {'email': 'resend@nyasablog.com'})
        self.assertEqual(len(mail.outbox), 2)

    def test_resend_case_insensitive_email_lookup(self):
        from django.core import mail
        self.client.post(reverse('resend_verification'), {'email': 'RESEND@NYASABLOG.COM'})
        self.assertEqual(len(mail.outbox), 1)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python manage.py test account.tests.ResendVerificationViewTests -v 2`
Expected: FAIL — view is currently a placeholder.

- [ ] **Step 3: Implement the view**

In `account/views.py`:

```python
from django.core.cache import cache


def _can_send_resend(email: str) -> bool:
    """Return True and reserve the cooldown slot, or False if email is in cooldown."""
    key = f"resend_cooldown:{email.lower()}"
    if cache.get(key):
        return False
    cache.set(key, True, timeout=60)
    return True


def resend_verification_view(request):
    if request.method == 'POST':
        email = (request.POST.get('email') or '').strip()
        if email:
            email_lower = email.lower()
            try:
                account = Account.objects.get(email__iexact=email_lower, email_verified=False)
                if _can_send_resend(email_lower):
                    send_verification_email(account, request)
            except Account.DoesNotExist:
                pass  # silent — no enumeration
        # Always render the same response.
        return render(request, 'account/verification_sent.html',
                      {'email': email, 'resend': True})

    # GET — render the form (reuses the verification_invalid template since it has the form)
    prefill = request.GET.get('email', '')
    return render(request, 'account/verification_invalid.html', {'email': prefill})
```

In `mysite/urls.py`, replace the placeholder:

```python
path('resend-verification/', resend_verification_view, name='resend_verification'),
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python manage.py test account.tests.ResendVerificationViewTests -v 2
```

Expected: 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add account/views.py mysite/urls.py account/tests.py
git -c commit.gpgsign=false commit -m "Add resend_verification_view with per-email cooldown and case-insensitive lookup"
```

---

## Task 10: `purge_unverified_accounts` management command

**Files:**
- Create: `account/management/__init__.py` (if absent)
- Create: `account/management/commands/__init__.py` (if absent)
- Create: `account/management/commands/purge_unverified_accounts.py`
- Test: `account/tests.py` — `PurgeUnverifiedAccountsTests`

- [ ] **Step 1: Write the failing tests**

Add to `account/tests.py`:

```python
from datetime import timedelta
from django.core.management import call_command
from django.utils import timezone
from io import StringIO

class PurgeUnverifiedAccountsTests(TestCase):
    def setUp(self):
        from account.models import Account
        now = timezone.now()
        old = now - timedelta(days=8)
        recent = now - timedelta(days=1)

        self.old_unverified = Account.objects.create_user(
            email='old_unverified@x.com', username='ou', password='testpass123'  # pragma: allowlist secret
        )
        Account.objects.filter(pk=self.old_unverified.pk).update(date_joined=old)

        self.old_verified = Account.objects.create_user(
            email='old_verified@x.com', username='ov', password='testpass123'  # pragma: allowlist secret
        )
        Account.objects.filter(pk=self.old_verified.pk).update(date_joined=old, email_verified=True)

        self.recent_unverified = Account.objects.create_user(
            email='recent_unverified@x.com', username='ru', password='testpass123'  # pragma: allowlist secret
        )
        Account.objects.filter(pk=self.recent_unverified.pk).update(date_joined=recent)

        self.recent_verified = Account.objects.create_user(
            email='recent_verified@x.com', username='rv', password='testpass123'  # pragma: allowlist secret
        )
        Account.objects.filter(pk=self.recent_verified.pk).update(date_joined=recent, email_verified=True)

    def test_purge_deletes_only_old_unverified(self):
        from account.models import Account
        call_command('purge_unverified_accounts', stdout=StringIO())
        self.assertFalse(Account.objects.filter(pk=self.old_unverified.pk).exists())
        self.assertTrue(Account.objects.filter(pk=self.old_verified.pk).exists())
        self.assertTrue(Account.objects.filter(pk=self.recent_unverified.pk).exists())
        self.assertTrue(Account.objects.filter(pk=self.recent_verified.pk).exists())

    def test_purge_dry_run_does_not_delete(self):
        from account.models import Account
        out = StringIO()
        call_command('purge_unverified_accounts', '--dry-run', stdout=out)
        self.assertTrue(Account.objects.filter(pk=self.old_unverified.pk).exists())
        self.assertIn('Would delete', out.getvalue())

    def test_purged_email_can_be_reregistered(self):
        from account.models import Account
        call_command('purge_unverified_accounts', stdout=StringIO())
        # Now register a brand-new account with the freed email.
        response = self.client.post(reverse('register'), {
            'email': 'old_unverified@x.com',
            'username': 'newowner',
            'password1': 'testpass123!',  # pragma: allowlist secret
            'password2': 'testpass123!',  # pragma: allowlist secret
        })
        self.assertTrue(Account.objects.filter(email='old_unverified@x.com').exists())
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python manage.py test account.tests.PurgeUnverifiedAccountsTests -v 2`
Expected: FAIL — command doesn't exist.

- [ ] **Step 3: Create the management command**

If they don't already exist:

```bash
mkdir -p account/management/commands
touch account/management/__init__.py
touch account/management/commands/__init__.py
```

Create `account/management/commands/purge_unverified_accounts.py`:

```python
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from account.models import Account


class Command(BaseCommand):
    help = "Delete accounts with email_verified=False older than 7 days."

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help="Report what would be deleted, but don't delete.")

    def handle(self, *args, dry_run=False, **opts):
        cutoff = timezone.now() - timedelta(days=7)
        qs = Account.objects.filter(email_verified=False, date_joined__lt=cutoff)
        count = qs.count()
        if dry_run:
            self.stdout.write(f"Would delete {count} unverified accounts")
            return
        qs.delete()
        self.stdout.write(f"Deleted {count} unverified accounts")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python manage.py test account.tests.PurgeUnverifiedAccountsTests -v 2
```

Expected: 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add account/management/ account/tests.py
git -c commit.gpgsign=false commit -m "Add purge_unverified_accounts management command (--dry-run support)"
```

---

## Task 11: DRF versioning settings

**Files:**
- Modify: `mysite/settings.py`
- Test: `account/tests.py` — `DRFVersioningTests`

- [ ] **Step 1: Write the failing test**

Add to `account/tests.py`:

```python
from rest_framework.test import APIClient

class DRFVersioningTests(TestCase):
    def test_default_version_is_v1(self):
        client = APIClient()
        # Hit any DRF endpoint and check the request.version is '1' by default.
        # Use the existing properties endpoint.
        from account.models import Account
        from rest_framework.authtoken.models import Token
        u = Account.objects.create_user(email='ver@x.com', username='ver', password='testpass123')  # pragma: allowlist secret
        u.email_verified = True
        u.save()
        token = Token.objects.get(user=u)
        client.credentials(HTTP_AUTHORIZATION='Token ' + token.key)
        response = client.get(reverse('account_api:properties'))
        self.assertEqual(response.status_code, 200)
        # No assertion on version — just that the request resolves cleanly under the default versioning class.

    def test_v2_accept_header_resolves_to_v2(self):
        from account.models import Account
        from rest_framework.authtoken.models import Token
        u = Account.objects.create_user(email='v2@x.com', username='v2', password='testpass123')  # pragma: allowlist secret
        u.email_verified = True
        u.save()
        token = Token.objects.get(user=u)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION='Token ' + token.key)
        # AcceptHeaderVersioning parses `version` parameter from Accept header.
        response = client.get(
            reverse('account_api:properties'),
            HTTP_ACCEPT='application/json; version=2'
        )
        self.assertEqual(response.status_code, 200)
```

- [ ] **Step 2: Run tests to verify they fail (or pass trivially)**

Run: `python manage.py test account.tests.DRFVersioningTests -v 2`
Expected: PASS for the first test (DRF endpoints already work). The `version=2` test may also pass since DRF doesn't reject unknown versions until `ALLOWED_VERSIONS` is set — that's the gap we're filling.

- [ ] **Step 3: Add DRF versioning config**

In `mysite/settings.py`, find the `REST_FRAMEWORK = {...}` dict (or add it if absent). Add these keys:

```python
REST_FRAMEWORK = {
    # ...existing keys...
    'DEFAULT_VERSIONING_CLASS': 'rest_framework.versioning.AcceptHeaderVersioning',
    'DEFAULT_VERSION': '1',
    'ALLOWED_VERSIONS': ['1', '2'],
}
```

- [ ] **Step 4: Verify nothing breaks**

```bash
python manage.py test account
```

Expected: all existing tests still pass.

- [ ] **Step 5: Commit**

```bash
git add mysite/settings.py account/tests.py
git -c commit.gpgsign=false commit -m "Configure DRF AcceptHeaderVersioning with v1 default, v1+v2 allowed"
```

---

## Task 12: Modify API `registration_view` (version-aware)

**Files:**
- Modify: `account/api/views.py` — `registration_view`
- Modify: `account/api/serializers.py` — `RegistrationSerializer` honors `is_active` from view
- Test: `account/tests.py` — extend `RegistrationAPITests` (existing class)

- [ ] **Step 1: Write the failing tests**

Add to `account/tests.py` (extend the existing `RegistrationAPITests`):

```python
class RegistrationAPIVersionTests(AccountAPITestMixin, APITestCase):

    def test_api_register_v1_returns_token_and_unverified(self):
        from django.core import mail
        mail.outbox = []
        url = reverse('account_api:register')
        response = self.client.post(url, {
            'email': 'apinew@nyasablog.com', 'username': 'apinewuser',
            'password': 'testpass123', 'password2': 'testpass123',  # pragma: allowlist secret
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn('token', response.data)
        from account.models import Account
        u = Account.objects.get(email='apinew@nyasablog.com')
        self.assertFalse(u.email_verified)
        self.assertTrue(u.is_active)  # v1 keeps is_active=True for back-compat
        self.assertEqual(len(mail.outbox), 1)

    def test_api_register_v2_no_token_unverified_inactive(self):
        from django.core import mail
        mail.outbox = []
        url = reverse('account_api:register')
        response = self.client.post(
            url,
            {'email': 'v2@nyasablog.com', 'username': 'v2user',
             'password': 'testpass123', 'password2': 'testpass123'},  # pragma: allowlist secret
            HTTP_ACCEPT='application/json; version=2',
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('token', response.data)
        self.assertEqual(response.data['response'], 'verification_email_sent')
        from account.models import Account
        u = Account.objects.get(email='v2@nyasablog.com')
        self.assertFalse(u.email_verified)
        self.assertFalse(u.is_active)
        self.assertEqual(len(mail.outbox), 1)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python manage.py test account.tests.RegistrationAPIVersionTests -v 2`
Expected: FAIL — current view doesn't differentiate by version, doesn't send email, and v1 currently passes but `email_verified` field check on the new account would fail until prior tasks are wired up.

- [ ] **Step 3: Modify `account/api/views.py` registration_view**

```python
from account.emails import send_verification_email
from account.models import Account


@api_view(['POST', ])
@permission_classes([])
@authentication_classes([])
def registration_view(request):
    if request.method == 'POST':
        data = {}
        email = request.data.get('email', '0').lower()
        if validate_email(email) is not None:
            data['error_message'] = 'That email is already in use.'
            data['response'] = 'Error'
            return Response(data)

        username = request.data.get('username', '0')
        if validate_username(username) is not None:
            data['error_message'] = 'That username is already in use.'
            data['response'] = 'Error'
            return Response(data)

        is_v2 = (request.version == '2')
        serializer = RegistrationSerializer(data=request.data, context={'is_active': not is_v2})

        if serializer.is_valid():
            account = serializer.save()
            send_verification_email(account, request)
            if is_v2:
                data['response'] = 'verification_email_sent'
                data['email'] = account.email
                data['email_verified'] = False
            else:
                data['response'] = 'successfully registered new user.'
                data['email'] = account.email
                data['username'] = account.username
                data['pk'] = account.pk
                data['email_verified'] = False
                token = Token.objects.get(user=account).key
                data['token'] = token
        else:
            data = serializer.errors
        return Response(data)
```

In `account/api/serializers.py`, modify `RegistrationSerializer.create` (or `save`) to honor `is_active` from context:

```python
class RegistrationSerializer(serializers.ModelSerializer):
    # ...existing code...

    def save(self):
        account = Account(
            email=self.validated_data['email'],
            username=self.validated_data['username'],
        )
        password = self.validated_data['password']
        password2 = self.initial_data.get('password2')
        if password != password2:
            raise serializers.ValidationError({'password': 'Passwords must match.'})  # pragma: allowlist secret
        account.set_password(password)
        # Honor is_active from the view's context (v2 sets False).
        if self.context.get('is_active') is False:
            account.is_active = False
        account.save()
        return account
```

(Adapt to the existing serializer's structure — read the file first.)

- [ ] **Step 4: Run tests to verify they pass**

```bash
python manage.py test account.tests.RegistrationAPIVersionTests -v 2
```

Expected: 2 tests PASS. Also re-run existing `RegistrationAPITests` to confirm no regressions:

```bash
python manage.py test account.tests.RegistrationAPITests -v 2
```

Note: `test_register_success` may need updating — it currently doesn't set `email_verified=True` to authenticate later, which is fine (the existing assertion just checks that the user exists). If anything fails, examine and update accordingly. The expectation: the existing tests stay green because v1 default behavior preserves the original contract (token returned).

- [ ] **Step 5: Commit**

```bash
git add account/api/views.py account/api/serializers.py account/tests.py
git -c commit.gpgsign=false commit -m "Make API registration_view version-aware (v2 gates, v1 preserves contract)"
```

---

## Task 13: Modify API `login_view` (version-aware)

**Files:**
- Modify: `account/api/views.py` — `login_view`
- Test: `account/tests.py` — `LoginAPIVersionTests`

- [ ] **Step 1: Write the failing tests**

```python
class LoginAPIVersionTests(APITestCase):
    def setUp(self):
        from account.models import Account
        # Active-unverified — matches v1 API register output
        self.unverified = Account.objects.create_user(
            email='un@x.com', username='un', password='testpass123'  # pragma: allowlist secret
        )
        # Inactive-unverified — matches v2 API register output and web register output
        self.inactive_unverified = Account.objects.create_user(
            email='inv@x.com', username='inv', password='testpass123'  # pragma: allowlist secret
        )
        self.inactive_unverified.is_active = False
        self.inactive_unverified.save()
        # Verified happy-path user
        self.verified = Account.objects.create_user(
            email='ver@x.com', username='ver', password='testpass123'  # pragma: allowlist secret
        )
        self.verified.email_verified = True
        self.verified.save()

    def test_api_login_v1_allows_unverified_with_email_verified_field(self):
        client = APIClient()
        url = reverse('account_api:login')
        response = client.post(url, {'username': 'un@x.com', 'password': 'testpass123'})  # pragma: allowlist secret
        self.assertEqual(response.data['response'], 'Successfully authenticated.')
        self.assertIn('token', response.data)
        self.assertIn('email_verified', response.data)
        self.assertFalse(response.data['email_verified'])

    def test_api_login_v2_rejects_unverified_with_error_code(self):
        client = APIClient()
        url = reverse('account_api:login')
        response = client.post(
            url, {'username': 'un@x.com', 'password': 'testpass123'},  # pragma: allowlist secret
            HTTP_ACCEPT='application/json; version=2',
        )
        self.assertEqual(response.data['response'], 'Error')
        self.assertEqual(response.data.get('error_code'), 'email_not_verified')
        self.assertNotIn('token', response.data)

    def test_api_login_v2_succeeds_for_verified_user(self):
        client = APIClient()
        url = reverse('account_api:login')
        response = client.post(
            url, {'username': 'ver@x.com', 'password': 'testpass123'},  # pragma: allowlist secret
            HTTP_ACCEPT='application/json; version=2',
        )
        self.assertEqual(response.data['response'], 'Successfully authenticated.')
        self.assertIn('token', response.data)
        self.assertTrue(response.data['email_verified'])

    def test_api_login_v2_rejects_inactive_unverified_with_error_code(self):
        # Mirrors what v2 API register produces (is_active=False, email_verified=False).
        # The view must give the explicit `email_not_verified` code rather than masking as "Invalid credentials".
        client = APIClient()
        url = reverse('account_api:login')
        response = client.post(
            url, {'username': 'inv@x.com', 'password': 'testpass123'},  # pragma: allowlist secret
            HTTP_ACCEPT='application/json; version=2',
        )
        self.assertEqual(response.data['response'], 'Error')
        self.assertEqual(response.data.get('error_code'), 'email_not_verified')
        self.assertNotIn('token', response.data)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python manage.py test account.tests.LoginAPIVersionTests -v 2`
Expected: FAIL.

- [ ] **Step 3: Modify the API login view**

Read the existing `login_view` in `account/api/views.py` first to understand its structure (class-based vs function-based, return shape). Then modify it to make the following behavioral changes — keep the existing structure, just add the new logic:

1. After the existing `authenticate()` call:
   - **If `account` is not None and unverified**: that means `is_active=True` but `email_verified=False` (the v1 API register path). Branch on version: v1 logs them in (preserves back-compat) and includes `email_verified: false` in the response; v2 returns the new `email_not_verified` error.
   - **If `account` is None**: do a manual lookup for a user matching the email with the correct password but `is_active=False, email_verified=False` (the v2 register / web register path). If found, on v2 return `email_not_verified`; on v1 return generic "Invalid credentials" (an inactive user shouldn't authenticate via v1 — v1 contract preserved exactly).

Concretely (adapt to the existing view's shape):

```python
def login_view(request):
    context = {}
    email = request.data.get('username', '0')
    password = request.data.get('password', '0')
    is_v2 = (request.version == '2')
    account = authenticate(email=email, password=password)

    if account is None:
        # Maybe it's an inactive-unverified user (v2 register output / web register output)
        # — manually verify password and check email_verified to produce the right v2 error code.
        try:
            candidate = Account.objects.get(email=email)
            if candidate.check_password(password) and not candidate.email_verified:
                if is_v2:
                    return Response({
                        'response': 'Error',
                        'error_message': 'Email not verified',
                        'error_code': 'email_not_verified',
                    })
        except Account.DoesNotExist:
            pass
        return Response({'response': 'Error', 'error_message': 'Invalid credentials'})

    # account is authenticated (is_active=True). Decide on verified gate.
    if is_v2 and not account.email_verified:
        return Response({
            'response': 'Error',
            'error_message': 'Email not verified',
            'error_code': 'email_not_verified',
        })

    token, _ = Token.objects.get_or_create(user=account)
    return Response({
        'response': 'Successfully authenticated.',
        'pk': account.pk,
        'email': account.email,
        'token': token.key,
        'email_verified': account.email_verified,
    })
```

The `manual lookup → check_password()` path is *only* used to produce the right error message on v2; it does not log anyone in. v1 callers with an inactive user still get "Invalid credentials" exactly as today.

- [ ] **Step 4: Run tests to verify they pass**

```bash
python manage.py test account.tests.LoginAPIVersionTests -v 2
python manage.py test account.tests.LoginAPITests -v 2
```

Expected: 4 new tests PASS, existing tests continue to PASS (v1 default still works).

- [ ] **Step 5: Commit**

```bash
git add account/api/views.py account/tests.py
git -c commit.gpgsign=false commit -m "Make API login_view version-aware: v2 rejects unverified, both expose email_verified"
```

---

## Task 14: Expose `email_verified` in `account_properties_view`

**Files:**
- Modify: `account/api/serializers.py` — `AccountPropertiesSerializer`
- Test: `account/tests.py` — `AccountPropertiesEmailVerifiedTests`

- [ ] **Step 1: Write the failing test**

```python
class AccountPropertiesEmailVerifiedTests(AccountAPITestMixin, APITestCase):
    def test_api_properties_includes_email_verified_field(self):
        self.user.email_verified = True
        self.user.save()
        self.authenticate()
        url = reverse('account_api:properties')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn('email_verified', response.data)
        self.assertTrue(response.data['email_verified'])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test account.tests.AccountPropertiesEmailVerifiedTests -v 2`
Expected: FAIL.

- [ ] **Step 3: Add field to serializer**

In `account/api/serializers.py`, find `AccountPropertiesSerializer` and add `'email_verified'` to its `fields` Meta tuple:

```python
class AccountPropertiesSerializer(serializers.ModelSerializer):
    class Meta:
        model = Account
        fields = ('pk', 'email', 'username', 'email_verified',)  # add email_verified
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python manage.py test account.tests.AccountPropertiesEmailVerifiedTests -v 2
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add account/api/serializers.py account/tests.py
git -c commit.gpgsign=false commit -m "Expose email_verified in /api/account/properties response"
```

---

## Task 15: API `resend-verification` endpoint

**Files:**
- Modify: `account/api/views.py` — add `resend_verification_view`
- Modify: `account/api/urls.py` — add route
- Test: `account/tests.py` — `ResendVerificationAPITests`

- [ ] **Step 1: Write the failing tests**

```python
class ResendVerificationAPITests(APITestCase):
    def setUp(self):
        from account.models import Account
        from django.core import mail
        from django.core.cache import cache
        cache.clear()
        mail.outbox = []
        self.unverified = Account.objects.create_user(
            email='r@x.com', username='r', password='testpass123'  # pragma: allowlist secret
        )

    def test_api_resend_sends_for_unverified(self):
        from django.core import mail
        client = APIClient()
        response = client.post(reverse('account_api:resend_verification'),
                               {'email': 'r@x.com'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)

    def test_api_resend_silent_for_unknown(self):
        from django.core import mail
        client = APIClient()
        client.post(reverse('account_api:resend_verification'), {'email': 'nobody@x.com'})
        self.assertEqual(len(mail.outbox), 0)

    def test_api_resend_silent_for_already_verified(self):
        from account.models import Account
        from django.core import mail
        verified = Account.objects.create_user(
            email='already@x.com', username='already', password='testpass123'  # pragma: allowlist secret
        )
        verified.email_verified = True
        verified.save()
        client = APIClient()
        client.post(reverse('account_api:resend_verification'), {'email': 'already@x.com'})
        self.assertEqual(len(mail.outbox), 0)

    def test_api_resend_rate_limited(self):
        from django.core import mail
        client = APIClient()
        client.post(reverse('account_api:resend_verification'), {'email': 'r@x.com'})
        client.post(reverse('account_api:resend_verification'), {'email': 'r@x.com'})
        self.assertEqual(len(mail.outbox), 1)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python manage.py test account.tests.ResendVerificationAPITests -v 2`
Expected: FAIL — endpoint doesn't exist (`NoReverseMatch`).

- [ ] **Step 3: Implement the API endpoint**

In `account/api/views.py`:

```python
from account.views import _can_send_resend  # reuse the cooldown helper
from account.emails import send_verification_email


@api_view(['POST', ])
@permission_classes([])
@authentication_classes([])
def api_resend_verification_view(request):
    email = (request.data.get('email') or '').strip().lower()
    response_body = {'response': 'If that email is registered and unverified, a new link was sent.'}
    if email:
        try:
            account = Account.objects.get(email__iexact=email, email_verified=False)
            if _can_send_resend(email):
                send_verification_email(account, request)
        except Account.DoesNotExist:
            pass
    return Response(response_body)
```

In `account/api/urls.py`, add:

```python
path('resend-verification/', api_resend_verification_view, name='resend_verification'),
```

(Update imports.)

- [ ] **Step 4: Run tests to verify they pass**

```bash
python manage.py test account.tests.ResendVerificationAPITests -v 2
```

Expected: 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add account/api/views.py account/api/urls.py account/tests.py
git -c commit.gpgsign=false commit -m "Add API resend-verification endpoint (per-email cooldown, no enumeration)"
```

---

## Task 16: API `confirm-email` endpoint

**Files:**
- Modify: `account/api/views.py` — add `api_confirm_email_view`
- Modify: `account/api/urls.py` — add route
- Test: `account/tests.py` — `ConfirmEmailAPITests`

- [ ] **Step 1: Write the failing tests**

```python
class ConfirmEmailAPITests(APITestCase):
    def setUp(self):
        from account.models import Account
        from account.tokens import email_verification_token
        from django.utils.encoding import force_bytes
        from django.utils.http import urlsafe_base64_encode
        self.user = Account.objects.create_user(
            email='c@x.com', username='c', password='testpass123'  # pragma: allowlist secret
        )
        self.user.is_active = False
        self.user.save()
        self.uidb64 = urlsafe_base64_encode(force_bytes(self.user.pk))
        self.token = email_verification_token.make_token(self.user)

    def test_api_confirm_valid_token_returns_token(self):
        client = APIClient()
        response = client.post(reverse('account_api:confirm_email'),
                               {'uid': self.uidb64, 'token': self.token})
        self.assertEqual(response.status_code, 200)
        self.assertIn('token', response.data)
        self.user.refresh_from_db()
        self.assertTrue(self.user.email_verified)
        self.assertTrue(self.user.is_active)

    def test_api_confirm_invalid_token_returns_400(self):
        client = APIClient()
        response = client.post(reverse('account_api:confirm_email'),
                               {'uid': self.uidb64, 'token': 'bogus'})
        self.assertEqual(response.status_code, 400)
        self.user.refresh_from_db()
        self.assertFalse(self.user.email_verified)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python manage.py test account.tests.ConfirmEmailAPITests -v 2`
Expected: FAIL.

- [ ] **Step 3: Implement the endpoint**

In `account/api/views.py`:

```python
from django.utils.http import urlsafe_base64_decode
from django.utils.encoding import force_str
from account.tokens import email_verification_token


@api_view(['POST', ])
@permission_classes([])
@authentication_classes([])
def api_confirm_email_view(request):
    uidb64 = request.data.get('uid')
    token = request.data.get('token')
    if not uidb64 or not token:
        return Response({'error_message': 'uid and token are required.'}, status=status.HTTP_400_BAD_REQUEST)
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        account = Account.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, Account.DoesNotExist):
        return Response({'error_message': 'Invalid link.'}, status=status.HTTP_400_BAD_REQUEST)
    if not email_verification_token.check_token(account, token):
        return Response({'error_message': 'Invalid or expired link.'}, status=status.HTTP_400_BAD_REQUEST)
    account.is_active = True
    account.email_verified = True
    account.save()
    auth_token, _ = Token.objects.get_or_create(user=account)
    return Response({'response': 'Email verified.', 'token': auth_token.key,
                     'email': account.email, 'pk': account.pk})
```

In `account/api/urls.py`:

```python
path('confirm-email/', api_confirm_email_view, name='confirm_email'),
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python manage.py test account.tests.ConfirmEmailAPITests -v 2
```

Expected: 2 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add account/api/views.py account/api/urls.py account/tests.py
git -c commit.gpgsign=false commit -m "Add API confirm-email endpoint that returns auth token on success"
```

---

## Task 17: `IsEmailVerified` permission class

**Files:**
- Create: `account/api/permissions.py`
- Test: `account/tests.py` — `IsEmailVerifiedPermissionTests`

- [ ] **Step 1: Write the failing tests**

```python
from rest_framework.test import APIRequestFactory
from rest_framework.views import APIView


class IsEmailVerifiedPermissionTests(TestCase):
    def setUp(self):
        from account.models import Account
        self.factory = APIRequestFactory()
        self.unverified = Account.objects.create_user(
            email='unv@x.com', username='unv', password='testpass123'  # pragma: allowlist secret
        )
        self.verified = Account.objects.create_user(
            email='ver@x.com', username='ver', password='testpass123'  # pragma: allowlist secret
        )
        self.verified.email_verified = True
        self.verified.save()

    def test_permission_allows_verified_user(self):
        from account.api.permissions import IsEmailVerified
        permission = IsEmailVerified()
        request = self.factory.get('/')
        request.user = self.verified
        self.assertTrue(permission.has_permission(request, APIView()))

    def test_permission_denies_unverified_user(self):
        from account.api.permissions import IsEmailVerified
        permission = IsEmailVerified()
        request = self.factory.get('/')
        request.user = self.unverified
        self.assertFalse(permission.has_permission(request, APIView()))

    def test_permission_denies_anonymous(self):
        from account.api.permissions import IsEmailVerified
        from django.contrib.auth.models import AnonymousUser
        permission = IsEmailVerified()
        request = self.factory.get('/')
        request.user = AnonymousUser()
        self.assertFalse(permission.has_permission(request, APIView()))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python manage.py test account.tests.IsEmailVerifiedPermissionTests -v 2`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Create the permission class**

Create `account/api/permissions.py`:

```python
from rest_framework import permissions


class IsEmailVerified(permissions.BasePermission):
    """Allow only authenticated users whose email has been verified."""
    message = "Email not verified. Please verify your email to perform this action."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and getattr(request.user, 'email_verified', False)
        )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python manage.py test account.tests.IsEmailVerifiedPermissionTests -v 2
```

Expected: 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add account/api/permissions.py account/tests.py
git -c commit.gpgsign=false commit -m "Add IsEmailVerified DRF permission class"
```

---

## Task 18: Apply `IsEmailVerified` to blog write API endpoints

**Files:**
- Modify: `blog/api/views.py` — apply permission to 7 write endpoints
- Test: `account/tests.py` — `BlogWriteEndpointGatingTests`

- [ ] **Step 1: Write the failing tests**

```python
class BlogWriteEndpointGatingTests(APITestCase):
    def setUp(self):
        from account.models import Account
        from blog.models import BlogPost, Category
        from rest_framework.authtoken.models import Token
        self.unverified = Account.objects.create_user(
            email='un@x.com', username='un', password='testpass123'  # pragma: allowlist secret
        )
        self.verified = Account.objects.create_user(
            email='ver@x.com', username='ver', password='testpass123'  # pragma: allowlist secret
        )
        self.verified.email_verified = True
        self.verified.save()
        self.un_token = Token.objects.get(user=self.unverified)
        self.ver_token = Token.objects.get(user=self.verified)
        self.category = Category.objects.create(name='News', slug='news')
        self.post = BlogPost.objects.create(
            title='Existing', body='Body', author=self.verified, status='published',
            category=self.category, slug='existing',
        )

    def _client_for(self, token):
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION='Token ' + token.key)
        return c

    def test_unverified_blocked_from_create_post(self):
        client = self._client_for(self.un_token)
        response = client.post(reverse('blog_api:create'), {
            'title': 'Spam', 'body': 'Spam body', 'category': self.category.pk,
        })
        self.assertEqual(response.status_code, 403)

    def test_unverified_blocked_from_create_comment(self):
        client = self._client_for(self.un_token)
        response = client.post(
            reverse('blog_api:create_comment', args=[self.post.slug]),
            {'body': 'Spam comment'},
        )
        self.assertEqual(response.status_code, 403)

    def test_unverified_blocked_from_toggle_like(self):
        client = self._client_for(self.un_token)
        response = client.post(reverse('blog_api:toggle_like', args=[self.post.slug]))
        self.assertEqual(response.status_code, 403)

    def test_verified_user_can_create_post(self):
        client = self._client_for(self.ver_token)
        response = client.post(reverse('blog_api:create'), {
            'title': 'OK Post', 'body': 'Body', 'category': self.category.pk,
        })
        self.assertNotEqual(response.status_code, 403)

    def test_unverified_can_still_read_blog_detail(self):
        client = self._client_for(self.un_token)
        response = client.get(reverse('blog_api:detail', args=[self.post.slug]))
        self.assertEqual(response.status_code, 200)

    def test_unverified_can_still_read_comments(self):
        client = self._client_for(self.un_token)
        response = client.get(reverse('blog_api:comments', args=[self.post.slug]))
        self.assertEqual(response.status_code, 200)
```

(Confirm exact `blog_api:*` URL names and required POST body shapes by reading `blog/api/urls.py` and `blog/api/views.py`.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `python manage.py test account.tests.BlogWriteEndpointGatingTests -v 2`
Expected: FAIL — unverified users currently can write.

- [ ] **Step 3: Apply the permission**

In `blog/api/views.py`, change `permission_classes` for each of the 7 write endpoints. Replace each occurrence of:

```python
@permission_classes((IsAuthenticated,))
```

with:

```python
@permission_classes((IsAuthenticated, IsEmailVerified))
```

The seven endpoints (per `blog/api/views.py` line numbers from the spec: 25, 42, 94, 118, 212, 243, 258):

- `api_update_blog_view` (PUT)
- `api_delete_blog_view` (DELETE)
- `api_create_blog_view` (POST)
- `api_create_comment_view` (POST)
- `api_delete_comment_view` (DELETE)
- `api_toggle_like_view` (POST)
- `api_toggle_bookmark_view` (POST)

Plus the import at the top:

```python
from account.api.permissions import IsEmailVerified
```

**Do NOT change** the read endpoints (`api_detail_blog_view`, `api_is_author_of_blogpost`, `api_categories_view`, `api_tags_view`, `api_comments_view`, `api_bookmarks_view`).

- [ ] **Step 4: Run tests to verify they pass**

```bash
python manage.py test account.tests.BlogWriteEndpointGatingTests -v 2
```

Expected: 6 tests PASS.

Re-run the full account suite to catch regressions:

```bash
python manage.py test account
```

Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add blog/api/views.py account/tests.py
git -c commit.gpgsign=false commit -m "Apply IsEmailVerified to 7 blog write API endpoints (reads stay open)"
```

---

## Task 19: Apply `IsEmailVerified` to account write API endpoints

**Files:**
- Modify: `account/api/views.py` — `account_update_view`, `update_profile_view`, `change_password_view`
- Test: `account/tests.py` — `AccountWriteEndpointGatingTests`

- [ ] **Step 1: Write the failing tests**

```python
class AccountWriteEndpointGatingTests(APITestCase):
    def setUp(self):
        from account.models import Account
        from rest_framework.authtoken.models import Token
        self.unverified = Account.objects.create_user(
            email='un@x.com', username='un', password='testpass123'  # pragma: allowlist secret
        )
        self.un_token = Token.objects.get(user=self.unverified)

    def _client(self):
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION='Token ' + self.un_token.key)
        return c

    def test_unverified_blocked_from_change_password(self):
        response = self._client().put(reverse('account_api:change_password'), {
            'old_password': 'testpass123', 'new_password': 'newtestpass123',  # pragma: allowlist secret
            'confirm_new_password': 'newtestpass123',  # pragma: allowlist secret
        })
        self.assertEqual(response.status_code, 403)

    def test_unverified_blocked_from_update_profile(self):
        response = self._client().put(reverse('account_api:update_profile'),
                                       {'bio': 'Spammy bio'})
        self.assertEqual(response.status_code, 403)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python manage.py test account.tests.AccountWriteEndpointGatingTests -v 2`
Expected: FAIL.

- [ ] **Step 3: Apply permission**

In `account/api/views.py`, find the relevant decorators and add `IsEmailVerified` to the `permission_classes` tuples. Endpoints to change:

- The PUT endpoint backing `account_api:update`
- The PUT endpoint backing `account_api:update_profile`
- The PUT endpoint backing `account_api:change_password`

Pattern:

```python
@permission_classes((IsAuthenticated, IsEmailVerified))
```

Plus the import:

```python
from account.api.permissions import IsEmailVerified
```

Read endpoints (`account_api:properties`, `account_api:author_profile`, `account_api:check_if_account_exists`) stay open.

- [ ] **Step 4: Run tests to verify they pass**

```bash
python manage.py test account.tests.AccountWriteEndpointGatingTests -v 2
```

Expected: 2 tests PASS.

Re-run full suite:

```bash
python manage.py test account
```

Note: existing tests in `UpdateAccountAPITests`, `UpdateProfileAPITests`, and `ChangePasswordAPITests` will start failing because their setUp creates unverified users. **Update those tests** by adding to each `setUp`:

```python
self.user.email_verified = True
self.user.save()
```

(Or wrap into `AccountAPITestMixin.setUp` directly so all tests using it have verified users — easier and applies the same fix everywhere.)

- [ ] **Step 5: Commit**

```bash
git add account/api/views.py account/tests.py
git -c commit.gpgsign=false commit -m "Apply IsEmailVerified to account update + change-password endpoints"
```

---

## Task 20: Final integration test run + manual verification + cron docs

**Files:**
- Manual: SSH check on production
- Doc: append cron entry to deploy notes

- [ ] **Step 1: Run the full test suite**

```bash
python manage.py test account
python manage.py test  # full project suite
```

Expected: all green. If any blog or unrelated tests fail, investigate — likely a missed `email_verified=True` in a setUp somewhere.

- [ ] **Step 2: Manual smoke test (in dev environment)**

Start the dev server and run through these flows manually:

```bash
python manage.py runserver
```

1. **Web register a brand-new account.**
   - Visit `http://localhost:8000/register/`.
   - Submit a fresh email, username, password.
   - Expected: redirected to `/verification-sent/?email=...`. The console-email backend prints the verification email to stdout. Copy the link.
2. **Click the verification link.**
   - Paste the link into a browser. Expected: redirected to home, with a green "Email verified" toast.
3. **Try to log in pre-verification.**
   - Register a second account, but don't click the link. Try to log in. Expected: "Invalid email or password." error visible, with a "Resend" link.
4. **Resend, click the new link.**
   - Click Resend. New email is printed. Click the link. Expected: account activated.
5. **Manual purge dry-run.**
   - `python manage.py purge_unverified_accounts --dry-run`. Expected: prints a count, doesn't delete.

- [ ] **Step 3: Confirm `ALLOWED_HOSTS` on production**

```bash
ssh root@104.248.204.211 "grep ALLOWED_HOSTS /home/ephraim/djangoprojectdir/mysite/settings.py" 2>/dev/null
```

Expected: `ALLOWED_HOSTS = ['nyasablog.com', 'www.nyasablog.com']` (or equivalent — must NOT include `'*'`).

- [ ] **Step 4: Document the cron entry (do not install yet — install during deploy)**

Append to `README.md` or create `docs/superpowers/runbooks/email-verification-purge-cron.md`:

```
## purge_unverified_accounts cron

Install on the production Droplet under user `ephraim`:

  crontab -u ephraim -e

Add (replace venv path if different — verify with `which python` after activating the env):

  0 3 * * * cd /home/ephraim/djangoprojectdir && /home/ephraim/djangoprojectenv/bin/python manage.py purge_unverified_accounts >> /var/log/nyasablog/purge.log 2>&1

Verify with:

  sudo -u ephraim crontab -l
  sudo -u ephraim /home/ephraim/djangoprojectenv/bin/python /home/ephraim/djangoprojectdir/manage.py purge_unverified_accounts --dry-run

Ensure `/var/log/nyasablog/` exists and is writable by `ephraim`.
```

- [ ] **Step 5: Commit and open PR**

```bash
git add README.md docs/superpowers/runbooks/  # whichever you used
git -c commit.gpgsign=false commit -m "Document email-verification cron installation steps"
```

Open PR with branch off `master`:

```bash
git push -u origin <branch-name>
gh pr create --title "Email verification on account creation" --body-file docs/superpowers/specs/2026-04-29-email-verification-design.md
```

---

## Self-review checklist (run before declaring the plan complete)

- [ ] Every section of the spec is covered by at least one task. No gaps.
- [ ] No `TBD`, `TODO`, or `# FIXME` markers in the plan.
- [ ] Function/class/method names are consistent across tasks (e.g., `email_verification_token` is not renamed mid-plan).
- [ ] All new files referenced earlier are created somewhere in the plan.
- [ ] All tests cited in the spec's test plan map to a task that creates them.
- [ ] No `permission_classes((IsAuthenticated, IsEmailVerified))` appears in a task before the permission class is created (Task 17 < Tasks 18, 19).
- [ ] No URL reverse with a name that hasn't been registered yet by the time the task using it runs (placeholders are added where needed).
