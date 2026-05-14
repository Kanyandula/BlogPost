from django.test import TestCase
from django.urls import reverse

from account.models import Account
from blog.forms import CreateBlogPostForm
from blog.models import BlogPost, Category
from blog.widgets import TiptapWidget


class TiptapWidgetRenderTests(TestCase):
	def test_renders_hidden_textarea(self):
		html = TiptapWidget().render('body', '<p>hi</p>')
		self.assertIn('<textarea', html)
		self.assertIn('hidden', html)
		self.assertIn('data-tiptap-input', html)

	def test_renders_editor_mount_and_bubble(self):
		html = TiptapWidget().render('body', '')
		self.assertIn('data-tiptap-root', html)
		self.assertIn('data-bubble', html)
		self.assertIn('data-editor', html)

	def test_preserves_initial_value(self):
		html = TiptapWidget().render('body', '<h2>Hi</h2>')
		self.assertIn('<h2>Hi</h2>', html)

	def test_media_includes_tiptap_assets(self):
		widget = TiptapWidget()
		self.assertIn('blog/tiptap.js', str(widget.media))
		self.assertIn('blog/tiptap.css', str(widget.media))


class TiptapFormRoundtripTests(TestCase):
	def setUp(self):
		self.user = Account.objects.create_user(
			email='t@nyasablog.com', username='t', password='p',
		)
		self.user.email_verified = True
		self.user.save()
		self.category, _ = Category.objects.get_or_create(
			name='Culture', slug='culture', defaults={'description': 'x'},
		)

	def test_form_uses_tiptap_widget_for_body(self):
		form = CreateBlogPostForm()
		self.assertIsInstance(form.fields['body'].widget, TiptapWidget)

	def test_form_roundtrip_preserves_html(self):
		form = CreateBlogPostForm({
			'title': 'T',
			'body': '<h2>X</h2><p>Y</p>',
			'category': self.category.id,
			'status': 'draft',
		})
		self.assertTrue(form.is_valid(), form.errors)
		post = form.save(commit=False)
		post.author = self.user
		post.save()
		form.save_m2m()
		post.refresh_from_db()
		self.assertEqual(post.body, '<h2>X</h2><p>Y</p>')


class SanitiserRegressionTests(TestCase):
	"""The editor swap MUST NOT regress the server-side sanitiser."""

	def setUp(self):
		self.user = Account.objects.create_user(
			email='s@nyasablog.com', username='s', password='p',
		)
		self.user.email_verified = True
		self.user.save()
		self.category, _ = Category.objects.get_or_create(
			name='Tech', slug='tech', defaults={'description': 'x'},
		)

	def test_detail_view_strips_style_attribute(self):
		post = BlogPost.objects.create(
			title='S',
			body='<p style="color:red">X</p>',
			author=self.user, category=self.category, status='published',
		)
		r = self.client.get(reverse('blog:detail', args=[post.slug]))
		self.assertEqual(r.status_code, 200)
		self.assertNotIn(b'style=', r.content)
		self.assertIn(b'<p>X</p>', r.content)

	def test_detail_view_strips_script(self):
		post = BlogPost.objects.create(
			title='S2',
			body='<p>safe</p><script>alert(1)</script>',
			author=self.user, category=self.category, status='published',
		)
		r = self.client.get(reverse('blog:detail', args=[post.slug]))
		self.assertEqual(r.status_code, 200)
		self.assertNotIn(b'<script>', r.content)
