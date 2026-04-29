from django.core.mail import EmailMessage
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
    body = render_to_string('registration/email_verification_email.txt', context)
    msg = EmailMessage(subject=subject, body=body, to=[user.email])
    msg.send()
