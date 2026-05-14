from django.conf import settings
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from account.tokens import email_verification_token


def send_verification_email(user, request=None):
    """Send the email-verification link to `user`.

    Domain and protocol are pulled from settings (SITE_DOMAIN, SITE_PROTOCOL) rather
    than the inbound request, so a forged Host header cannot redirect the link to
    an attacker-controlled domain. `request` is accepted but unused; kept for
    backward compatibility with existing callers.
    """
    context = {
        'user': user,
        'domain': settings.SITE_DOMAIN,
        'protocol': settings.SITE_PROTOCOL,
        'uid': urlsafe_base64_encode(force_bytes(user.pk)),
        'token': email_verification_token.make_token(user),
    }
    subject = render_to_string('registration/email_verification_subject.txt', context).strip()
    body = render_to_string('registration/email_verification_email.txt', context)
    msg = EmailMessage(
        subject=subject,
        body=body,
        to=[user.email],
        reply_to=[settings.SUPPORT_EMAIL],
    )
    # Anymail-native fields: ignored by non-ESP backends, used by Postmark to
    # surface this message in the Activity dashboard and webhook payloads.
    # Postmark allows AT MOST ONE tag per message — adding a second raises
    # AnymailUnsupportedFeature at send time; use metadata for finer-grained
    # categorization.
    msg.tags = ['email-verification']
    msg.metadata = {'user_id': str(user.pk)}
    msg.send()
