# Postmark backend deploy (django-anymail)

Switching production transactional email from Gmail SMTP to Postmark via
`django-anymail`. This is a one-shot operation; do not run repeatedly.

> **Important — config file:** This runbook references `.env`, but production
> currently uses **`settings.ini`** (python-decouple prefers it over `.env`
> when both exist). Replace every `.env` mention below with `settings.ini`
> until the consolidation ticket lands. The keys and values are identical;
> only the file path and INI section header (`[settings]` at the top) differ.

## Pre-flight

1. **Postmark account approved.** Postmark UI top bar must NOT show "Test mode"
   or "We're reviewing your account."
2. **DNS resolves.** `dig @8.8.8.8` for all four:
   - `TXT 20260513155127pm._domainkey.nyasablog.com` (DKIM)
   - `CNAME pm-bounces.nyasablog.com` → `pm.mtasv.net` (Return-Path)
   - `TXT _dmarc.nyasablog.com` (DMARC)
   - DKIM + Return-Path both **Verified** in Postmark UI → Domains.
3. **Fresh production server token generated.** Postmark UI → Servers → My
   First Server → API Tokens → Add Token → name it `prod`. Don't reuse the
   dev/local token already in Keychain (different rotation cycles).

## Deploy steps

### 1. SSH and back up the current `.env`

```bash
ssh root@104.248.204.211
cd /home/ephraim/djangoprojectdir
cp .env .env.pre-postmark.$(date +%Y%m%d)
chmod 600 .env.pre-postmark.*
```

### 2. Edit `.env`

**Add:**
```
POSTMARK_SERVER_TOKEN=<paste prod token from Postmark UI>
SUPPORT_EMAIL=hello@nyasablog.com
```

**Change:**
```
DEFAULT_FROM_EMAIL=NyasaBlog <hello@nyasablog.com>
```
(was `khayamalawi@gmail.com`)

**Comment out (do NOT delete — kept for fast rollback):**
```
# EMAIL_HOST=smtp.gmail.com
# EMAIL_HOST_USER=khayamalawi@gmail.com
# EMAIL_HOST_PASSWORD=...
# EMAIL_PORT=587
# EMAIL_USE_TLS=True
```

Confirm permissions: `chmod 600 .env`.

### 3. Deploy code

Use the `nyasablog-deploy` skill, or manual rsync (with `--exclude=.env`).
The new `EMAIL_BACKEND` and `ANYMAIL` config ship with the deploy.

### 4. Install dependency on the server

```bash
sudo -u ephraim /home/ephraim/djangoprojectdir/djangoprojectenv/bin/pip install -r /home/ephraim/djangoprojectdir/requirements.txt
```

This pulls in `django-anymail[postmark]==15.0`.

### 5. Validate config before restarting Gunicorn

```bash
sudo -u ephraim /home/ephraim/djangoprojectdir/djangoprojectenv/bin/python /home/ephraim/djangoprojectdir/manage.py check --deploy
```

The startup guard added in `mysite/settings.py` will raise `ImproperlyConfigured`
if `POSTMARK_SERVER_TOKEN` is missing — fix the `.env` and re-run.

### 6. Restart Gunicorn

```bash
systemctl restart gunicorn
systemctl status gunicorn   # confirm active (running), no recent error logs
```

If Gunicorn fails to start, check `journalctl -u gunicorn -n 50`. The most
likely cause is an empty `POSTMARK_SERVER_TOKEN` — settings.py refuses to
load in that state by design.

## Smoke test

1. Register a brand-new test account at https://nyasablog.com/register/ with
   a throwaway email you control.
2. Within ~30s, verify the email arrives in **Inbox** (not Spam) with
   From: `NyasaBlog <hello@nyasablog.com>`.
3. Gmail → ⋮ → **Show Original**. Confirm all three:
   - DKIM **PASS** on `nyasablog.com` selector `20260513155127pm`
   - SPF **PASS** via `pm-bounces.nyasablog.com`
   - DMARC **PASS**
4. Click the verification link → account activates → can log in.
5. Postmark UI → Servers → Activity tab: confirm message tagged
   `email-verification` with metadata `user_id=<pk>`.

If any auth check FAILs, **roll back immediately** — DMARC alignment is the
load-bearing piece for the migration.

## Rollback

Because `EMAIL_BACKEND` is env-controlled, rollback is `.env`-only. No code
revert, no redeploy.

**Total rollback time: <2 minutes** with the `.env.pre-postmark.*` backup.

1. SSH to Droplet:
   ```bash
   ssh root@104.248.204.211
   cd /home/ephraim/djangoprojectdir
   ```
2. Restore the backup:
   ```bash
   cp .env.pre-postmark.<YYYYMMDD> .env
   chmod 600 .env
   ```
   If the backup is missing, edit `.env` directly and add:
   ```
   EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
   EMAIL_HOST=smtp.gmail.com
   EMAIL_HOST_USER=khayamalawi@gmail.com
   EMAIL_HOST_PASSWORD=<app password — generate fresh if Step 8 already ran>
   EMAIL_PORT=587
   EMAIL_USE_TLS=True
   DEFAULT_FROM_EMAIL=NyasaBlog <khayamalawi@gmail.com>
   ```
3. Restart Gunicorn: `systemctl restart gunicorn`
4. Trigger a registration in incognito and confirm mail arrives.

**If the Gmail app password was already revoked** (post-deploy step below),
generate a new one at https://myaccount.google.com/apppasswords. Adds
~2 minutes to rollback.

## Post-deploy

After the smoke test passes:

1. **Delete the throwaway test account** via Django admin or
   `manage.py shell`:
   ```bash
   sudo -u ephraim /home/ephraim/djangoprojectdir/djangoprojectenv/bin/python /home/ephraim/djangoprojectdir/manage.py shell -c "from account.models import Account; Account.objects.filter(email='<throwaway>').delete()"
   ```
2. **Revoke the Gmail app password** used by `khayamalawi@gmail.com` for
   SMTP: Google account → Security → App passwords → revoke. Least-privilege
   hygiene; the credential is no longer used.
3. **Schedule cleanup PR ~30 days out** (Task 9 of the migration plan):
   delete commented-out SMTP env vars from `.env`, delete the
   `.env.pre-postmark.*` backup on the Droplet, drop the SMTP `config()`
   reads from `settings.py`.
