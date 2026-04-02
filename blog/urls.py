from django.urls import path,re_path
from blog.views import (
	create_blog_view,
	detail_blog_view,
	edit_blog_view,
    delete_blog_post,
)

app_name = 'blog'

urlpatterns = [
    path('create/', create_blog_view, name="create"),
    path('<slug>/detail/', detail_blog_view, name="detail"),
    path('<slug>/edit/', edit_blog_view, name="edit"),
    path('delete/<pk>',  delete_blog_post, name="delete"),
    
 ]


