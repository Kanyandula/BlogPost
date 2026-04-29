from rest_framework import permissions


class IsEmailVerified(permissions.BasePermission):
    """Allow only authenticated users whose email has been verified."""
    message = "Email not verified. Please verify your email to perform this action."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and getattr(request.user, 'email_verified', False)
        )
