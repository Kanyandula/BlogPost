from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, logout

from account.forms import RegistrationForm, AccountAuthenticationForm, AccountUpdateForm
from account.models import Account
from django.db.models import Count, Sum
from blog.models import BlogPost



def registration_view(request):
	context = {}
	if request.POST:
		form = RegistrationForm(request.POST)
		if form.is_valid():
			form.save()
			email = form.cleaned_data.get('email').lower()
			raw_password = form.cleaned_data.get('password1')
			account = authenticate(email=email, password=raw_password)
			login(request, account)
			return redirect('home')
		else:
			context['registration_form'] = form

	else:
		form = RegistrationForm()
		context['registration_form'] = form
	return render(request, 'account/register.html', context)


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

			if user:
				login(request, user)
				return redirect("home")

	else:
		form = AccountAuthenticationForm()

	context['login_form'] = form

	# print(form)
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
