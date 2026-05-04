import uuid
from django.db import models
from django_ckeditor_5.fields import CKEditor5Field


class Subscriber(models.Model):
	email = models.EmailField(unique=True)
	token = models.UUIDField(default=uuid.uuid4, editable=False)
	confirmed = models.BooleanField(default=False)
	created_at = models.DateTimeField(auto_now_add=True)

	def __str__(self):
		return self.email


class Page(models.Model):
	"""Admin-editable static page (about, privacy, terms, etc.).

	Slug is the URL key. The view fetches by slug; the page-chrome wrapper
	lives in the template so admins can change copy without breaking layout.
	"""

	slug = models.SlugField(unique=True, max_length=50)
	title = models.CharField(max_length=120)
	body = CKEditor5Field(config_name='default')
	is_published = models.BooleanField(default=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ['slug']

	def __str__(self):
		return f"{self.slug} — {self.title}"
