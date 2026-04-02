from django.contrib import admin

from blog.models import BlogPost, Category, Tag, Comment, Like, Bookmark


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
	list_display = ('name', 'slug', 'created_at')
	prepopulated_fields = {'slug': ('name',)}


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
	list_display = ('name', 'slug')
	prepopulated_fields = {'slug': ('name',)}


@admin.register(BlogPost)
class BlogPostAdmin(admin.ModelAdmin):
	list_display = ('title', 'author', 'category', 'status', 'is_featured', 'view_count', 'date_updated')
	list_filter = ('status', 'is_featured', 'category')
	search_fields = ('title', 'body')
	filter_horizontal = ('tags',)
	actions = ['publish_posts', 'feature_posts']

	@admin.action(description="Publish selected posts")
	def publish_posts(self, request, queryset):
		queryset.update(status='published')

	@admin.action(description="Feature selected posts")
	def feature_posts(self, request, queryset):
		queryset.update(is_featured=True)


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
	list_display = ('author', 'post', 'is_active', 'created_at')
	list_filter = ('is_active', 'created_at')
	search_fields = ('body', 'author__username')


@admin.register(Like)
class LikeAdmin(admin.ModelAdmin):
	list_display = ('user', 'post', 'created_at')


@admin.register(Bookmark)
class BookmarkAdmin(admin.ModelAdmin):
	list_display = ('user', 'post', 'created_at')
