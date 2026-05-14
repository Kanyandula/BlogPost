# Postmark via django-anymail — Migration Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Gmail SMTP with Postmark (via `django-anymail`) for all production transactional email so verification + password-reset mail sends from `admin@nyasablog.com` with the DKIM/SPF/Return-Path/DMARC alignment configured on 2026-05-13.

**Why now:** Production currently sends from `khayamalawi@gmail.com` via `smtp.gmail.com`. None of the nyasablog.com email-auth records configured 2026-05-13 (DKIM `20260513155127pm._domainkey`, Return-Path `pm-bounces`, DMARC `_dmarc`) are doing anything until the `From:` address actually claims `@nyasablog.com` and sends through Postmark. This plan makes that switch.

**Approach:** Drop-in `EMAIL_BACKEND` change. The existing `send_verification_email()` helper in `account/emails.py` uses Django's stock `EmailMessage` API, which `django-anymail` is fully drop-in compatible with. Behavior of the verification flow is unchanged; only the transport changes.

**Why django-anymail and not raw SMTP relay:** Bounce/complaint webhooks, tags for the Postmark dashboard, structured error reporting, ESP-portability. Comparison and decision rationale in `docs/superpowers/runbooks/email-deliverability-followup.md` (or inline below).

**Tech stack:** Django 5.2, `django-anymail[postmark]` (new dep), Postmark transactional stream, `python-decouple` for env.

---

## Conventions used in this plan

- All commands from project root: `/Users/admin/PycharmProjects/nyasablog/`.
- Test runner: `python manage.py test account`. Narrow with class/method paths (e.g. `python manage.py test account.tests.PostmarkBackendTests.test_verification_email_uses_anymail_backend`).
- All commits use `git -c commit.gpgsign=false commit -m "..."` (project signs by default, local env may not).
- After each task, affected tests must be green before moving to the next.
- Production Postmark server token is **distinct** from the dev/local token already in Keychain. Generate a separate token for prod.

## File structure (new + modified)

| Path | Status | Responsibility |
|------|--------|----------------|
| `requirements.txt` | modify | Pin `django-anymail[postmark]==<version>` |
| `.pip-audit-ignore` | possibly modify | Add ignores only if anymail surfaces CVEs (unlikely) |
| `mysite/settings.py` | modify | Switch `EMAIL_BACKEND`, add `ANYMAIL` dict, read `POSTMARK_SERVER_TOKEN` from env |
| `account/emails.py` | modify | Add `tags=['email-verification']` and `metadata={'user_id': str(user.pk)}` to `EmailMessage` (Anymail-native fields, passed through to Postmark) |
| `account/tests.py` | modify | + ~5 tests (config, tagging, metadata, From/Reply-To, error handling) |
| `.env.example` | modify or create | Document the new env var |
| Production `.env` | modify (on Droplet) | Add `POSTMARK_SERVER_TOKEN`, update `DEFAULT_FROM_EMAIL`, comment out (don't delete) old Gmail SMTP vars |
| `docs/superpowers/runbooks/postmark-deploy.md` | new | Deploy + rollback steps |

---

## Pre-flight (do before starting Task 1)

- [ ] **Confirm Postmark account state.** Postmark UI top bar must NOT show "Test mode" or "We're reviewing your account." Approved state was confirmed 2026-05-13.

- [ ] **Add a dedicated production Postmark server token** (don't regenerate the existing one — that'd invalidate the dev/local Keychain copy). In Postmark UI → Servers → My First Server → API Tokens → **Add Token** → name it `prod`. The Keychain token used for ad-hoc API work from this laptop must NOT be reused for prod — different rotation cycles, different blast radius. Store the new token directly in the production `.env` via SSH (never paste it into chat). If Postmark's UI only shows a single regenerate-style flow, regenerate the dev token first (re-add to Keychain), then create a fresh prod token afterwards.

- [ ] **Confirm DNS records.** All four must still resolve correctly via `dig @8.8.8.8`:
  - `TXT 20260513155127pm._domainkey.nyasablog.com` — DKIM
  - `CNAME pm-bounces.nyasablog.com` → `pm.mtasv.net` — Return-Path
  - `TXT _dmarc.nyasablog.com` — DMARC policy
  - Postmark UI → Domains → `nyasablog.com` should show both DKIM and Return-Path **Verified**.

- [ ] **Baseline tests green.** `python manage.py test account` from a clean checkout.

- [ ] **Confirm `ALLOWED_HOSTS` and `SITE_DOMAIN` in production settings.** Verification links are built from `settings.SITE_DOMAIN` (per `account/emails.py`), so this is less load-bearing than for the verification feature itself, but keeping a tight `ALLOWED_HOSTS` is still a security expectation for the site.

  ```bash
  ssh root@104.248.204.211 "grep -E 'ALLOWED_HOSTS|SITE_DOMAIN' /home/ephraim/djangoprojectdir/mysite/settings.py /home/ephraim/djangoprojectdir/.env 2>/dev/null"
  ```

---

## Task 1: Add `django-anymail[postmark]` as a dependency

**Files:**
- Modify: `requirements.txt`
- (Possibly) modify: `.pip-audit-ignore`

- [ ] **Step 1: Pin the package.** Add to `requirements.txt`:
  ```
  django-anymail[postmark]==15.0
  ```
  Anymail 15.0 supports Django 5.2 / 6.0 and Python 3.10+. NyasaBlog runs Python 3.12 so this is fine. The `[postmark]` extra adds Postmark-specific dependencies. Verify https://pypi.org/project/django-anymail/ at install time in case a newer release is current.

- [ ] **Step 2: Install locally.**
  ```bash
  source .venv/bin/activate
  pip install -r requirements.txt
  ```

- [ ] **Step 3: Run `pip-audit` to confirm no new CVEs.**
  ```bash
  pip-audit -r requirements.txt --ignore-vuln $(cat .pip-audit-ignore | grep -v '^#' | tr '\n' ',' | sed 's/,$//')
  ```
  If audit fails on an anymail-introduced CVE, evaluate: pin a different version, or add the CVE to `.pip-audit-ignore` with a justification.

- [ ] **Step 4: Commit.** `git -c commit.gpgsign=false commit -m "Add django-anymail[postmark] dependency"`

---

## Task 2: Configure Anymail in settings (with failing test first)

**Files:**
- Modify: `mysite/settings.py`
- Modify: `account/tests.py`

- [ ] **Step 1: Write the failing test** in `account/tests.py`. This proves the Anymail package is installed and resolvable; full config wiring is verified in Step 4 via `manage.py check`:

  ```python
  from django.test import TestCase, override_settings
  from django.core.mail import get_connection

  class PostmarkBackendTests(TestCase):
      @override_settings(
          EMAIL_BACKEND='anymail.backends.postmark.EmailBackend',
          ANYMAIL={'POSTMARK_SERVER_TOKEN': 'test-token'},
      )
      def test_anymail_postmark_backend_is_resolvable(self):
          conn = get_connection()
          self.assertEqual(
              conn.__class__.__module__,
              'anymail.backends.postmark',
          )
  ```

  Run: `python manage.py test account.tests.PostmarkBackendTests` — expect `ImportError` if Task 1 wasn't done; expect a pass once `django-anymail` is installed.

- [ ] **Step 2: Update `mysite/settings.py`.** Two changes:

  **(a) Add `anymail` to `INSTALLED_APPS`** (required for `manage.py` commands like Anymail's status check, and for webhook routing in Task 8):

  ```python
  INSTALLED_APPS = [
      # ... existing apps ...
      'anymail',
  ]
  ```

  **(b) Replace the email config in the `else:` block (around line 185)** with env-overridable backend selection (this is what enables fast rollback in Task 6 without code edits):

  ```python
  SUPPORT_EMAIL = config('SUPPORT_EMAIL', default='hello@nyasablog.com')

  if DEBUG:
      EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
  else:
      # Default is Postmark via Anymail. Override via env (e.g.
      # `EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend`) for
      # emergency rollback without redeploying.
      EMAIL_BACKEND = config(
          'EMAIL_BACKEND',
          default='anymail.backends.postmark.EmailBackend',
      )
      ANYMAIL = {
          'POSTMARK_SERVER_TOKEN': config('POSTMARK_SERVER_TOKEN'),
      }
      EMAIL_TIMEOUT = 10

  DEFAULT_FROM_EMAIL = config(
      'DEFAULT_FROM_EMAIL',
      default='NyasaBlog <hello@nyasablog.com>',
  )
  ```

  **Keep** the `EMAIL_HOST`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_PORT`, `EMAIL_USE_TLS` reads in `settings.py` with `default=''`/`default=587`/`default=True` as appropriate — they're no-ops while Anymail is the backend but **load-bearing for rollback**. Django's SMTP backend reads `settings.EMAIL_HOST` etc., NOT `os.environ` directly; if these `config(...)` calls are removed, an env-only `EMAIL_BACKEND=...smtp...` rollback silently fails (SMTP backend tries `localhost:25`). Earlier revision of this plan said to delete them — that was wrong; corrected 2026-05-14 during Task 2 execution.

  Also: `POSTMARK_SERVER_TOKEN` defaults to `''` rather than being required, so a rollback `.env` without the token doesn't crash settings load.

  **Do not set `SEND_DEFAULTS` / message stream.** Postmark's default stream is `outbound` which is exactly what transactional uses; explicit configuration is dead code until you add a second stream (Task 10).

- [ ] **Step 3: Update `.env.example`** (create if missing) with:
  ```
  POSTMARK_SERVER_TOKEN=<obtain from Postmark UI; never commit a real value>
  DEFAULT_FROM_EMAIL=NyasaBlog <hello@nyasablog.com>
  SUPPORT_EMAIL=hello@nyasablog.com
  # EMAIL_BACKEND override (only set during rollback):
  # EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
  ```

- [ ] **Step 4: Verify settings resolve correctly with env vars set.** This catches missing/typo'd config that `override_settings`-based unit tests can't:

  ```bash
  DEBUG=False \
  POSTMARK_SERVER_TOKEN=test-only-not-used \
  python manage.py check --deploy
  ```

  Should exit 0 with no errors about missing settings. Warnings about HTTPS / cookie security are expected because we're running locally and not all production env vars are set; ignore those.

- [ ] **Step 5: Re-run the failing test.** Should now pass.

- [ ] **Step 6: Run the full test suite.** `python manage.py test account` — all green.

- [ ] **Step 7: Commit.** `"Switch production EMAIL_BACKEND to django-anymail + Postmark"`

---

## Task 3: Add tags and metadata to verification emails

**Files:**
- Modify: `account/emails.py`
- Modify: `account/tests.py`

- [ ] **Step 1: Failing test.** Add to `account/tests.py`:

  ```python
  from django.core import mail
  from django.test import TestCase, override_settings
  from account.models import Account
  from account.emails import send_verification_email

  @override_settings(
      EMAIL_BACKEND='anymail.backends.test.EmailBackend',
      ANYMAIL={'POSTMARK_SERVER_TOKEN': 'test-token'},
  )
  class VerificationEmailTaggingTests(TestCase):
      def setUp(self):
          self.user = Account.objects.create_user(
              email='test@example.com', username='tester', password='x',
          )

      def test_verification_email_is_tagged_for_postmark(self):
          send_verification_email(self.user)
          sent = mail.outbox[-1]
          self.assertEqual(sent.anymail_test_params['tags'], ['email-verification'])

      def test_verification_email_includes_user_id_metadata(self):
          send_verification_email(self.user)
          sent = mail.outbox[-1]
          self.assertEqual(
              sent.anymail_test_params['metadata'],
              {'user_id': str(self.user.pk)},
          )
  ```

  Run: expect failure (`AttributeError` on `tags`/`metadata`).

- [ ] **Step 2: Update `account/emails.py`** to attach Anymail's `tags` and `metadata`:

  ```python
  msg = EmailMessage(subject=subject, body=body, to=[user.email])
  # Postmark allows AT MOST ONE tag per message. Adding a second tag raises
  # AnymailUnsupportedFeature at send time. Use `metadata` if you need to
  # categorize further.
  msg.tags = ['email-verification']  # surfaces in Postmark dashboard
  msg.metadata = {'user_id': str(user.pk)}  # available in webhooks + Activity
  msg.send()
  ```

  `tags` and `metadata` are Anymail-native attributes — they're ignored by SMTP backends (no-op) and used by ESP backends. So this remains compatible with local dev where the console backend is in play.

- [ ] **Step 3: Re-run the failing tests.** Should pass.

- [ ] **Step 4: Commit.** `"Tag verification emails for Postmark dashboard segmentation"`

---

## Task 4: Set From/Reply-To via DEFAULT_FROM_EMAIL + verify behavior

**Files:**
- Modify: `account/emails.py`
- Modify: `account/tests.py`

The current `EmailMessage(subject, body, to=[...])` doesn't pass `from_email`, so Django falls back to `DEFAULT_FROM_EMAIL`. That's correct. But we should also set a `Reply-To` so users who hit reply land somewhere a human reads.

- [ ] **Step 1: Failing test.**

  ```python
  def test_verification_email_has_reply_to_set(self):
      send_verification_email(self.user)
      sent = mail.outbox[-1]
      self.assertEqual(sent.reply_to, ['hello@nyasablog.com'])

  def test_verification_email_from_address_is_a_nyasablog_address(self):
      with override_settings(
          DEFAULT_FROM_EMAIL='NyasaBlog <hello@nyasablog.com>',
      ):
          send_verification_email(self.user)
      sent = mail.outbox[-1]
      self.assertIn('@nyasablog.com', sent.from_email)
  ```

- [ ] **Step 2: Update `account/emails.py`.** Add `reply_to`:

  ```python
  msg = EmailMessage(
      subject=subject,
      body=body,
      to=[user.email],
      reply_to=[settings.SUPPORT_EMAIL],
  )
  ```

  `SUPPORT_EMAIL` was added in Task 2 alongside the backend switch. Default is `hello@nyasablog.com` — a user-facing alias that catches via ImprovMX to Gmail. `admin@nyasablog.com` is intentionally not used as the reply-to: it reads as internal/admin-only to recipients. Keep `admin@` for Postmark account-confirmation mail only.

- [ ] **Step 3: Verify tests pass.**

- [ ] **Step 4: Commit.** `"Set Reply-To on verification emails so user replies reach a human"`

---

## Task 5: Local integration test — actually send through Postmark from dev

This task is **manual, not part of CI**. It validates the wiring before deploying.

**Don't `export DEBUG=False`.** It pulls in production-only branches (AWS Spaces, SECURE_SSL_REDIRECT, etc.) and you'll either need every prod env var set or fight cascading failures unrelated to email. Use `override_settings` in a one-off shell command instead — it isolates exactly the settings we want to test.

- [ ] **Step 1: Load tokens from Keychain.**
  ```bash
  nyasablog-env  # loads $POSTMARK_TOKEN
  ```

- [ ] **Step 2: Run an isolated send via Django shell + `override_settings`:**
  ```bash
  python manage.py shell <<'PY'
  from django.test.utils import override_settings
  from account.models import Account
  from account.emails import send_verification_email
  import os

  with override_settings(
      EMAIL_BACKEND='anymail.backends.postmark.EmailBackend',
      ANYMAIL={'POSTMARK_SERVER_TOKEN': os.environ['POSTMARK_TOKEN']},
      DEFAULT_FROM_EMAIL='NyasaBlog <hello@nyasablog.com>',
      SUPPORT_EMAIL='hello@nyasablog.com',
  ):
      u, _ = Account.objects.get_or_create(
          email='mkanyandula@gmail.com',
          defaults={'username': 'me-test'},
      )
      send_verification_email(u)
      print('Sent.')
  PY
  ```

  No env vars touch your shell; nothing persists. Token comes from Keychain via the `nyasablog-env` function loaded in Step 1.

- [ ] **Step 3: Verify in Gmail.** Expected: email lands in Inbox (not Spam) from `NyasaBlog <hello@nyasablog.com>`. Show Original:
  - DKIM: PASS with `nyasablog.com` selector `20260513155127pm`
  - SPF: PASS (via `pm-bounces.nyasablog.com`)
  - DMARC: PASS (alignment now works for both DKIM and SPF)

- [ ] **Step 4: Verify in Postmark dashboard.** Activity tab shows the send tagged `email-verification` with metadata `user_id=<pk>`.

- [ ] **Step 5: Clean up the test Account** so it doesn't end up in production: `python manage.py shell -c "from account.models import Account; Account.objects.filter(username='me-test').delete()"`.

---

## Task 6: Production deploy

**Files:**
- Modify: production `.env` on Droplet
- Push code to main branch (existing CI/CD picks it up)
- Document in: `docs/superpowers/runbooks/postmark-deploy.md` (new)

- [ ] **Step 1: Write the runbook** at `docs/superpowers/runbooks/postmark-deploy.md` (template at end of this plan).

- [ ] **Step 2: SSH and update production `.env`:**

  ```bash
  ssh root@104.248.204.211
  cd /home/ephraim/djangoprojectdir
  cp .env .env.pre-postmark.$(date +%Y%m%d)   # backup
  ```

  Edit `.env`:
  - **Add:** `POSTMARK_SERVER_TOKEN=<token from Postmark UI>`
  - **Add:** `SUPPORT_EMAIL=admin@nyasablog.com`
  - **Change:** `DEFAULT_FROM_EMAIL=NyasaBlog <admin@nyasablog.com>` (was `khayamalawi@gmail.com`)
  - **Comment out** (don't delete — keeps fast rollback): `EMAIL_HOST`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_PORT`, `EMAIL_USE_TLS`

  Confirm permissions: `chmod 600 .env`.

- [ ] **Step 3: Deploy code.** Use the `nyasablog-deploy` skill or manual rsync. The new `EMAIL_BACKEND` and `ANYMAIL` settings ship with the deploy.

- [ ] **Step 4: Install dependency on the server:**
  ```bash
  sudo -u ephraim /home/ephraim/djangoprojectdir/djangoprojectenv/bin/pip install -r /home/ephraim/djangoprojectdir/requirements.txt
  ```

- [ ] **Step 5: Restart Gunicorn:** `systemctl restart gunicorn`.

- [ ] **Step 6: Smoke test in prod.** Register a brand-new test account at https://nyasablog.com/register/ with a throwaway email you control. Verify:
  - Email lands in Inbox within ~30s.
  - From: `NyasaBlog <admin@nyasablog.com>`.
  - Show Original: DKIM/SPF/DMARC all PASS.
  - Verification link works → account activates → logs in.

- [ ] **Step 7: Delete the throwaway account** via Django admin or `manage.py shell`.

- [ ] **Step 8: Revoke Gmail app password.** In your Google account → Security → App passwords → revoke the one used by `khayamalawi@gmail.com` for NyasaBlog SMTP. Without this, the credential is still live, which violates least-privilege.

---

## Rollback plan

Because `EMAIL_BACKEND` is env-controlled (Task 2 Step 2b), rollback is `.env`-only — no code revert required.

If anything goes wrong in production (mail not sending, mail going to spam at unexpected rate, Postmark API errors in logs):

1. **SSH to Droplet:** `cd /home/ephraim/djangoprojectdir`.
2. **Restore the old `.env`** which still contains the Gmail SMTP block (Task 6 keeps them commented out, not deleted):
   ```bash
   cp .env.pre-postmark.<date> .env
   chmod 600 .env
   ```
   OR — if the backup is missing — edit `.env` directly and add these lines (override the default Postmark backend with SMTP):
   ```
   EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
   EMAIL_HOST=smtp.gmail.com
   EMAIL_HOST_USER=khayamalawi@gmail.com
   EMAIL_HOST_PASSWORD=<app password — generate a new one if you revoked the old>
   EMAIL_PORT=587
   EMAIL_USE_TLS=True
   DEFAULT_FROM_EMAIL=NyasaBlog <khayamalawi@gmail.com>
   ```
3. **Restart Gunicorn:** `systemctl restart gunicorn`.
4. **Verify rollback** by triggering a registration in incognito and confirming mail arrives.

Total rollback time: **<2 minutes** with the `.env` backup. The env-controlled backend means no code edit, no deploy, no git revert.

**If you already revoked the Gmail app password** (Task 6 Step 8) and need to roll back, Google can't restore the revoked one — generate a new app password at https://myaccount.google.com/apppasswords. Adds ~2 minutes to rollback.

---

## Test plan

**Unit / integration (in `account/tests.py`):**

1. `test_anymail_postmark_backend_is_importable` (Task 2)
2. `test_verification_email_is_tagged_for_postmark` (Task 3)
3. `test_verification_email_includes_user_id_metadata` (Task 3)
4. `test_verification_email_has_reply_to_set` (Task 4)
5. `test_verification_email_from_address_is_admin_at_nyasablog` (Task 4)

These use Anymail's `test` backend (`anymail.backends.test.EmailBackend`), which captures the same data the Postmark backend would send without making real API calls.

**Manual (Task 5 + Task 6.6):** end-to-end send + Gmail Show Original auth check.

**Regression:** existing email-verification feature tests (`account/tests.py::RegistrationViewTests`, etc.) must remain green. The change is backend-only — behavior is identical from Django's perspective.

---

## Follow-up tasks (in this plan, separate PRs)

Tasks 1–6 are the core migration and must ship together. Tasks 7–10 are sequenced for separate PRs after the migration is stable. The "When" column gives the trigger for each; don't bundle them into Tasks 1–6 even if you have time — keeping them separate keeps reviews focused and rollback simple.

| Task | What | When |
|---|---|---|
| 7 | Password reset email tagging | Immediately after Task 6 smoke test passes (same week) |
| 8 | Bounce/complaint webhook handlers | Within 2 weeks of migration; ahead of any volume scale-up |
| 9 | Remove commented-out Gmail SMTP lines | ~30 days after Task 6 deploys cleanly |
| 10 | Multiple Postmark message streams | Only when a non-transactional use case appears (e.g., broadcast email) |

---

## Task 7: Tag password reset emails for Postmark dashboard

**Files:**
- Modify: `templates/registration/password_reset_email.html` (if needed for body) — or override the view
- Create: `account/views.py` modification or new `account/password_reset.py` subclassing Django's `PasswordResetView`
- Modify: `mysite/urls.py` to point password-reset URL at the subclass
- Modify: `account/tests.py`

Django's built-in `PasswordResetView` constructs an `EmailMultiAlternatives` internally with no hook for `tags`/`metadata`. Two options to add them:

- **Option A — subclass `PasswordResetForm`** and override `send_mail()`. Cleanest. The form is what actually builds the email.
- **Option B — write a custom view that doesn't use Django's built-in.** More code, more behavior to maintain. Skip unless A doesn't fit.

Use Option A.

- [ ] **Step 1: Failing test.** In `account/tests.py`:

  ```python
  @override_settings(
      EMAIL_BACKEND='anymail.backends.test.EmailBackend',
      ANYMAIL={'POSTMARK_SERVER_TOKEN': 'test-token'},
  )
  class PasswordResetEmailTaggingTests(TestCase):
      def setUp(self):
          self.user = Account.objects.create_user(
              email='reset@example.com', username='reset', password='x',
              is_active=True,
          )
          self.user.email_verified = True
          self.user.save()

      def test_password_reset_email_is_tagged(self):
          self.client.post('/password_reset/', {'email': 'reset@example.com'})
          self.assertEqual(len(mail.outbox), 1)
          self.assertEqual(mail.outbox[0].anymail_test_params['tags'], ['password-reset'])

      def test_password_reset_email_includes_user_id_metadata(self):
          self.client.post('/password_reset/', {'email': 'reset@example.com'})
          self.assertEqual(
              mail.outbox[0].anymail_test_params['metadata'],
              {'user_id': str(self.user.pk)},
          )
  ```

  Adjust the URL path to whatever `mysite/urls.py` actually uses for password reset.

- [ ] **Step 2: Create `account/forms.py` addition** (or new file `account/password_reset_form.py`) with a subclass:

  ```python
  from django.contrib.auth.forms import PasswordResetForm
  from django.core.mail import EmailMultiAlternatives
  from django.template import loader

  class TaggedPasswordResetForm(PasswordResetForm):
      def send_mail(self, subject_template_name, email_template_name,
                    context, from_email, to_email,
                    html_email_template_name=None):
          subject = loader.render_to_string(subject_template_name, context).strip()
          body = loader.render_to_string(email_template_name, context)
          msg = EmailMultiAlternatives(subject, body, from_email, [to_email])
          if html_email_template_name is not None:
              html_email = loader.render_to_string(html_email_template_name, context)
              msg.attach_alternative(html_email, 'text/html')
          msg.tags = ['password-reset']
          # `context['user']` is the Account instance Django's view passed in
          user = context.get('user')
          if user is not None:
              msg.metadata = {'user_id': str(user.pk)}
          msg.reply_to = [settings.SUPPORT_EMAIL]
          msg.send()
  ```

- [ ] **Step 3: Wire it into `mysite/urls.py`.** Find the existing password-reset route and pass the form class:

  ```python
  from django.contrib.auth import views as auth_views
  from account.forms import TaggedPasswordResetForm

  path(
      'password_reset/',
      auth_views.PasswordResetView.as_view(form_class=TaggedPasswordResetForm),
      name='password_reset',
  ),
  ```

- [ ] **Step 4: Verify tests pass.**

- [ ] **Step 5: Manual smoke test** in dev: trigger password reset for a real test user; check console output (or use Task 5's prod-mode shell pattern to send through Postmark and inspect the dashboard).

- [ ] **Step 6: Commit + deploy** as a separate PR from the migration. Title: `"Tag password-reset emails for Postmark dashboard segmentation"`.

---

## Task 8: Bounce/complaint webhook handlers

**Files:**
- Modify: `requirements.txt` (Anymail already includes webhook support — no new dep)
- Modify: `mysite/urls.py` to include Anymail's webhook URLs
- Modify: `mysite/settings.py` to add `ANYMAIL['WEBHOOK_SECRET']` and signal handlers
- Create: `account/signals.py` (or add to existing) — handle `anymail.signals.tracking` events
- Modify: `account/models.py` — optionally add a `SuppressedEmail` model, or use Django's cache
- Modify: `account/tests.py`

**Why this matters:** Without webhooks, you don't know when your verification emails bounce or get marked as spam. Postmark already won't retry hard-bounced addresses (their own suppression list handles that internally), but for your own Django side, you want to:

1. Know when a verification email bounced → display "we couldn't reach that email" on the user's next login attempt.
2. Block re-registration with addresses Postmark has marked as bouncing.
3. Track complaint signals (Gmail "Report spam" → Postmark spam-complaint webhook) so you can be proactive about senders flagged as spammy.

**Security note:** The webhook endpoint is publicly reachable. Anymail handles signature verification via `WEBHOOK_SECRET`. Do NOT skip configuring it.

- [ ] **Step 1: Failing test** — POST a forged webhook to the endpoint, expect 400/401.

  ```python
  @override_settings(ANYMAIL={'POSTMARK_SERVER_TOKEN': 't', 'WEBHOOK_SECRET': 'user:pass'})  # pragma: allowlist secret
  class WebhookSecurityTests(TestCase):
      def test_unauthenticated_webhook_post_is_rejected(self):
          response = self.client.post('/anymail/postmark/tracking/', data={}, content_type='application/json')
          self.assertEqual(response.status_code, 400)
  ```

- [ ] **Step 2: Add webhook routing.** In `mysite/urls.py`:

  ```python
  path('anymail/', include('anymail.urls')),
  ```

- [ ] **Step 3: Generate a webhook secret** (NOT in Keychain — it goes into prod `.env` only):

  ```bash
  python -c "import secrets; print(secrets.token_urlsafe(32))"
  ```

  Add to production `.env`:
  ```
  ANYMAIL_WEBHOOK_SECRET=<the generated value>
  ```

  Update `mysite/settings.py`:
  ```python
  ANYMAIL = {
      'POSTMARK_SERVER_TOKEN': config('POSTMARK_SERVER_TOKEN'),
      'WEBHOOK_SECRET': config('ANYMAIL_WEBHOOK_SECRET'),
  }
  ```

  Anymail uses HTTP Basic auth on the webhook endpoint. Format the secret as `user:password` (e.g. `nyasablog:<random>`). Adjust the env var accordingly.

- [ ] **Step 4: Configure Postmark to POST to the endpoint.** In Postmark UI → Servers → My First Server → Default Transactional Stream → **Webhooks** → Add webhook.
  - URL: `https://<user>:<password>@nyasablog.com/anymail/postmark/tracking/` (Basic auth in URL)
  - Events: Bounce, SpamComplaint, Open, Click (last two optional — set if you want engagement tracking)

- [ ] **Step 5: Signal handler.** In `account/signals.py`:

  ```python
  from anymail.signals import tracking
  from django.dispatch import receiver

  @receiver(tracking)
  def handle_tracking_event(sender, event, esp_name, **kwargs):
      if event.event_type in ('bounced', 'rejected', 'complained'):
          # Look up the user via metadata
          user_id = event.metadata.get('user_id')
          if not user_id:
              return
          # Mark account as having a bouncing email — surface on next login attempt
          # (implementation depends on what UX you want here)
          ...
  ```

  Decide the data model for "bounced address" tracking:
  - **Simple:** add a boolean `email_bounced` field on `Account`.
  - **Richer:** new `SuppressedEmail` model with email + reason + timestamp.

  Simple is probably enough for v1.

- [ ] **Step 6: Tests** for the signal handler with synthesized event payloads.

- [ ] **Step 7: Manual test in production** by sending to a known-bouncing address (Postmark provides `bounces+hardbounce@postmarkapp.com` for this) and confirming the webhook fires + the user record updates.

- [ ] **Step 8: Commit + deploy** as separate PR: `"Wire up Postmark bounce/complaint webhooks via django-anymail"`.

---

## Task 9: Remove commented-out Gmail SMTP lines

Cleanup PR. Run ~30 days after Task 6 deploys, only if:
- Zero deliverability incidents traceable to the new backend.
- Postmark Activity dashboard shows healthy delivery rates.
- Bounce rate is within expected range (<5% for verification mail).

**Files:**
- Modify: `mysite/settings.py` (delete commented-out lines)
- Modify: production `.env` (delete commented-out lines)
- Delete: `.env.pre-postmark.<date>` backup on Droplet (server-side cleanup)

- [ ] **Step 1: Delete from `mysite/settings.py`** any commented `EMAIL_HOST`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_PORT`, `EMAIL_USE_TLS` references.

- [ ] **Step 2: SSH and clean prod `.env`:**
  ```bash
  ssh root@104.248.204.211
  cd /home/ephraim/djangoprojectdir
  # Edit .env, remove commented lines
  # Then delete the backup
  rm .env.pre-postmark.<date>
  ```

- [ ] **Step 3: Deploy.** Standard rsync flow.

- [ ] **Step 4: Commit.** Title: `"Remove dead Gmail SMTP config now that Postmark is stable"`.

**Don't skip this task.** Dead commented code rots; future maintainers (including you in 6 months) will wonder if it's load-bearing. Either it's real config or it isn't.

---

## Task 10: Multiple Postmark message streams

**Trigger:** A non-transactional sending use case appears. Examples that would justify it:

- Newsletter / digest emails to subscribers (broadcast stream).
- Marketing announcements about new content (broadcast).
- Internal notifications to admins about events (a separate transactional stream so admin mail isn't lumped in with user-facing transactional metrics).

**Until that trigger fires, don't do this task.** Postmark accounts include separate broadcast and inbound streams by default; you just don't use them. Multiple transactional streams aren't free — Postmark prices broadcasts separately.

**When triggered:**

- [ ] **Step 1: Design.** Write a short spec (not just plan) at `docs/superpowers/specs/<date>-postmark-multistream.md` covering:
  - Which streams (broadcast? second transactional?)
  - How code decides which stream to use (per-call argument, or settings-driven)
  - Suppression list scoping (broadcasts have their own suppression separate from transactional)
  - Cost implications

- [ ] **Step 2: Update `ANYMAIL` settings** with `POSTMARK_SEND_DEFAULTS` or per-message stream tags.

- [ ] **Step 3: Refactor relevant send sites** to pass `esp_extra={'MessageStream': '<name>'}` per send.

- [ ] **Step 4: Tests.**

- [ ] **Step 5: Deploy + verify in Postmark dashboard** that messages land in the right stream.

---

## Tasks 1–6 vs 7–10: shipping discipline

**Always ship Tasks 1–6 together.** Splitting them risks an intermediate state where the backend is half-swapped.

**Tasks 7–10 ship as separate PRs.** Each gets its own review, its own rollback story. Resist the urge to combine them — small PRs are easier to bisect when something breaks later.

---

## Pre-deploy checklist (consolidated)

- [ ] Postmark approval confirmed
- [ ] Fresh production server token generated, stored only in production `.env`
- [ ] DNS records (DKIM, Return-Path, DMARC) all verified
- [ ] `django-anymail[postmark]` pinned and installed
- [ ] `pip-audit` clean
- [ ] All unit tests pass (existing + new)
- [ ] Local end-to-end test (Task 5) shows DKIM/SPF/DMARC PASS in Gmail
- [ ] Production `.env` backed up before edit
- [ ] Rollback steps validated (mentally walked through; ideally tested in staging if one existed)
- [ ] Runbook written
- [ ] Gmail app password revocation scheduled for after smoke-test passes

---

## Runbook template (Task 6 artifact)

Create at `docs/superpowers/runbooks/postmark-deploy.md`:

```markdown
# Postmark backend deploy (django-anymail)

## What this runbook is for
Switching production from Gmail SMTP to Postmark/Anymail. One-shot operation;
do not run repeatedly.

## Pre-flight
1. Postmark account: approved (no "Test mode" banner).
2. DNS: DKIM, Return-Path, DMARC all resolving + DKIM/Return-Path verified
   in Postmark UI.
3. Fresh production server token generated; old test-mode token can be revoked
   after this deploy succeeds.

## Deploy steps
[copy from Task 6 of the migration plan]

## Smoke test
[copy from Task 6.6]

## Rollback
[copy from Rollback plan section]

## Post-deploy
1. Revoke Gmail app password used by khayamalawi@gmail.com for SMTP.
2. Schedule cleanup PR for ~30 days out: delete commented-out SMTP env vars
   from .env, delete the .env.pre-postmark.<date> backup.
```
