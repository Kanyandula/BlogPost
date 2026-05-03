from functools import wraps
from urllib.parse import urlencode

from django.shortcuts import redirect
from django.urls import reverse


def email_verified_required(view_func):
    """Web-view decorator that gates write actions on email verification.

    Apply *after* @login_required (closer to the function). Anonymous users are
    redirected to login by login_required first; authenticated-but-unverified
    users land on verification_sent so they can request a fresh link.
    """

    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if request.user.is_authenticated and not request.user.email_verified:
            target = f"{reverse('verification_sent')}?{urlencode({'email': request.user.email})}"
            return redirect(target)
        return view_func(request, *args, **kwargs)

    return _wrapped
