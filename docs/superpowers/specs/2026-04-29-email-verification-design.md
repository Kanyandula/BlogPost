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

The hash includes `user.email_verified`, so **all outstanding tokens for an account become invalid the moment `email_verified` flips to `True`**. Multiple unused tokens may coexist before that point — a user who triggers two resends has three live tokens, any one of which works. The first valid click ends the verification window and burns all of them. This is sufficient for our purposes (we don't need per-token revocation) and avoids the complexity of a token table.

### URL routes (mysite/urls.py)

```
path('confirm-email/<uidb64>/<token>/', confirm_email_view, name='confirm_email'),
path('resend-verification/', resend_verification_view, name='resend_verification'),
```

### Views (account/views.py)

- **`registration_view`** — Modified. Saves account with `is_active=False`, sends verification email via `send_verification_email(account, request)`, renders `verification_sent.html`. No auto-login.
- **`login_view`** — Modified. After `authenticate()`, reject if `user is None` OR `user.email_verified is False`; render the existing login template with a generic "Invalid credentials" error and a "Didn't receive verification email? Resend" link. The link is always shown on every failed login (no enumeration). This is the single canonical place the verification check lives — `AccountAuthenticationForm` keeps doing field-level validation only, not user resolution.
- **`confirm_email_view(request, uidb64, token)`** — New. Decode uid, fetch account, validate token. On success: `is_active=True; email_verified=True; save()`, log the user in, redirect to `home` with a success toast. On failure: render `verification_invalid.html` with a resend form.
- **`resend_verification_view`** — New. GET renders the form. POST always renders the same "If that email is registered and unverified, we sent a new link" page. Internally, only sends if `Account.objects.filter(email__iexact=email, email_verified=False).exists()` AND the per-email cooldown has elapsed (see Rate limiting below). The lookup and the cooldown key both use the lowercased email so an attacker can't bypass the cooldown by toggling case. Accepts an `?email=` query param for prefill from the login error link.

### Forms

`AccountAuthenticationForm` (existing custom login form) is **not** modified — it continues to validate form fields only. The `email_verified` check lives in `login_view`, which is the existing place that calls `authenticate()` and decides whether to log the user in. Keeping it in one place prevents the form-vs-view duplication trap.

### Email templates

Mirroring the password-reset templates already in `templates/registration/`:

- `templates/registration/email_verification_subject.txt`
- `templates/registration/email_verification_email.html`

The verification URL is built with `request.build_absolute_uri(reverse('confirm_email', kwargs={...}))` so it works in dev and prod without a hardcoded domain. **Pre-flight requirement:** `ALLOWED_HOSTS` in production settings must be tight (`['nyasablog.com', 'www.nyasablog.com']`) — `build_absolute_uri` trusts the `Host` header, so a permissive `ALLOWED_HOSTS = ['*']` would let an attacker send a victim a verification link pointing at an attacker-controlled domain that proxies the real one. Verify this before deploying.

### Rate limiting

The resend endpoint is an unauthenticated public POST that triggers real outbound email through SMTP on a 1GB Droplet. Without a cap, a single attacker can flood the SMTP relay or mailbomb a target email address. Mitigation:

```python
from django.core.cache import cache

def _can_send_resend(email: str) -> bool:
    key = f"resend_cooldown:{email.lower()}"
    if cache.get(key):
        return False
    cache.set(key, True, timeout=60)  # 60-second per-email cooldown
    return True
```

Applied inside `resend_verification_view` *before* sending. The outer response is identical regardless of cooldown state — the user just doesn't receive a duplicate email. Keys are scoped per-email, not per-IP, because per-IP would be circumvented trivially and per-email is what matters for mailbomb prevention.

The default cache backend (`LocMemCache`) is acceptable for a single-Gunicorn-worker deploy; if Gunicorn workers are scaled later, the backend should move to Redis or filesystem cache so cooldown state is shared. Note this in the runbook when scaling.

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
| `account/tests.py` | + ~16 tests |

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
12. `test_grandfather_migration` (staff, contributor, lurker — assert correct verified state)
13. `test_grandfather_migration_idempotent` — re-running the data migration after an already-verified user has signed up, verified normally, or had their email changed must not regress their state. Asserts `.update()` semantics hold and no user is un-verified by a second run.
14. `test_login_with_wrong_password_for_unverified_account_does_not_send_email` — failed login must never trigger a verification email. Only the explicit resend endpoint sends. Guards against accidentally wiring email-send into the login error path during implementation.
15. `test_purged_email_can_be_reregistered` — create unverified account, age it 8 days, run purge, register a brand-new account with the same email, assert success. Validates the "free up email/username" goal of the cleanup feature end-to-end.
16. `test_resend_rate_limited_within_cooldown` — two POSTs in quick succession; only the first sends mail. Outer response identical. Third POST after `cache.clear()` (or time advance) sends again.

Manual (post-deploy, throwaway email):

- Register fresh → receive email → click link → land logged in on home.
- Attempt login pre-verification → generic error + visible resend link.
- Click an expired link → see resend form.
- `python manage.py purge_unverified_accounts --dry-run` → expected count, no deletions.

## Decision history

These are the decisions made during brainstorming and the reasoning behind them. Code review will ask "why this and not X?" — the answers live here.

- **Custom token flow over `django-allauth`.** The `Account` model is custom (`AbstractBaseUser`, `USERNAME_FIELD='email'`), the registration form is HTMX-wired, and Django's password-reset templates already exist in `templates/registration/`. Allauth would mean reshaping working code to fit its conventions and adding a real dependency to a 1GB Droplet for ~150 LoC of native-Django logic.
- **Hard gate over soft gate.** Soft-gating (login allowed, but commenting/posting blocked until verified) requires permission checks scattered through the codebase — every new contribution surface is a place to forget the check. Hard-gating concentrates the risk in exactly one place: SMTP delivery. Since password reset is already proving SMTP works in production, the delivery risk is well-understood and bounded; the soft-gate's permission-surface risk is open-ended.
- **Grandfather contributors, not just staff.** Staff-only grandfathering would force every existing author through verification on next login, with the cost being one author's typo'd-or-abandoned email = one locked-out real contributor. That cost is worse than letting lurkers re-verify; the point of verification is forward-looking spam prevention, not retroactive cleanup of legitimate users.
- **3-day token lifetime, matching `PASSWORD_RESET_TIMEOUT`.** One timeout to reason about across two flows. 24 hours is unforgiving on Malawian mobile networks where mail delivery can lag; 7 days is forgiving but mostly buys time for already-abandoned signups.
- **Hybrid login UX (generic error + always-shown resend link, always-200 resend response).** Account enumeration matters more for a public site than an internal tool. The hybrid pattern costs nothing extra to implement and handles the wrong-email-at-signup recovery case gracefully.
- **7-day purge window.** Equals two consecutive 3-day token windows: signup link (days 0–3) plus one resend window (days 4–7). A user who misses the first link has one shot to recover before purge frees the email/username.
- **`email_verified` as a separate field from `is_active`.** Verification semantics ("did you click the link?") and activation semantics ("are you allowed to log in?") will diverge — a banned user is `is_active=False` but stays verified. Coupling them now means uncoupling later.

## Out of scope

- Social/OAuth signup (no Google/Facebook login currently).
- Changing email after signup (would need re-verification — separate feature).
- IP-based rate limiting (per-email cooldown is in scope and is the meaningful defence; per-IP is trivially circumvented and adds complexity for marginal value).
- 2FA / MFA.
