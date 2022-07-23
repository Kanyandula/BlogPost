from email import message
from django.shortcuts import render
from operator import attrgetter
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator

from blog.views import get_blog_queryset
from blog.models import BlogPost
from blog.forms import ContactForm
from django.core.mail import send_mail, BadHeaderError
from django.http import HttpResponse

BLOG_POSTS_PER_PAGE = 10



def home_screen_view(request):
	
	context = {}

	query = ""
	query = request.GET.get('q', '')
	context['query'] = str(query)
	print("home_screen_view: " + str(query))

	blog_posts = sorted(get_blog_queryset(query), key=attrgetter('date_updated'), reverse=True)
	
	# Pagination
	page = request.GET.get('page', 1)
	blog_posts_paginator = Paginator(blog_posts, BLOG_POSTS_PER_PAGE)

	try:
		blog_posts = blog_posts_paginator.page(page)
	except PageNotAnInteger:
		blog_posts = blog_posts_paginator.page(BLOG_POSTS_PER_PAGE)
	except EmptyPage:
		blog_posts = blog_posts_paginator.page(blog_posts_paginator.num_pages)

	context['blog_posts'] = blog_posts

	return render(request, "personal/home.html", context)

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
			sender =  form.cleaned_data["email"]
			recipients = ['ekanyandula8@gmail.com']
			try:
				send_mail(subject, message, sender, recipients, fail_silently= True)
			except BadHeaderError:
				return HttpResponse('Invalid header found')
			return HttpResponse('Success....Your email has been sent')		
	return render(request, 'personal/contact.html', {'form': form})	



