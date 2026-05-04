from django.test import TestCase
from django.urls import reverse

from personal.models import Page


class AboutPageRenderingTests(TestCase):
	"""The /about view reads from the Page model so admin can edit copy."""

	def test_about_renders_seeded_page(self):
		"""Migration 0005 seeds slug='about'; the view must render its title + body."""
		response = self.client.get(reverse('about'))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'About NyasaBlog')
		self.assertContains(response, 'NyasaBlog is a digital platform')

	def test_about_reflects_admin_edits(self):
		Page.objects.filter(slug='about').update(
			title='About Us', body='<p>New body content from admin.</p>',
		)
		response = self.client.get(reverse('about'))
		self.assertContains(response, 'About Us')
		self.assertContains(response, 'New body content from admin.')

	def test_about_falls_back_when_unpublished(self):
		Page.objects.filter(slug='about').update(is_published=False)
		response = self.client.get(reverse('about'))
		self.assertEqual(response.status_code, 200)
		# Falls back to the static template default heading
		self.assertContains(response, 'About NyasaBlog')

	def test_about_falls_back_when_page_missing(self):
		Page.objects.filter(slug='about').delete()
		response = self.client.get(reverse('about'))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'About NyasaBlog')

	def test_page_body_is_sanitized(self):
		Page.objects.filter(slug='about').update(
			body='<p>Hello</p><script>alert(99887766)</script><iframe src="evil.example"></iframe>',
		)
		response = self.client.get(reverse('about'))
		# Use unique strings so we don't collide with the base template's own scripts.
		self.assertNotContains(response, 'alert(99887766)')
		self.assertNotContains(response, 'evil.example')
		self.assertContains(response, '<p>Hello</p>')


class PageModelTests(TestCase):
	def test_page_str(self):
		p = Page.objects.create(slug='terms', title='Terms', body='<p>x</p>')
		self.assertEqual(str(p), 'terms — Terms')

	def test_slug_unique(self):
		from django.db import IntegrityError
		Page.objects.create(slug='privacy', title='Privacy', body='<p>x</p>')
		with self.assertRaises(IntegrityError):
			Page.objects.create(slug='privacy', title='Other', body='<p>y</p>')
