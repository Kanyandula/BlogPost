from django.shortcuts import render
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import Count
from django.conf import settings

from blog.views import get_blog_queryset
from blog.models import BlogPost, Category, Tag
from personal.forms import ContactForm
from django.core.mail import send_mail, BadHeaderError
from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_POST

from personal.models import Subscriber

BLOG_POSTS_PER_PAGE = 10


def _annotate_posts(queryset):
	return queryset.select_related(
		'author', 'category'
	).annotate(
		like_count=Count('likes', distinct=True),
		comment_count=Count('comments', distinct=True),
	)


def home_screen_view(request):
	context = {}

	query = request.GET.get('q', '')
	category_slug = request.GET.get('category', '')
	context['query'] = str(query)

	if query:
		blog_posts = _annotate_posts(
			get_blog_queryset(query)
		).order_by('-date_updated')
	elif category_slug:
		blog_posts = _annotate_posts(
			BlogPost.objects.filter(status='published', category__slug=category_slug)
		).order_by('-date_updated')
	else:
		blog_posts = _annotate_posts(
			BlogPost.objects.filter(status='published')
		).order_by('-date_updated')

	# Pagination
	page = request.GET.get('page', 1)
	blog_posts_paginator = Paginator(blog_posts, BLOG_POSTS_PER_PAGE)

	try:
		blog_posts = blog_posts_paginator.page(page)
	except PageNotAnInteger:
		blog_posts = blog_posts_paginator.page(1)
	except EmptyPage:
		blog_posts = blog_posts_paginator.page(blog_posts_paginator.num_pages)

	context['blog_posts'] = blog_posts
	context['active_category'] = category_slug

	# HTMX partial — skip sidebar queries
	if request.htmx and request.GET.get('partial') == 'post_grid':
		return render(request, 'personal/partials/post_grid.html', context)

	# Full page — compute sidebar data
	context['featured_posts'] = BlogPost.objects.filter(
		is_featured=True, status='published'
	).select_related('author').order_by('-date_published')[:3]
	context['trending_posts'] = BlogPost.objects.filter(
		status='published'
	).annotate(
		like_count=Count('likes')
	).order_by('-view_count', '-like_count')[:5]
	context['categories'] = Category.objects.all()
	return render(request, "personal/home.html", context)


def search_view(request):
	context = {}
	query = request.GET.get('q', '')
	category_slug = request.GET.get('category', '')
	context['query'] = query

	if query:
		blog_posts = _annotate_posts(
			get_blog_queryset(query)
		).order_by('-date_updated')

		if category_slug:
			blog_posts = blog_posts.filter(category__slug=category_slug)

		context['result_count'] = blog_posts.count()
	else:
		blog_posts = BlogPost.objects.none()
		context['result_count'] = 0

	# Pagination
	page = request.GET.get('page', 1)
	paginator = Paginator(blog_posts, BLOG_POSTS_PER_PAGE)
	try:
		blog_posts = paginator.page(page)
	except PageNotAnInteger:
		blog_posts = paginator.page(1)
	except EmptyPage:
		blog_posts = paginator.page(paginator.num_pages)

	context['blog_posts'] = blog_posts
	context['active_category'] = category_slug

	# HTMX partial — skip sidebar queries
	if request.htmx and request.GET.get('partial') == 'search_list':
		return render(request, 'personal/partials/search_results_list.html', context)

	# Full page — compute sidebar data
	context['categories'] = Category.objects.all()
	context['tags'] = Tag.objects.all()[:20]
	return render(request, 'personal/search_results.html', context)


def about_screen_view(request):
	return render(request, 'personal/about.html')


def api_screen_view(request):
	return render(request, 'personal/api.html')


def contact_screen_view(request):
	form = ContactForm()
	if request.method == 'POST':
		form = ContactForm(request.POST)
		if form.is_valid():
			subject = f'Message from {form.cleaned_data["name"]}'
			message = form.cleaned_data["message"]
			sender = form.cleaned_data["email"]
			recipients = [getattr(settings, 'CONTACT_EMAIL', settings.DEFAULT_FROM_EMAIL)]
			try:
				send_mail(subject, message, sender, recipients, fail_silently=True)
			except BadHeaderError:
				return HttpResponse('Invalid header found')
			return render(request, 'personal/contact.html', {'form': ContactForm(), 'success': True})
	return render(request, 'personal/contact.html', {'form': form})


@require_POST
def subscribe_view(request):
	from django.core.validators import validate_email
	from django.core.exceptions import ValidationError

	email = request.POST.get('email', '').strip().lower()
	if not email:
		if request.htmx:
			return HttpResponse('Please enter your email.', status=422)
		return JsonResponse({'error': 'Email is required'}, status=400)

	try:
		validate_email(email)
	except ValidationError:
		if request.htmx:
			return HttpResponse('Please enter a valid email.', status=422)
		return JsonResponse({'error': 'Invalid email address'}, status=400)

	subscriber, created = Subscriber.objects.get_or_create(email=email)
	message = 'Thanks for subscribing!' if created else 'You are already subscribed!'

	if request.htmx:
		return HttpResponse(message)
	return JsonResponse({'success': True, 'message': message})
