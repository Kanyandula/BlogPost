import uuid

from django.db import models


class Subscriber(models.Model):
	email = models.EmailField(unique=True)
	token = models.UUIDField(default=uuid.uuid4, editable=False)
	confirmed = models.BooleanField(default=False)
	created_at = models.DateTimeField(auto_now_add=True)

	def __str__(self):
		return self.email


class AboutPage(models.Model):
	"""Singleton model holding the editable copy for /about.

	Structured fields map to fixed visual sections in the template (intro,
	mission card, categories grid, founder callout). The template owns the
	chrome — admins edit only the words, so the layout cannot be broken.
	"""

	intro = models.TextField(
		help_text='The opening paragraph beneath the page title.',
	)

	mission_title = models.CharField(max_length=80, default='Our Mission')
	mission_body = models.TextField()

	categories_heading = models.CharField(max_length=80, default='Categories We Cover')
	categories = models.TextField(
		help_text='Comma-separated list of category labels (e.g. "Culture, Entertainment, Tourism").',
	)

	founder_title = models.CharField(max_length=120, default='Founded by Ephraim Kanyandula')
	founder_body = models.TextField()

	is_published = models.BooleanField(default=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		verbose_name = 'About page'
		verbose_name_plural = 'About page'

	def __str__(self):
		return 'About page content'

	@property
	def category_list(self):
		"""Split the comma-separated `categories` field into a clean list."""
		return [c.strip() for c in self.categories.split(',') if c.strip()]
