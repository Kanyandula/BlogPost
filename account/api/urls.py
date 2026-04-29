from django.urls import path
from account.api.views import(
	registration_view,
	ObtainAuthTokenView,
	account_properties_view,
	update_account_view,
	does_account_exist_view,
	ChangePasswordView,
	api_author_profile_view,
	api_update_profile_view,
	api_resend_verification_view,
	api_confirm_email_view,
)
from rest_framework.authtoken.views import obtain_auth_token

app_name = 'account'

urlpatterns = [
	path('check_if_account_exists/', does_account_exist_view, name="check_if_account_exists"),
	path('change_password/', ChangePasswordView.as_view(), name="change_password"),
	path('properties', account_properties_view, name="properties"),
	path('properties/update', update_account_view, name="update"),
 	path('login', ObtainAuthTokenView.as_view(), name="login"),
	path('register', registration_view, name="register"),
	path('profile/update/', api_update_profile_view, name="update_profile"),
	path('profile/<str:username>/', api_author_profile_view, name="author_profile"),
	path('resend-verification/', api_resend_verification_view, name="resend_verification"),
	path('confirm-email/', api_confirm_email_view, name="confirm_email"),
]
