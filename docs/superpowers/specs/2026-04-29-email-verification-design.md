# Email Verification on Account Creation — Design

**Date:** 2026-04-29
**Status:** Draft (pending implementation plan)
**Owner:** Ephraim Kanyandula

## Goal

Require new NyasaBlog users to verify their email address before their account can be used. Reduce spam/abandoned signups without disrupting existing legitimate users.

## Decisions

| # | Decision | Rationale |
|---|----------|-----------|
| 1 | **Hard gate on web + API v2** — `is_active=False` until verified, login blocked. API v1 keeps issuing tokens (back-compat) but `IsEmailVerified` permission gates *write* endpoints universally so the spam vector is closed at the action level | Strongest anti-abuse posture for web/v2; API v1 preserves the existing mobile contract while still preventing unverified actions |
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

**Field defaults across creation paths:**

| Path | `is_active` | `email_verified` |
|------|-------------|------------------|
| Web `registration_view` | False (set explicitly) | False (model default) |
| API `registration_view` v2 | False (set explicitly) | False (model default) |
| API `registration_view` v1 | True (model default kept for back-compat) | False (model default) |
| Admin / shell / `create_user(...)` | True (model default kept) | False (model default) |
| `confirm_email_view` / API `confirm-email` (success) | True (flipped) | True (flipped) |

The model default for `is_active` stays at Django's default (`True`) — paths that need to gate set it to `False` explicitly. This avoids breaking `create_user` callers (admin command-line, fixtures, tests outside this feature) that don't know about the gate.

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

### Auth error UX fixes (bundled into this feature)

The existing login/register partials (`account/templates/account/partials/login_form.html`, `register_form.html`) iterate `field.errors` only — they do not render `form.non_field_errors`. The login form's wrong-password path raises a non-field `ValidationError("Invalid login")` from `AccountAuthenticationForm.clean()`, which means **the form currently re-renders blank with no visible error message on failed login**. This is a pre-existing bug, not something the verification feature introduces, but we'd ship the same silent-failure UX to every new error state in this feature (expired link, unverified login attempt, rate-limit hit) if we don't fix it now.

Bundled fixes:

1. **Add `form.non_field_errors` block to both partials** at the top of the form, styled consistently with field errors:
   ```django
   {% if login_form.non_field_errors %}
   <div class="rounded-lg bg-error/10 border border-error/20 p-3 text-sm text-error" role="alert">
     {% for error in login_form.non_field_errors %}<p>{{ error }}</p>{% endfor %}
   </div>
   {% endif %}
   ```
2. **Surface the resend-verification link inside the login partial** when login has failed, regardless of the failure reason (no enumeration). The link is rendered immediately under the non-field-errors block:
   ```django
   {% if login_form.non_field_errors %}
   <p class="text-xs text-on-surface-variant mt-2">
     Didn't receive verification email?
     <a href="{% url 'resend_verification' %}?email={{ login_form.email.value|default:'' }}"
        class="text-secondary font-medium hover:underline">Resend</a>
   </p>
   {% endif %}
   ```
   Pre-filling `?email=` from the submitted value (not from a DB lookup) is safe — it's just echoing what the user typed.
3. **Success messaging.** After clicking the verification link and being logged in, the redirect to `home` should carry a success message. Use Django's `messages` framework (one-line addition; `messages.success(request, 'Email verified — welcome!')` before redirect) and render it once on `base.html` via a small `{% if messages %}` block that fires `showToast` events. This also gives us a clean way to show success toasts on other future flows (account update already uses HX-Trigger toasts; this complements that for full-page redirects).

These fixes are scoped tightly: ~30 lines across two template partials, one base.html addition, and a one-line `messages.success()` call in `confirm_email_view`. They unblock visible error feedback for every state in this feature.

## API contract changes (versioned)

NyasaBlog has a parallel DRF API (`account/api/`, `blog/api/`) consumed by a mobile app. Hard-gating registration/login at the API would break old mobile clients on deploy day. Mitigated via DRF's `AcceptHeaderVersioning`: clients opt in to the new gated contract via `Accept: application/vnd.nyasablog.v2+json`. Default and `v1` preserve the old contract for back-compat.

### Settings change

`mysite/settings.py`:

```python
REST_FRAMEWORK = {
    # ...existing keys...
    'DEFAULT_VERSIONING_CLASS': 'rest_framework.versioning.AcceptHeaderVersioning',
    'DEFAULT_VERSION': '1',
    'ALLOWED_VERSIONS': ['1', '2'],
}
```

Each view checks `request.version` and branches.

### Auth-contract changes (versioned)

| Endpoint | v1 (default, old behavior preserved) | v2 (gated, new behavior) |
|----------|--------------------------------------|--------------------------|
| `POST /api/account/register/` | `is_active=True`, `email_verified=False`, returns auth token immediately, sends verification email | `is_active=False`, `email_verified=False`, **no token returned**, sends verification email; response: `{"response": "verification_email_sent", "email": "..."}` |
| `POST /api/account/login/` | Allows unverified users (preserves working tokens), response now includes `email_verified` field | Rejects unverified users with `{"response": "Error", "error_message": "Email not verified", "error_code": "email_not_verified"}` (HTTP 200, matching existing error pattern in this codebase) |

Even on v1, every new account is created with `email_verified=False`. The verification email is sent regardless of version. v1 clients ignore it; v2 clients prompt the user to verify.

### Additive endpoints (version-agnostic)

These are new, so there's no contract to break — available on any version:

- `POST /api/account/resend-verification/` — body: `{"email": "..."}`. Always returns `{"response": "If that email is registered and unverified, a new link was sent."}` (no enumeration, same wording as the web flow). Internally subject to the same per-email cooldown as the web `resend_verification_view`.
- `POST /api/account/confirm-email/` — body: `{"uid": "<uidb64>", "token": "..."}`. On success: flips `is_active=True, email_verified=True`, returns the user's auth token (so a v2 mobile client can move directly into authenticated state without a separate login round-trip). On failure: returns 400 with a generic error.
- `GET /api/account/properties/` — modify the existing endpoint to include `email_verified` in the response (additive, doesn't break v1 clients).

### `IsEmailVerified` permission class (universal)

Versioning controls the *auth contract* — who can authenticate. A separate permission class controls *what authenticated users can do*. Both layers are needed: without the permission, a v1 client could create an unverified account, get a token, and then comment/post/like, leaving a permanent spam vector for the lifetime of v1.

`account/api/permissions.py`:

```python
from rest_framework import permissions

class IsEmailVerified(permissions.BasePermission):
    message = "Email not verified. Please verify your email to perform this action."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.email_verified)
```

Applied to write/destructive endpoints across the API (combined with `IsAuthenticated`):

- `blog/api/views.py`:
  - `api_create_blog_view` (POST)
  - `api_update_blog_view` (PUT)
  - `api_delete_blog_view` (DELETE)
  - `api_create_comment_view` (POST)
  - `api_delete_comment_view` (DELETE)
  - `api_toggle_like_view` (POST)
  - `api_toggle_bookmark_view` (POST)
- `account/api/views.py`:
  - profile-update endpoint (PUT)
  - change-password endpoint (PUT)

Read endpoints (list posts, view profiles, view comments, list categories/tags) keep `IsAuthenticated`-only or remain public — they're not a spam vector and blocking unverified users from reading is hostile.

The permission returns HTTP 403 with `{"detail": "Email not verified..."}` when a verified-only action is attempted by an unverified account. The mobile team's old client will see this as a generic 403 and probably show "permission denied" — not great UX but not broken. Once the mobile team ships an update aware of `email_verified`, it can prompt the user to verify before attempting the write.

### Mobile migration timeline (informational)

This spec doesn't mandate a timeline, but for context:

1. **Day 0 (this PR ships):** Backend deploys. v1 clients keep working for auth. Unverified writes return 403 (mild regression for active mobile commenters who haven't published — they must verify before commenting again). New API endpoints available. Mobile team can read `email_verified` in `GET /api/account/properties/` and start building UI.
2. **Day 7 (cleanup cron starts impacting):** Unverified accounts older than 7 days begin being purged. Mobile team should ship a "verify your email" prompt before this if they want to retain unverified users.
3. **Day N (separate PR, when mobile is ready):** Either deprecate v1 entirely, or keep it indefinitely for clients that never update. The decision is out of scope for this PR.

The grandfather rule remains "is_staff OR is_superuser OR has any BlogPost." Active mobile commenters/likers who never published are temporarily blocked from writing until they verify. This is a one-time, recoverable cost; the alternative (grandfather all active accounts) would defeat the spam-mitigation goal of the feature.

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
- Everyone else (lurkers, commenters, spam signups): unverified. On the **web** they'll be sent through the verification flow on their next login attempt. On **API v1** they remain logged-in (no login gate), but their existing tokens won't allow write actions until they verify, due to the `IsEmailVerified` permission. On **API v2** their existing tokens will be rejected at login (gated).

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
| `account/views.py` | modify `registration_view`, `login_view`; add `confirm_email_view` (with `messages.success(...)` before home redirect), `resend_verification_view` |
| `account/management/commands/purge_unverified_accounts.py` | new |
| `mysite/urls.py` | + 2 routes |
| `templates/registration/email_verification_subject.txt` | new |
| `templates/registration/email_verification_email.html` | new |
| `templates/account/verification_sent.html` | new |
| `templates/account/verification_invalid.html` | new |
| `account/templates/account/partials/login_form.html` | modify — render `non_field_errors` + resend-verification link block |
| `account/templates/account/partials/register_form.html` | modify — render `non_field_errors` |
| `templates/base.html` | modify — render Django `messages` as `showToast` events on full-page loads |
| `mysite/settings.py` | + DRF versioning config (AcceptHeaderVersioning, v1/v2) |
| `account/api/permissions.py` | new — `IsEmailVerified` |
| `account/api/views.py` | modify `registration_view` and `login_view` to branch on `request.version`; add `resend_verification_view`, `confirm_email_view`; expose `email_verified` in `account_properties_view`; apply `IsEmailVerified` to update/change-password endpoints |
| `account/api/urls.py` | + 2 routes (resend-verification, confirm-email) |
| `account/api/serializers.py` | modify `RegistrationSerializer` to set `is_active=False` on v2 path (or pass via context) |
| `blog/api/views.py` | apply `IsEmailVerified` alongside `IsAuthenticated` on 7 write endpoints |
| `account/tests.py` | + ~34 tests (web + API) |

## Test plan

Automated (`account/tests.py`):

1. `test_registration_creates_inactive_unverified_account`
2. `test_registration_sends_verification_email`
3. `test_registration_does_not_log_user_in`
4. `test_confirm_email_with_valid_token_activates_account`
5. `test_confirm_email_with_invalid_token_shows_error_page`
6. `test_confirm_email_with_expired_token_shows_error_page` (freeze time +4 days)
7. `test_token_invalidated_after_first_use` (second click fails)
8. `test_unverified_user_cannot_log_in` — correct password, generic error visible in response (asserts the rendered HTML contains the error message text and the resend-verification link, not just that login failed silently — guards against the non-field-errors bug returning).
9. `test_resend_verification_sends_new_email_for_unverified_account`
10. `test_resend_verification_silent_for_unknown_or_verified_email` (no enumeration)
11. `test_purge_command_deletes_old_unverified_only` (matrix of 4 accounts)
12. `test_grandfather_migration` (staff, contributor, lurker — assert correct verified state)
13. `test_grandfather_migration_idempotent` — re-running the data migration after an already-verified user has signed up, verified normally, or had their email changed must not regress their state. Asserts `.update()` semantics hold and no user is un-verified by a second run.
14. `test_login_with_wrong_password_for_unverified_account_does_not_send_email` — failed login must never trigger a verification email. Only the explicit resend endpoint sends. Guards against accidentally wiring email-send into the login error path during implementation.
15. `test_purged_email_can_be_reregistered` — create unverified account, age it 8 days, run purge, register a brand-new account with the same email, assert success. Validates the "free up email/username" goal of the cleanup feature end-to-end.
16. `test_resend_rate_limited_within_cooldown` — two POSTs in quick succession; only the first sends mail. Outer response identical. Third POST after `cache.clear()` (or time advance) sends again.
17. `test_failed_login_with_wrong_password_shows_error_message` — pre-existing bug regression test. POST wrong password against an existing verified account; assert the rendered HTML contains the "Invalid login" / "Invalid email or password" message text. Without the non-field-errors fix, the response renders blank.
18. `test_confirm_email_success_sets_messages_framework` — after clicking valid link, `messages.success` is queued with the welcome text. Asserts the message exists in `messages` middleware storage on the redirect response.

API-layer tests (live in `account/tests.py` alongside existing `RegistrationAPITests`/`LoginAPITests` classes):

19. `test_api_register_v1_returns_token_and_unverified` — default `Accept` header. Account created with `email_verified=False, is_active=True`. Token returned. Verification email sent.
20. `test_api_register_v2_no_token_unverified_inactive` — `Accept: application/vnd.nyasablog.v2+json`. No token in response. `is_active=False`. Verification email sent.
21. `test_api_login_v1_allows_unverified_user_with_email_verified_field` — v1 login of an unverified user succeeds; response includes `email_verified: false`.
22. `test_api_login_v2_rejects_unverified_with_error_code` — v2 login of unverified user returns `error_code: "email_not_verified"`; no token.
23. `test_api_login_v2_succeeds_for_verified_user` — sanity check that v2 isn't broken for the happy path.
24. `test_api_resend_verification_sends_for_unverified_account` — POST email of unverified account; outbox grows by 1; same generic response as silent path.
25. `test_api_resend_verification_silent_for_unknown_or_verified` — POST unknown email or already-verified email; outbox stays empty; same response.
26. `test_api_resend_verification_rate_limited` — two POSTs in cooldown window send only one email; same response either way.
27. `test_api_confirm_email_valid_token_returns_token` — POST `{uid, token}` with a valid pair; account becomes verified+active; auth token returned in response.
28. `test_api_confirm_email_invalid_token_returns_400` — bad token; HTTP 400 with generic error.
29. `test_api_properties_includes_email_verified_field` — `GET /api/account/properties/` returns `email_verified` in the body for both v1 and v2 (additive on v1).
30. `test_is_email_verified_permission_blocks_unverified_create_post` — authenticated unverified user POSTs to `api_create_blog_view`; HTTP 403 with the `IsEmailVerified` message; no BlogPost created.
31. `test_is_email_verified_permission_blocks_unverified_create_comment` — same shape, on `api_create_comment_view`.
32. `test_is_email_verified_permission_blocks_unverified_toggle_like` — same shape, on `api_toggle_like_view`.
33. `test_is_email_verified_permission_allows_verified_user_to_post` — sanity — verified user can post.
34. `test_is_email_verified_permission_does_not_block_read_endpoints` — unverified user can still GET blog detail, comments list, categories, etc.

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
- **Bundle the `non_field_errors` rendering fix into this feature.** The login partial currently swallows non-field validation errors silently — wrong-password users see a blank re-render today. Shipping verification on top of that means *every* new error state we add (expired link, unverified-login attempt, rate-limit hit) inherits the silent failure. The fix is ~30 lines and one base.html change. Pulling it into this feature trades a small scope expansion for not shipping a feature whose error UX is broken on day one. The alternative — file the bug separately and ship verification regardless — was rejected because it would make this feature visibly worse than what's there today.
- **Versioned API contract via `Accept` header (v1 default, v2 gated).** A mobile app currently consumes the API and expects an immediate token on registration. A hard cutover would break old mobile clients on deploy day. Versioning lets the backend ship now and the mobile team migrate on its own schedule. C was chosen over a phased additive-then-breaking approach (option B) because it makes the contract change explicit per request — clients opt in. Rejected: hard cutover (option A — couples backend release to mobile), and "no API gate at all" (leaves a permanent spam vector).
- **`IsEmailVerified` permission separate from versioning.** Versioning controls who can authenticate, but a v1 client could otherwise still get a token, stay on v1, and write spam indefinitely. The permission class gates *write actions* universally, regardless of API version. Read endpoints stay open to keep unverified users able to browse content while they're prompted to verify. Active mobile commenters who never published are temporarily blocked from writing until they verify (one-time, recoverable cost — covered in the mobile migration timeline section).
- **Grandfather rule stays "posts only"; commenters/likers do not auto-grandfather.** Considered widening to anyone with any user action (comment, like, bookmark) so active mobile lurkers wouldn't be blocked. Rejected because (a) the verification gate is explicitly forward-looking spam mitigation, (b) commenters/likers can always recover by verifying their email — there's no permanent loss of state, just a one-time prompt, and (c) widening the grandfather rule weakens the gate against any pre-existing spam accounts that liked or commented before.

## Out of scope

- Social/OAuth signup (no Google/Facebook login currently).
- Changing email after signup (would need re-verification — separate feature).
- IP-based rate limiting (per-email cooldown is in scope and is the meaningful defence; per-IP is trivially circumvented and adds complexity for marginal value).
- 2FA / MFA.
- API v1 deprecation/removal (kept indefinitely in this PR for back-compat; deprecation timing is a future decision driven by mobile team adoption).
