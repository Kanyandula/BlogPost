# `purge_unverified_accounts` cron installation

The email-verification feature relies on a daily cron job that deletes unverified accounts older than 7 days. This runbook documents the install steps.

## Install

SSH to the production Droplet and edit `ephraim`'s crontab:

```bash
ssh root@104.248.204.211
sudo -u ephraim crontab -e
```

Add this entry (replace the venv path if different — verify with `which python` after activating the env):

```
0 3 * * * cd /home/ephraim/djangoprojectdir && /home/ephraim/djangoprojectenv/bin/python manage.py purge_unverified_accounts >> /var/log/nyasablog/purge.log 2>&1
```

Runs daily at 03:00 UTC (~05:00 in Malawi).

## Verify

```bash
sudo -u ephraim crontab -l                                        # confirm entry is present
ls -ld /var/log/nyasablog                                         # confirm log dir exists, ephraim-writable
sudo -u ephraim /home/ephraim/djangoprojectenv/bin/python /home/ephraim/djangoprojectdir/manage.py purge_unverified_accounts --dry-run
```

The `--dry-run` invocation should print `[DRY RUN] cutoff=... — Would delete N unverified accounts` without deleting anything.

## Log rotation

Add `/etc/logrotate.d/nyasablog-purge`:

```
/var/log/nyasablog/purge.log {
    weekly
    rotate 8
    compress
    missingok
    notifempty
    copytruncate
}
```

Without rotation the log will grow forever.

## Rate-limit cache backend (related concern)

The web `resend_verification_view` and API `api_resend_verification_view` use Django's default `LocMemCache` for the per-email cooldown. This is per-process, so multi-worker Gunicorn would have separate cooldown counters per worker — effectively dividing the cooldown window by N. If Gunicorn ever runs with `--workers > 1`, switch to filesystem cache before deploying:

```python
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.filebased.FileBasedCache',
        'LOCATION': '/var/tmp/nyasablog_cache',
    }
}
```

Verify Gunicorn config:

```bash
ssh root@104.248.204.211 "systemctl cat gunicorn | grep -i workers"
```

If `--workers 1` (single worker, current default for 1GB Droplet), no action needed.

## ALLOWED_HOSTS hygiene

`request.build_absolute_uri()` (used to construct verification links in `account/emails.py`) trusts the `Host` header. Production `ALLOWED_HOSTS` MUST NOT include `'*'`. Confirm before deploy:

```bash
ssh root@104.248.204.211 "grep ALLOWED_HOSTS /home/ephraim/djangoprojectdir/mysite/settings.py"
```

Expected: `ALLOWED_HOSTS = ['nyasablog.com', 'www.nyasablog.com']` or equivalent tight list.

## Manual smoke test (post-deploy)

1. Register a fresh email at https://nyasablog.com/register/ — should redirect to "Check your inbox" page.
2. Receive email; click verification link — should land logged in on home with toast "Email verified".
3. Try to log in pre-verification (separate account) — should see "Invalid email or password." inline + "Resend" link.
4. Click Resend — should receive a new email.
5. (24-48 hours later) confirm `purge.log` has a `[DRY RUN]` or `Deleted` line from the daily cron.
