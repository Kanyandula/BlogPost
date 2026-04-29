from urllib.parse import urlencode

from django.contrib import messages
from django.core.cache import cache
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, logout
from django.http import HttpResponse
from django.urls import reverse
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode

from account.emails import send_verification_email
from account.forms import RegistrationForm, AccountAuthenticationForm, AccountUpdateForm
from account.models import Account
from account.tokens import email_verification_token
from django.db.models import Count, Sum
from blog.models import BlogPost
from blog.utils import trigger_toast



def registration_view(request):
	context = {}
	if request.POST:
		form = RegistrationForm(request.POST)
		if form.is_valid():
			account = form.save(commit=False)
			account.is_active = False
			account.save()
			email = form.cleaned_data.get('email').lower()
			send_verification_email(account, request)
			target = f"{reverse('verification_sent')}?{urlencode({'email': email})}"
			if getattr(request, 'htmx', False):
				response = HttpResponse(status=204)
				response['HX-Redirect'] = target
				return response
			return redirect(target)
		else:
			context['registration_form'] = form
			if getattr(request, 'htmx', False):
				return render(request, 'account/partials/register_form.html', context)
	else:
		form = RegistrationForm()
		context['registration_form'] = form
	return render(request, 'account/register.html', context)


def verification_sent_view(request):
	return render(request, 'account/verification_sent.html', {'email': request.GET.get('email', '')})


def _can_send_resend(email: str) -> bool:
	"""Reserve the cooldown slot for `email` (lowercased), or refuse if still in cooldown."""
	key = f"resend_cooldown:{email.lower()}"
	if cache.get(key):
		return False
	cache.set(key, True, timeout=60)
	return True


def resend_verification_view(request):
	if request.method == 'POST':
		email = (request.POST.get('email') or '').strip()
		if email:
			email_lower = email.lower()
			try:
				account = Account.objects.get(email__iexact=email_lower, email_verified=False)
				if _can_send_resend(email_lower):
					try:
						send_verification_email(account, request)
					except Exception:  # pylint: disable=broad-except
						# Release the cooldown so the user can retry on transient SMTP failure.
						# Bare except is intentional: send() can raise SMTPException, socket.error,
						# ConnectionRefusedError, etc. Re-allowing one retry is safer than enumerating.
						cache.delete(f"resend_cooldown:{email_lower}")
						raise
			except Account.DoesNotExist:
				pass  # silent — no enumeration
		# Always render the same response, regardless of state.
		return render(request, 'account/verification_sent.html',
		              {'email': email, 'resend': True})

	# GET — render the form (reuses verification_invalid.html which has an embedded resend form)
	prefill = request.GET.get('email', '')
	return render(request, 'account/verification_invalid.html', {'email': prefill})


def confirm_email_view(request, uidb64, token):
	try:
		uid = force_str(urlsafe_base64_decode(uidb64))
		account = Account.objects.get(pk=uid)
	except (TypeError, ValueError, OverflowError, Account.DoesNotExist):
		return render(request, 'account/verification_invalid.html')

	if account.email_verified:
		messages.info(request, 'Your email is already verified. Please log in.')
		return redirect('login')

	if email_verification_token.check_token(account, token):
		account.is_active = True
		account.email_verified = True
		account.save()
		login(request, account, backend='account.backends.CaseInsensitiveModelBackend')
		messages.success(request, 'Email verified — welcome to NyasaBlog!')
		return redirect('home')

	return render(request, 'account/verification_invalid.html')


def logout_view(request):
	logout(request)
	return redirect('/')


def login_view(request):
	context = {}

	user = request.user
	if user.is_authenticated:
		return redirect("home")

	if request.POST:
		form = AccountAuthenticationForm(request.POST)
		if form.is_valid():
			email = request.POST['email']
			password = request.POST['password']
			user = authenticate(email=email, password=password)
			# AUTHENTICATION_BACKENDS lists AllowAllUsersModelBackend first, which lets
			# inactive users through authenticate(). The email_verified check below is
			# therefore the *sole* gate for the web login flow — don't drop it without
			# also re-evaluating the backend config.
			if user and user.email_verified:
				login(request, user)
				if getattr(request, 'htmx', False):
					response = HttpResponse(status=204)
					response['HX-Redirect'] = '/'
					return response
				return redirect("home")
			# Authentication failed OR user is unverified — render the same generic error.
			form.add_error(None, "Invalid email or password.")

		if getattr(request, 'htmx', False):
			context['login_form'] = form
			return render(request, 'account/partials/login_form.html', context)
	else:
		form = AccountAuthenticationForm()

	context['login_form'] = form
	return render(request, "account/login.html", context)


def account_view(request):

	if not request.user.is_authenticated:
			return redirect("login")

	context = {}
	profile = request.user.profile

	if request.POST:
		form = AccountUpdateForm(request.POST, instance=request.user)
		if form.is_valid():
			form.initial = {
					"email": request.POST['email'],
					"username": request.POST['username'],
			}
			form.save()

			# Update profile fields
			if request.FILES.get('avatar'):
				profile.avatar = request.FILES['avatar']
			profile.bio = request.POST.get('bio', profile.bio)
			profile.location = request.POST.get('location', profile.location)
			profile.website = request.POST.get('website', profile.website)
			profile.twitter = request.POST.get('twitter', profile.twitter)
			profile.save()

			context['success_message'] = "Updated"
			if getattr(request, 'htmx', False):
				response = render(request, "account/account.html", context)
				trigger_toast(response, 'Settings saved!')
				return response
	else:
		form = AccountUpdateForm(
			initial={
					"email": request.user.email,
					"username": request.user.username,
				}
			)

	context['account_form'] = form
	context['profile'] = profile

	blog_posts = BlogPost.objects.filter(author=request.user)
	context['blog_posts'] = blog_posts

	return render(request, "account/account.html", context)


def must_authenticate_view(request):
	return render(request, 'account/must_authenticate.html', {})


def author_profile_view(request, username):
	author = get_object_or_404(Account.objects.select_related('profile'), username=username)
	posts = BlogPost.objects.filter(
		author=author, status='published'
	).select_related('category').order_by('-date_published')
	stats = posts.aggregate(
		total_views=Sum('view_count'),
		post_count=Count('id'),
	)
	context = {
		'author': author,
		'posts': posts,
		'post_count': stats['post_count'],
		'total_views': stats['total_views'] or 0,
	}
	return render(request, 'account/author_profile.html', context)
