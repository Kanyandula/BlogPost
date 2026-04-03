from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Q, F, Count
from django.http import HttpResponseForbidden, JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required

from blog.models import BlogPost, Category, Comment, Like, Bookmark
from blog.forms import CreateBlogPostForm, UpdateBlogPostForm, CommentForm


@login_required(login_url='must_authenticate')
def create_blog_view(request):
	context = {}

	form = CreateBlogPostForm(request.POST or None, request.FILES or None)
	if form.is_valid():
		obj = form.save(commit=False)
		obj.author = request.user
		obj.save()
		form.save_m2m()
		return redirect('home')

	context['form'] = form
	context['categories'] = Category.objects.all()
	return render(request, "blog/create_blog.html", context)


def detail_blog_view(request, slug):
	context = {}
	blog_post = get_object_or_404(
		BlogPost.objects.select_related('author__profile', 'category').prefetch_related('tags'),
		slug=slug
	)

	# Increment view count
	BlogPost.objects.filter(pk=blog_post.pk).update(view_count=F('view_count') + 1)

	# Handle comment submission
	if request.method == 'POST' and request.user.is_authenticated:
		comment_form = CommentForm(request.POST)
		if comment_form.is_valid():
			comment = comment_form.save(commit=False)
			comment.post = blog_post
			comment.author = request.user
			parent_id = request.POST.get('parent_id')
			if parent_id:
				parent = get_object_or_404(Comment, pk=parent_id)
				# Flatten to max 1 level: replies to replies become siblings
				comment.parent = parent.parent or parent
			comment.save()
			return redirect('blog:detail', slug=slug)
	else:
		comment_form = CommentForm()

	# Get comments (top-level only, replies via prefetch)
	comments = blog_post.comments.filter(
		parent=None, is_active=True
	).select_related('author').prefetch_related('replies__author')

	# Like and bookmark status
	is_liked = False
	is_bookmarked = False
	if request.user.is_authenticated:
		is_liked = Like.objects.filter(post=blog_post, user=request.user).exists()
		is_bookmarked = Bookmark.objects.filter(post=blog_post, user=request.user).exists()

	context['blog_post'] = blog_post
	context['comment_form'] = comment_form
	context['comments'] = comments
	context['comment_count'] = blog_post.comments.filter(is_active=True).count()
	context['like_count'] = blog_post.likes.count()
	context['is_liked'] = is_liked
	context['is_bookmarked'] = is_bookmarked
	context['related_posts'] = blog_post.get_related_posts(limit=4)

	return render(request, 'blog/detail_blog.html', context)


@login_required(login_url='must_authenticate')
def edit_blog_view(request, slug):
	context = {}

	blog_post = get_object_or_404(BlogPost, slug=slug)
	if blog_post.author != request.user:
		return HttpResponseForbidden('You are not the author of that post.')

	if request.POST:
		form = UpdateBlogPostForm(request.POST or None, request.FILES or None, instance=blog_post)
		if form.is_valid():
			blog_post = form.save()
			context['success_message'] = "Updated"
	else:
		form = UpdateBlogPostForm(
			initial={
				"title": blog_post.title,
				"body": blog_post.body,
				"image": blog_post.image,
			}
		)

	context['form'] = form
	context['blog_post'] = blog_post
	context['categories'] = Category.objects.all()
	return render(request, 'blog/edit_blog.html', context)


def get_blog_queryset(query=None):
	if not query:
		return BlogPost.objects.filter(status='published')
	q_objects = Q()
	for term in query.split():
		q_objects |= Q(title__icontains=term) | Q(body__icontains=term)
	return BlogPost.objects.filter(q_objects, status='published').distinct()


@login_required(login_url='must_authenticate')
def delete_blog_post(request, pk):
	post = get_object_or_404(BlogPost, id=pk)
	if post.author != request.user:
		return HttpResponseForbidden('You are not the author of that post.')
	if request.method == 'POST':
		post.delete()
		return redirect('home')
	context = {'post': post}
	return render(request, 'blog/post_delete.html', context)


@login_required(login_url='must_authenticate')
def delete_comment_view(request, pk):
	comment = get_object_or_404(Comment, pk=pk)
	if comment.author != request.user:
		return HttpResponseForbidden('You are not the author of this comment.')
	slug = comment.post.slug
	if request.method == 'POST':
		comment.delete()
	return redirect('blog:detail', slug=slug)


@require_POST
def toggle_like_view(request, slug):
	if not request.user.is_authenticated:
		return JsonResponse({'error': 'Login required'}, status=401)
	post = get_object_or_404(BlogPost, slug=slug)
	like, created = Like.objects.get_or_create(post=post, user=request.user)
	if not created:
		like.delete()
		liked = False
	else:
		liked = True
	return JsonResponse({'liked': liked, 'count': post.likes.count()})


@require_POST
def toggle_bookmark_view(request, slug):
	if not request.user.is_authenticated:
		return JsonResponse({'error': 'Login required'}, status=401)
	post = get_object_or_404(BlogPost, slug=slug)
	bookmark, created = Bookmark.objects.get_or_create(post=post, user=request.user)
	if not created:
		bookmark.delete()
		bookmarked = False
	else:
		bookmarked = True
	return JsonResponse({'bookmarked': bookmarked})


@login_required(login_url='login')
def bookmarks_view(request):
	bookmarked_posts = BlogPost.objects.filter(
		bookmarks__user=request.user
	).select_related('author', 'category').order_by('-bookmarks__created_at')
	return render(request, 'blog/bookmarks.html', {'blog_posts': bookmarked_posts})
