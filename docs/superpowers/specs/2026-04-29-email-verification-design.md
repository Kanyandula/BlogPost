# Email Verification on Account Creation — Design

**Date:** 2026-04-29
**Status:** Draft (pending implementation plan)
**Owner:** Ephraim Kanyandula

## Goal

Require new NyasaBlog users to verify their email address before their account can be used. Reduce spam/abandoned signups without disrupting existing legitimate users.

## Decisions

| # | Decision | Rationale |
|---|----------|-----------|
| 1 | **Hard gate** — `is_active=False` until verified, login blocked | Strongest anti-abuse posture; matches the user's explicit choice |
| 2 | **Custom token flow**, mirroring Django's password-reset pattern | No new dependency; reuses `default_token_generator` style, existing SMTP config, and `templates/registration/` directory; fits the codebase (custom `Account` model, HTMX, function-based views) |
| 3 | **Selective grandfathering** — `is_staff OR is_superuser OR has any BlogPost (any status)` → auto-verified; everyone else must verify on next login | Real contributors and admins keep working unchanged; lurkers/spam signups go through the gate |
| 4 | **3-day token lifetime** — reuse `PASSWORD_RESET_TIMEOUT` | Same expiry as password reset; one timeout to reason about |
| 5 | **Hybrid login UX** — generic "invalid credentials" + always-shown resend link; resend endpoint always returns 200 with the same response | No account enumeration; usable for legit users; handles typo'd-email case gracefully |
| 6 | **Auto-purge unverified accounts after 7 days** via management command + cron | Frees up email/username for re-registration; keeps tables clean. 7 days fits one signup-link window (days 0–3) plus one resend window (days 4–7), so a user who misses the first link still has a chance to recover before purge |

## Architecture

### Data model change

One new field on `Account`:

```python
email_verified = models.BooleanField(default=False)
```

No new tables. `is_active` continues to mean "can log in"; `email_verified` is the source-of-truth for the verification check. They are intentionally separate fields: `is_active` may later be flipped off independently (e.g., banned account), and we want the verification semantics distinct from the activation semantics.

### Token generator

`account/tokens.py`:

```python
from django.contrib.auth.tokens import PasswordResetTokenGenerator

class EmailVerificationTokenGenerator(PasswordResetTokenGenerator):
    def _make_hash_value(self, user, timestamp):
        return f"{user.pk}{user.email}{user.email_verified}{timestamp}"

email_verification_token = EmailVerificationTokenGenerator()
```

The hash includes `user.email_verified`, so the token becomes invalid the moment verification flips to `True`. This gives single-use semantics for free, including across resends.

### URL routes (mysite/urls.py)

```
path('confirm-email/<uidb64>/<token>/', confirm_email_view, name='confirm_email'),
path('resend-verification/', resend_verification_view, name='resend_verification'),
```

### Views (account/views.py)

- **`registration_view`** — Modified. Saves account with `is_active=False`, sends verification email via `send_verification_email(account, request)`, renders `verification_sent.html`. No auto-login.
- **`login_view`** — Modified. After `authenticate()`, reject if `user is None` OR `user.email_verified is False`; render the existing login template with a generic "Invalid credentials" error and a "Didn't receive verification email? Resend" link. The link is always shown on every failed login (no enumeration). This is the single canonical place the verification check lives — `AccountAuthenticationForm` keeps doing field-level validation only, not user resolution.
- **`confirm_email_view(request, uidb64, token)`** — New. Decode uid, fetch account, validate token. On success: `is_active=True; email_verified=True; save()`, log the user in, redirect to `home` with a success toast. On failure: render `verification_invalid.html` with a resend form.
- **`resend_verification_view`** — New. GET renders the form. POST always renders the same "If that email is registered and unverified, we sent a new link" page. Internally, only sends if `Account.objects.filter(email=email, email_verified=False).exists()`. Accepts an `?email=` query param for prefill from the login error link.

### Forms

`AccountAuthenticationForm` (existing custom login form) is **not** modified — it continues to validate form fields only. The `email_verified` check lives in `login_view`, which is the existing place that calls `authenticate()` and decides whether to log the user in. Keeping it in one place prevents the form-vs-view duplication trap.

### Email templates

Mirroring the password-reset templates already in `templates/registration/`:

- `templates/registration/email_verification_subject.txt`
- `templates/registration/email_verification_email.html`

The verification URL is built with `request.build_absolute_uri(reverse('confirm_email', kwargs={...}))` so it works in dev and prod without a hardcoded domain.

### User-facing pages

- `templates/account/verification_sent.html` — "We sent a link to <email>. Check your inbox."
- `templates/account/verification_invalid.html` — "This link is invalid or expired" + embedded resend form.

## Migration plan

### Schema migration (auto-generated)

Adds `email_verified = BooleanField(default=False)` to `account.Account`.

### Data migration (hand-written)

```python
def grandfather(apps, schema_editor):
    Account = apps.get_model('account', 'Account')
    BlogPost = apps.get_model('blog', 'BlogPost')
    contributor_ids = set(BlogPost.objects.values_list('author_id', flat=True))
    Account.objects.filter(
        Q(is_staff=True) | Q(is_superuser=True) | Q(pk__in=contributor_ids)
    ).update(email_verified=True)
```

Reverse operation is `noop` — un-grandfathering on rollback would lock real users out.

After this migration runs:

- All staff and superusers: verified.
- All users with at least one `BlogPost` (any status, including drafts): verified.
- Everyone else (lurkers, commenters, spam signups): unverified, will be sent through the verification flow on their next login attempt.

## Cleanup

`account/management/commands/purge_unverified_accounts.py`:

```python
class Command(BaseCommand):
    help = "Delete accounts with email_verified=False older than 7 days."
    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')
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

System cron entry on the Droplet (under `ephraim`):

```
0 3 * * * cd /home/ephraim/djangoprojectdir && /home/ephraim/djangoprojectenv/bin/python manage.py purge_unverified_accounts >> /var/log/nyasablog/purge.log 2>&1
```

The exact venv path will be verified via SSH before installing.

## Files touched

| Path | Change |
|------|--------|
| `account/models.py` | + `email_verified` field |
| `account/migrations/0XXX_add_email_verified.py` | new (schema) |
| `account/migrations/0XXX_grandfather_existing_users.py` | new (data) |
| `account/tokens.py` | new |
| `account/views.py` | modify `registration_view`, `login_view`; add `confirm_email_view`, `resend_verification_view` |
| `account/management/commands/purge_unverified_accounts.py` | new |
| `mysite/urls.py` | + 2 routes |
| `templates/registration/email_verification_subject.txt` | new |
| `templates/registration/email_verification_email.html` | new |
| `templates/account/verification_sent.html` | new |
| `templates/account/verification_invalid.html` | new |
| `account/tests.py` | + ~12 tests |

## Test plan

Automated (`account/tests.py`):

1. `test_registration_creates_inactive_unverified_account`
2. `test_registration_sends_verification_email`
3. `test_registration_does_not_log_user_in`
4. `test_confirm_email_with_valid_token_activates_account`
5. `test_confirm_email_with_invalid_token_shows_error_page`
6. `test_confirm_email_with_expired_token_shows_error_page` (freeze time +4 days)
7. `test_token_invalidated_after_first_use` (second click fails)
8. `test_unverified_user_cannot_log_in` (correct password, generic error)
9. `test_resend_verification_sends_new_email_for_unverified_account`
10. `test_resend_verification_silent_for_unknown_or_verified_email` (no enumeration)
11. `test_purge_command_deletes_old_unverified_only` (matrix of 4 accounts)
12. `test_grandfather_migration` (staff, contributor, lurker)

Manual (post-deploy, throwaway email):

- Register fresh → receive email → click link → land logged in on home.
- Attempt login pre-verification → generic error + visible resend link.
- Click an expired link → see resend form.
- `python manage.py purge_unverified_accounts --dry-run` → expected count, no deletions.

## Out of scope

- Social/OAuth signup (no Google/Facebook login currently).
- Changing email after signup (would need re-verification — separate feature).
- Rate-limiting the resend endpoint (Django doesn't ship this; would need `django-ratelimit` or similar — separate concern).
- 2FA / MFA.
