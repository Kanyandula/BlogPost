# Email deliverability — follow-up

**Status:** Paused. Pick up when ready.

## Context

The email-verification feature shipped end-to-end and the SMTP plumbing technically works (Gmail accepts the messages — `send_mail` returns `1`). But **delivery to recipient inboxes is unreliable**: at least one new signup (`findyourlawyer265@gmail.com`, pk=155) never received any of the verification emails sent from production, even though every send was logged as successful at the SMTP layer.

## Why the current setup is unreliable

The production SMTP relay is `smtp.gmail.com` authenticated as `khayamalawi@gmail.com` (a personal Gmail account, not Google Workspace). This pattern is structurally fragile:

| Issue | Impact |
|---|---|
| New Gmail account suddenly sending automated mail | Receivers (especially other Gmail) treat as spammy |
| `From: NyasaBlog <khayamalawi@gmail.com>` — DKIM signed for `gmail.com`, not `nyasablog.com` | Domain alignment fails, score drops |
| No SPF record for `nyasablog.com` | No DNS proof Gmail is authorized to send for us |
| No DMARC record | No policy telling receivers what to do with unsigned mail "from" us |
| Free Gmail SMTP cap ≈ 100–500 messages/day | Will be hit on a busy day |

## Recommended fix — switch to a transactional email provider

Default pick: **Resend** (3,000/month free tier, simplest setup). Backup: **Postmark** (100/day forever, strongest deliverability track record). Either solves all the issues above with one DNS-record set + one SMTP credential swap.

## Migration steps (when picking this back up)

### User-side (cannot be done by me)
1. Sign up at <https://resend.com> (or Postmark / SendGrid).
2. Add `nyasablog.com` as a sender domain. The provider will give you 3–5 DNS records (SPF TXT, DKIM CNAMEs, optional DMARC).
3. Add those records in DigitalOcean DNS for `nyasablog.com`. Wait for verification (usually <15 min).
4. Generate an API key / SMTP credentials.
5. Decide on a sender address (e.g. `noreply@nyasablog.com`).

### Claude-side (once user provides creds + sender address)
6. Update `/home/ephraim/djangoprojectdir/settings.ini` (and `.env` for parity):
   ```
   EMAIL_HOST=smtp.resend.com           # or smtp.postmarkapp.com / smtp.sendgrid.net
   EMAIL_HOST_USER=resend               # provider-specific username
   EMAIL_HOST_PASSWORD=<api-key>
   EMAIL_PORT=587
   EMAIL_USE_TLS=True
   DEFAULT_FROM_EMAIL=NyasaBlog <noreply@nyasablog.com>
   ```
7. `systemctl stop gunicorn && systemctl start gunicorn` (NOT `restart` — see runbook lessons).
8. Smoke test: send to a non-Gmail address (Outlook, Yahoo, ProtonMail). Those are the harder targets — if they land, Gmail will too.
9. Once verified, also retire the Gmail App Password at <https://myaccount.google.com/apppasswords>.

## Open items unrelated to deliverability

- **pk=155 (`findyourlawyer265@gmail.com`, username `Andrew`)** — currently `is_active=False, email_verified=False`. After the email-provider migration, hit `/resend-verification/` for this account; the user should receive the link reliably and can self-verify. If they need to be unblocked before the migration is done, manual override is acceptable for this account specifically (`Account.objects.filter(pk=155).update(is_active=True, email_verified=True)`) since the SMTP sender owner already proved control of the recipient mailbox indirectly.

## Lessons baked in from the original deploy

- After editing `.env` or `settings.ini`, use `systemctl stop gunicorn && systemctl start gunicorn` — not `restart`. Workers don't always pick up env changes through `restart`.
- 1GB swap added to the Droplet (already persisted in `/etc/fstab`).
- `EMAIL_TIMEOUT = 10` in `mysite/settings.py` — fails fast on hung SMTP connects (commit `256e942`).
- `python-decouple` reads both `.env` and `settings.ini`; for keys present in both, **`settings.ini` wins**. When updating credentials, change BOTH files or just go through `settings.ini`.

## Reference

- Spec: `docs/superpowers/specs/2026-04-29-email-verification-design.md`
- Plan: `docs/superpowers/plans/2026-04-29-email-verification.md`
- Cron runbook: `docs/superpowers/runbooks/email-verification-purge-cron.md`
