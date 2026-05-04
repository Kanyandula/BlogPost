from django.urls import path

from blog.views import (
	bookmarks_view,
	create_blog_view,
	delete_blog_post,
	delete_comment_view,
	detail_blog_view,
	edit_blog_view,
	htmx_create_comment_view,
	toggle_bookmark_view,
	toggle_like_view,
)

app_name = 'blog'

urlpatterns = [
	path('create/', create_blog_view, name="create"),
	path('bookmarks/', bookmarks_view, name="bookmarks"),
	path('<slug>/detail/', detail_blog_view, name="detail"),
	path('<slug>/edit/', edit_blog_view, name="edit"),
	path('<slug>/like/', toggle_like_view, name="like"),
	path('<slug>/bookmark/', toggle_bookmark_view, name="bookmark"),
	path('<slug>/comment/create/', htmx_create_comment_view, name="comment_create"),
	path('delete/<pk>', delete_blog_post, name="delete"),
	path('comment/delete/<int:pk>/', delete_comment_view, name="delete_comment"),
]
