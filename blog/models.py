from django.db import models
from django.db.models import Q
from django.db.models.signals import pre_save
from django.utils.text import slugify
from django.utils.html import strip_tags
from django.conf import settings
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django_ckeditor_5.fields import CKEditor5Field


def upload_location(instance, filename):
	file_path = 'blog/{author_id}/{title}-{filename}'.format(
				author_id=str(instance.author.id), title=str(instance.title), filename=filename)
	return file_path


class Category(models.Model):
	name = models.CharField(max_length=100, unique=True)
	slug = models.SlugField(max_length=100, unique=True)
	description = models.TextField(max_length=500, blank=True)
	image = models.ImageField(upload_to='categories/', null=True, blank=True)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		verbose_name_plural = "categories"
		ordering = ['name']

	def __str__(self):
		return self.name


class Tag(models.Model):
	name = models.CharField(max_length=60, unique=True)
	slug = models.SlugField(max_length=60, unique=True)

	class Meta:
		ordering = ['name']

	def __str__(self):
		return self.name


class BlogPost(models.Model):
	STATUS_CHOICES = [
		('draft', 'Draft'),
		('published', 'Published'),
	]

	title = models.CharField(max_length=50, null=False, blank=True)
	body = CKEditor5Field(max_length=20000, blank=True, config_name='default')
	image = models.ImageField(upload_to=upload_location, null=True, blank=True)
	date_published = models.DateTimeField(auto_now_add=True, verbose_name="date published")
	date_updated = models.DateTimeField(auto_now=True, verbose_name="date updated")
	author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
	slug = models.SlugField(blank=True, unique=True)
	category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name='posts')
	tags = models.ManyToManyField(Tag, blank=True, related_name='posts')
	status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='draft')
	is_featured = models.BooleanField(default=False)
	view_count = models.PositiveIntegerField(default=0)

	class Meta:
		ordering = ['-date_updated']

	def __str__(self):
		return self.title

	@property
	def reading_time(self):
		word_count = len(strip_tags(self.body).split())
		minutes = max(1, round(word_count / 200))
		return minutes

	def get_related_posts(self, limit=4):
		return BlogPost.objects.filter(
			Q(category=self.category) | Q(tags__in=self.tags.all()),
			status='published'
		).exclude(pk=self.pk).distinct().order_by('-date_published')[:limit]


class Comment(models.Model):
	post = models.ForeignKey(BlogPost, on_delete=models.CASCADE, related_name='comments')
	author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='comments')
	parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='replies')
	body = models.TextField(max_length=1000)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)
	is_active = models.BooleanField(default=True)

	class Meta:
		ordering = ['-created_at']

	def __str__(self):
		return f"Comment by {self.author.username} on {self.post.title}"


class Like(models.Model):
	post = models.ForeignKey(BlogPost, on_delete=models.CASCADE, related_name='likes')
	user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='likes')
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		unique_together = ('post', 'user')

	def __str__(self):
		return f"{self.user.username} likes {self.post.title}"


class Bookmark(models.Model):
	post = models.ForeignKey(BlogPost, on_delete=models.CASCADE, related_name='bookmarks')
	user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='bookmarks')
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		unique_together = ('post', 'user')

	def __str__(self):
		return f"{self.user.username} bookmarked {self.post.title}"


@receiver(post_delete, sender=BlogPost)
def submission_delete(sender, instance, **kwargs):
	instance.image.delete(False)


def pre_save_blog_post_receiver(sender, instance, *args, **kwargs):
	if not instance.slug:
		instance.slug = slugify(instance.author.username + "-" + instance.title)

pre_save.connect(pre_save_blog_post_receiver, sender=BlogPost)
