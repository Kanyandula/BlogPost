from django.test import TestCase
from django.urls import reverse

from personal.models import AboutPage


class AboutPageRenderingTests(TestCase):
	"""The /about view reads from the AboutPage singleton so admin can edit copy."""

	def test_about_renders_seeded_page(self):
		"""Migration 0006 seeds the singleton; the view must render all sections."""
		response = self.client.get(reverse('about'))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'About NyasaBlog')
		self.assertContains(response, 'NyasaBlog is a digital platform')
		self.assertContains(response, 'Our Mission')
		self.assertContains(response, 'Categories We Cover')
		self.assertContains(response, 'Founded by Ephraim Kanyandula')

	def test_about_renders_categories_as_chips(self):
		"""Each comma-separated category should produce its own chip span."""
		AboutPage.objects.update(categories='Culture, Tourism, Sports')
		response = self.client.get(reverse('about'))
		# Each chip is wrapped in a span — search for exact label between tags
		self.assertContains(response, '>Culture</span>')
		self.assertContains(response, '>Tourism</span>')
		self.assertContains(response, '>Sports</span>')

	def test_about_reflects_admin_edits(self):
		AboutPage.objects.update(
			intro='Brand new intro paragraph.',
			mission_title='Why we exist',
			mission_body='Edited mission body.',
			founder_title='Built by Ephraim',
			founder_body='Custom founder copy.',
		)
		response = self.client.get(reverse('about'))
		self.assertContains(response, 'Brand new intro paragraph.')
		self.assertContains(response, 'Why we exist')
		self.assertContains(response, 'Edited mission body.')
		self.assertContains(response, 'Built by Ephraim')
		self.assertContains(response, 'Custom founder copy.')

	def test_about_falls_back_when_unpublished(self):
		AboutPage.objects.update(is_published=False)
		response = self.client.get(reverse('about'))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'About NyasaBlog')
		# Falls back to the static template default copy
		self.assertContains(response, 'NyasaBlog is a digital platform')

	def test_about_falls_back_when_singleton_missing(self):
		AboutPage.objects.all().delete()
		response = self.client.get(reverse('about'))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'About NyasaBlog')

	def test_intro_is_html_escaped(self):
		"""User input through structured fields must be escaped, not rendered as HTML."""
		AboutPage.objects.update(intro='<script>alert(99887766)</script>')
		response = self.client.get(reverse('about'))
		# The raw <script> tag must not appear — Django auto-escape converts it
		# to &lt;script&gt;, which is harmless text in the rendered page.
		self.assertNotContains(response, '<script>alert(99887766)')
		self.assertContains(response, '&lt;script&gt;alert(99887766)')


class AboutPageModelTests(TestCase):
	def test_singleton_str(self):
		page = AboutPage.objects.first()
		self.assertEqual(str(page), 'About page content')

	def test_category_list_property_strips_whitespace_and_empties(self):
		page = AboutPage.objects.first()
		page.categories = 'Culture,  Tourism ,, Sports ,'
		self.assertEqual(page.category_list, ['Culture', 'Tourism', 'Sports'])

	def test_category_list_handles_empty_string(self):
		page = AboutPage.objects.first()
		page.categories = ''
		self.assertEqual(page.category_list, [])
