# NyasaBlog — project context

Django site at **nyasablog.com**, run by Ephraim Kanyandula. Promotes positive
Malawian content (Culture, Entertainment, Tourism, Tech, Sports, etc.).
WhatsApp sharing is the dominant social channel — never deprioritize it.

## Stack

- Django 5.2 LTS, DRF 3.17, CKEditor 5, SQLite, Python 3.12
- Tailwind CSS — **compiled** (not CDN). After template changes, run
  `npm run build:css` so the production CSS file picks up new utility classes.
- Repo: `github.com/Kanyandula/BlogPost`
- Local checkout: this directory (`~/PycharmProjects/nyasablog/`)

## Hosting

- DigitalOcean Droplet, AMS3, Ubuntu 20.04, 1 GB RAM
- IP `104.248.204.211`; SSH as `root` with ed25519 key
- Gunicorn 25.3 behind Nginx; SSL via Let's Encrypt
- **DO Spaces (S3) serves static & media in production.** A `rsync`-only deploy
  will NOT update CSS/JS — you must also run `collectstatic` so new assets land
  in the bucket. If a CSS change "doesn't take" in prod, this is why.
- Postgres upgrade is blocked: Ubuntu 20.04 ships PG12, Django 5.2 needs PG14+.
  Droplet OS upgrade has to come first.

## Configuration files

- python-decouple reads `settings.ini` **first**, then falls back to `.env`.
  Production currently has both files, so `settings.ini` is the active source
  of truth — any `.env` edits are silently inert until `settings.ini` is
  removed. Consolidating to `.env` requires rotating `SECRET_KEY` (the two
  files have different values) and a planned mass-logout. Until that
  migration, **edit `settings.ini` on the Droplet**, not `.env`.
- Local dev uses `settings.ini` only (`.env` doesn't exist locally).

## Deploy workflow

- `rsync` source up, **always** with `--exclude=.env --exclude=settings.ini`
  (and other secrets) — never overwrite production config.
- `chown -R ephraim:www-data .` after rsync so Gunicorn can read.
- `systemctl restart gunicorn` to pick up Python changes.
- For static/CSS changes: `python manage.py collectstatic --noinput` to push to
  DO Spaces.
- Use the `nyasablog-deploy` skill when available — it bundles this sequence.

## CI/CD

- GitHub Actions: `ci.yml` (tests + ruff) and `security.yml` (deps + audit).
- Composite action under `.github/actions/`. As of 2026-05-05, 8/9 checks pass;
  ruff cleanup is the outstanding gap.

## Audit-driven hardening (2026-05)

- Auth: removed `AllowAllUsersModelBackend`; HTTPS + email-domain config in;
  email verification gates registration. (PR #35.)
- Search uses M2M AND semantics (PRs #39–40, 242 tests).
- Two API v1 findings (`api_register_v1` keeps `is_active=True`,
  `does_account_exist` enumeration oracle, `api_confirm_email` token disclosure)
  are **deferred to a coordinated v1-deprecation PR**, not silently fixed —
  WebView consumers depend on current v1 behavior. Do not patch them ad hoc.

## Conventions

- Marketing-style pages with cards/chips need **structured fields** (multiple
  named text/image fields), not a single CKEditor body. Editors paste rich
  content and chips end up as `<p>` blobs otherwise.
- Dark mode is implemented via CSS custom properties that swap Tailwind color
  tokens — don't introduce hard-coded colors.
- WhatsApp share button is first-class on every shareable surface.

## Open threads

- Dependabot npm-side vulns (PostCSS GHSA-qx2v-qp2m-jg93 was moderate; transitive
  deps need triage). Python deps are clean (Django 5.2.12 LTS, all packages
  CVE-free as of last audit).
- Newsletter subscription backend (PR #21) merge + deploy.
- Notifications + follow-system features.
- Dropdown UX polish.

## Don't re-derive

If you need historical PR context (PRs #16–42), check `git log` and
`recent.md` in `~/.remember/`. Don't re-summarize the audit history into
this file — it grows stale.
