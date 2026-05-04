from django.urls import path

from blog.api.views import (
	ApiBlogListView,
	api_bookmarks_view,
	api_categories_view,
	api_comments_view,
	api_create_blog_view,
	api_create_comment_view,
	api_delete_blog_view,
	api_delete_comment_view,
	api_detail_blog_view,
	api_is_author_of_blogpost,
	api_tags_view,
	api_toggle_bookmark_view,
	api_toggle_like_view,
	api_update_blog_view,
)

app_name = 'blog'

urlpatterns = [
	# Blog CRUD
	path('create', api_create_blog_view, name="create"),
	path('list', ApiBlogListView.as_view(), name="list"),

	# Categories & Tags
	path('categories/', api_categories_view, name="categories"),
	path('tags/', api_tags_view, name="tags"),

	# Bookmarks (user's list)
	path('bookmarks/', api_bookmarks_view, name="bookmarks"),

	# Comments
	path('comments/<int:pk>/delete/', api_delete_comment_view, name="delete_comment"),

	# Post-specific endpoints (slug-based must come after static paths)
	path('<slug>/', api_detail_blog_view, name="detail"),
	path('<slug>/update', api_update_blog_view, name="update"),
	path('<slug>/delete', api_delete_blog_view, name="delete"),
	path('<slug>/is_author', api_is_author_of_blogpost, name="is_author"),
	path('<slug>/comments/', api_comments_view, name="comments"),
	path('<slug>/comments/create/', api_create_comment_view, name="create_comment"),
	path('<slug>/like/', api_toggle_like_view, name="like"),
	path('<slug>/bookmark/', api_toggle_bookmark_view, name="bookmark"),
]
