from rest_framework import status
from rest_framework.response import Response
from rest_framework.decorators import api_view,permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.generics import UpdateAPIView
from django.contrib.auth import authenticate
from django.core.cache import cache
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from rest_framework.authentication import TokenAuthentication
from rest_framework.decorators import api_view, authentication_classes, permission_classes

from account.api.permissions import IsEmailVerified
from account.api.serializers import RegistrationSerializer, AccountPropertiesSerializer, ChangePasswordSerializer, UserProfileSerializer
from account.emails import send_verification_email
from account.models import Account, UserProfile
from account.tokens import email_verification_token
from account.views import _can_send_resend  # reuse the cooldown helper from web view
from rest_framework.authtoken.models import Token
from django.db.models import Sum, Count


# Register
# Url: https://<your-domain>/api/account/register
@api_view(['POST', ])
@permission_classes([])
@authentication_classes([])
def registration_view(request):

	if request.method == 'POST':
		data = {}
		email = request.data.get('email', '0').lower()
		if validate_email(email) != None:
			data['error_message'] = 'That email is already in use.'
			data['response'] = 'Error'
			return Response(data)

		username = request.data.get('username', '0')
		if validate_username(username) != None:
			data['error_message'] = 'That username is already in use.'
			data['response'] = 'Error'
			return Response(data)

		is_v2 = (request.version == '2')
		serializer = RegistrationSerializer(data=request.data, context={'is_active': not is_v2})

		if serializer.is_valid():
			account = serializer.save()
			send_verification_email(account, request)
			if is_v2:
				data['response'] = 'verification_email_sent'
				data['email'] = account.email
				data['email_verified'] = False
			else:
				data['response'] = 'successfully registered new user.'
				data['email'] = account.email
				data['username'] = account.username
				data['pk'] = account.pk
				data['email_verified'] = False
				token = Token.objects.get(user=account).key
				data['token'] = token
		else:
			data = serializer.errors
		return Response(data)

def validate_email(email):
	account = None
	try:
		account = Account.objects.get(email=email)
	except Account.DoesNotExist:
		return None
	if account != None:
		return email

def validate_username(username):
	account = None
	try:
		account = Account.objects.get(username=username)
	except Account.DoesNotExist:
		return None
	if account != None:
		return username		


@api_view(['GET', ])
@permission_classes((IsAuthenticated, ))
def account_properties_view(request):

	try:
		account = request.user
	except Account.DoesNotExist:
		return Response(status=status.HTTP_404_NOT_FOUND)

	if request.method == 'GET':
		serializer = AccountPropertiesSerializer(account)
		return Response(serializer.data)


@api_view(['PUT',])
@permission_classes((IsAuthenticated, IsEmailVerified))
def update_account_view(request):

	try:
		account = request.user
	except Account.DoesNotExist:
		return Response(status=status.HTTP_404_NOT_FOUND)
		
	if request.method == 'PUT':
		serializer = AccountPropertiesSerializer(account, data=request.data)
		data = {}
		if serializer.is_valid():
			serializer.save()
			data['response'] = 'Account update success'
			return Response(data=data)
		return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
		


# LOGIN
# URL: http://127.0.0.1:8000/api/account/login
class ObtainAuthTokenView(APIView):

	authentication_classes = []
	permission_classes = []

	def post(self, request):
		context = {}

		email = request.data.get('username', '')
		password = request.data.get('password', '')
		is_v2 = (request.version == '2')
		account = authenticate(email=email, password=password)

		if account is None:
			# Maybe inactive-unverified - check manually so v2 can give the right error code.
			candidate = Account.objects.filter(email__iexact=email).first()
			if candidate and candidate.check_password(password) and not candidate.email_verified:
				if is_v2:
					return Response({
						'response': 'Error',
						'error_message': 'Email not verified',
						'error_code': 'email_not_verified',
					})
			return Response({'response': 'Error', 'error_message': 'Invalid credentials'})

		if is_v2 and not account.email_verified:
			return Response({
				'response': 'Error',
				'error_message': 'Email not verified',
				'error_code': 'email_not_verified',
			})

		token, _ = Token.objects.get_or_create(user=account)
		return Response({
			'response': 'Successfully authenticated.',
			'pk': account.pk,
			'email': account.email,
			'token': token.key,
			'email_verified': account.email_verified,
		})

@api_view(['GET', ])
@permission_classes([])
@authentication_classes([])
def does_account_exist_view(request):

	if request.method == 'GET':
		email = request.GET['email'].lower()
		data = {}
		try:
			account = Account.objects.get(email=email)
			data['response'] = email
		except Account.DoesNotExist:
			data['response'] = "Account does not exist"
		return Response(data)



class ChangePasswordView(UpdateAPIView):

	serializer_class = ChangePasswordSerializer
	model = Account
	permission_classes = (IsAuthenticated, IsEmailVerified)
	authentication_classes = (TokenAuthentication,)

	def get_object(self, queryset=None):
		obj = self.request.user
		return obj

	def update(self, request, *args, **kwargs):
		self.object = self.get_object()
		serializer = self.get_serializer(data=request.data)

		if serializer.is_valid():
			# Check old password
			if not self.object.check_password(serializer.data.get("old_password")):
				return Response({"old_password": ["Wrong password."]}, status=status.HTTP_400_BAD_REQUEST)

			# confirm the new passwords match
			new_password = serializer.data.get("new_password")
			confirm_new_password = serializer.data.get("confirm_new_password")
			if new_password != confirm_new_password:
				return Response({"new_password": ["New passwords must match"]}, status=status.HTTP_400_BAD_REQUEST)

			# set_password also hashes the password that the user will get
			self.object.set_password(serializer.data.get("new_password"))
			self.object.save()
			return Response({"response":"successfully changed password"}, status=status.HTTP_200_OK)

		return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([])
def api_author_profile_view(request, username):
	try:
		account = Account.objects.select_related('profile').get(username=username)
	except Account.DoesNotExist:
		return Response(status=status.HTTP_404_NOT_FOUND)

	from blog.models import BlogPost
	posts = BlogPost.objects.filter(author=account, status='published')
	stats = posts.aggregate(
		total_views=Sum('view_count'),
		post_count=Count('id'),
	)

	profile_data = UserProfileSerializer(account.profile).data
	profile_data['post_count'] = stats['post_count']
	profile_data['total_views'] = stats['total_views'] or 0
	return Response(profile_data)


@api_view(['PUT'])
@permission_classes((IsAuthenticated, IsEmailVerified))
def api_update_profile_view(request):
	profile = request.user.profile
	serializer = UserProfileSerializer(profile, data=request.data, partial=True)
	if serializer.is_valid():
		serializer.save()
		return Response(serializer.data)
	return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST', ])
@permission_classes([])
@authentication_classes([])
def api_confirm_email_view(request):
	uidb64 = request.data.get('uid')
	token = request.data.get('token')
	if not uidb64 or not token:
		return Response({'error_message': 'uid and token are required.'}, status=status.HTTP_400_BAD_REQUEST)
	try:
		uid = force_str(urlsafe_base64_decode(uidb64))
		account = Account.objects.get(pk=uid)
	except (TypeError, ValueError, OverflowError, Account.DoesNotExist):
		return Response({'error_message': 'Invalid link.'}, status=status.HTTP_400_BAD_REQUEST)
	# Idempotency: a retried confirm on an already-verified account returns the existing token
	# rather than 400. Mobile clients on flaky networks retry; one-shot 400 punishes legit users.
	if account.email_verified:
		auth_token, _ = Token.objects.get_or_create(user=account)
		return Response({'response': 'Email verified.', 'token': auth_token.key,
						 'email': account.email, 'pk': account.pk})
	if not email_verification_token.check_token(account, token):
		return Response({'error_message': 'Invalid or expired link.'}, status=status.HTTP_400_BAD_REQUEST)
	account.is_active = True
	account.email_verified = True
	account.save()
	auth_token, _ = Token.objects.get_or_create(user=account)
	return Response({'response': 'Email verified.', 'token': auth_token.key,
					 'email': account.email, 'pk': account.pk})


@api_view(['POST', ])
@permission_classes([])
@authentication_classes([])
def api_resend_verification_view(request):
	email = (request.data.get('email') or '').strip().lower()
	response_body = {'response': 'If that email is registered and unverified, a new link was sent.'}
	if email:
		try:
			account = Account.objects.get(email__iexact=email, email_verified=False)
			if _can_send_resend(email):
				try:
					send_verification_email(account, request)
				except Exception:
					# Release the cooldown so the user can retry on transient SMTP failure.
					cache.delete(f"resend_cooldown:{email}")
					raise
		except Account.DoesNotExist:
			pass
	return Response(response_body)
