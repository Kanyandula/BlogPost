from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse

from account.models import Account
from blog.models import BlogPost, Bookmark, Category, Comment, Like, Tag


class ModelTestMixin:
	"""Create shared test fixtures."""
	def setUp(self):
		self.user = Account.objects.create_user(
			email='test@nyasablog.com', username='testuser', password='testpass123'
		)
		self.user.email_verified = True
		self.user.save()
		self.user2 = Account.objects.create_user(
			email='other@nyasablog.com', username='otheruser', password='testpass123'
		)
		self.user2.email_verified = True
		self.user2.save()
		self.category, _ = Category.objects.get_or_create(name='Culture', slug='culture', defaults={'description': 'Test'})
		self.tag, _ = Tag.objects.get_or_create(name='Malawi', slug='malawi')
		self.post = BlogPost.objects.create(
			title='Test Post', body='This is test content for the blog post with enough words.',
			author=self.user, status='published', category=self.category
		)
		self.post.tags.add(self.tag)


class CategoryTagTests(ModelTestMixin, TestCase):

	def test_category_creation(self):
		self.assertEqual(str(self.category), 'Culture')
		self.assertEqual(self.category.slug, 'culture')

	def test_tag_creation(self):
		self.assertEqual(str(self.tag), 'Malawi')

	def test_post_has_category_and_tags(self):
		self.assertEqual(self.post.category, self.category)
		self.assertIn(self.tag, self.post.tags.all())


class BlogPostTests(ModelTestMixin, TestCase):

	def test_post_creation(self):
		self.assertEqual(str(self.post), 'Test Post')
		self.assertEqual(self.post.status, 'published')
		self.assertFalse(self.post.is_featured)
		self.assertEqual(self.post.view_count, 0)

	def test_slug_auto_generated(self):
		self.assertTrue(self.post.slug)
		self.assertIn('testuser', self.post.slug)

	def test_slug_collision_resolved(self):
		post2 = BlogPost.objects.create(
			title='Test Post', body='Different content here.',
			author=self.user, status='published'
		)
		self.assertNotEqual(self.post.slug, post2.slug)
		self.assertTrue(post2.slug.startswith('testuser-test-post'))

	def test_reading_time(self):
		self.assertGreaterEqual(self.post.reading_time, 1)

	def test_get_related_posts(self):
		post2 = BlogPost.objects.create(
			title='Related Post', body='Related content.',
			author=self.user, status='published', category=self.category
		)
		related = self.post.get_related_posts()
		self.assertIn(post2, related)

	def test_draft_posts_excluded_from_related(self):
		draft = BlogPost.objects.create(
			title='Draft Post', body='Draft content.',
			author=self.user, status='draft', category=self.category
		)
		related = self.post.get_related_posts()
		self.assertNotIn(draft, related)


class CommentTests(ModelTestMixin, TestCase):

	def test_comment_creation(self):
		comment = Comment.objects.create(
			post=self.post, author=self.user, body='Great post!'
		)
		self.assertEqual(str(comment), 'Comment by testuser on Test Post')

	def test_threaded_reply(self):
		parent = Comment.objects.create(post=self.post, author=self.user, body='Parent')
		reply = Comment.objects.create(post=self.post, author=self.user2, body='Reply', parent=parent)
		self.assertEqual(reply.parent, parent)
		self.assertIn(reply, parent.replies.all())


class LikeBookmarkTests(ModelTestMixin, TestCase):

	def test_like_creation(self):
		like = Like.objects.create(post=self.post, user=self.user)
		self.assertEqual(self.post.likes.count(), 1)
		self.assertEqual(str(like), 'testuser likes Test Post')

	def test_like_unique_constraint(self):
		Like.objects.create(post=self.post, user=self.user)
		with self.assertRaises(IntegrityError):
			Like.objects.create(post=self.post, user=self.user)

	def test_bookmark_creation(self):
		Bookmark.objects.create(post=self.post, user=self.user)
		self.assertEqual(self.post.bookmarks.count(), 1)

	def test_bookmark_unique_constraint(self):
		Bookmark.objects.create(post=self.post, user=self.user)
		with self.assertRaises(IntegrityError):
			Bookmark.objects.create(post=self.post, user=self.user)


class HomeViewTests(ModelTestMixin, TestCase):

	def test_home_page_loads(self):
		response = self.client.get(reverse('home'))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'NyasaBlog')

	def test_home_shows_published_posts(self):
		response = self.client.get(reverse('home'))
		self.assertContains(response, 'Test Post')

	def test_home_hides_draft_posts(self):
		self.post.status = 'draft'
		self.post.save()
		response = self.client.get(reverse('home'))
		self.assertNotContains(response, 'Test Post')

	def test_home_category_filter(self):
		response = self.client.get(reverse('home') + '?category=culture')
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Test Post')

	def test_home_category_filter_no_match(self):
		Category.objects.get_or_create(name='Sports', slug='sports')
		response = self.client.get(reverse('home') + '?category=sports')
		# Post appears in trending sidebar but not in main feed
		self.assertContains(response, 'No stories found')

	def test_home_search(self):
		response = self.client.get(reverse('home') + '?q=Test')
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Test Post')


class DetailViewTests(ModelTestMixin, TestCase):

	def test_detail_page_loads(self):
		response = self.client.get(reverse('blog:detail', args=[self.post.slug]))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Test Post')

	def test_detail_increments_view_count(self):
		self.client.get(reverse('blog:detail', args=[self.post.slug]))
		self.post.refresh_from_db()
		self.assertEqual(self.post.view_count, 1)

	def test_detail_shows_comments(self):
		Comment.objects.create(post=self.post, author=self.user, body='Nice article!')
		response = self.client.get(reverse('blog:detail', args=[self.post.slug]))
		self.assertContains(response, 'Nice article!')


class LikeToggleViewTests(ModelTestMixin, TestCase):

	def test_like_requires_post_method(self):
		self.client.login(email='test@nyasablog.com', password='testpass123')
		response = self.client.get(reverse('blog:like', args=[self.post.slug]))
		self.assertEqual(response.status_code, 405)

	def test_like_requires_auth(self):
		response = self.client.post(reverse('blog:like', args=[self.post.slug]))
		# @htmx_login_required redirects non-HTMX unauthenticated requests
		self.assertEqual(response.status_code, 302)

	def test_like_toggle(self):
		self.client.login(email='test@nyasablog.com', password='testpass123')
		# Like
		response = self.client.post(reverse('blog:like', args=[self.post.slug]))
		self.assertEqual(response.status_code, 200)
		data = response.json()
		self.assertTrue(data['liked'])
		self.assertEqual(data['count'], 1)
		# Unlike
		response = self.client.post(reverse('blog:like', args=[self.post.slug]))
		data = response.json()
		self.assertFalse(data['liked'])
		self.assertEqual(data['count'], 0)


class BookmarkViewTests(ModelTestMixin, TestCase):

	def test_bookmark_toggle(self):
		self.client.login(email='test@nyasablog.com', password='testpass123')
		response = self.client.post(reverse('blog:bookmark', args=[self.post.slug]))
		self.assertTrue(response.json()['bookmarked'])
		response = self.client.post(reverse('blog:bookmark', args=[self.post.slug]))
		self.assertFalse(response.json()['bookmarked'])

	def test_bookmarks_page_requires_auth(self):
		response = self.client.get(reverse('blog:bookmarks'))
		self.assertEqual(response.status_code, 302)

	def test_bookmarks_page_shows_bookmarked(self):
		self.client.login(email='test@nyasablog.com', password='testpass123')
		Bookmark.objects.create(post=self.post, user=self.user)
		response = self.client.get(reverse('blog:bookmarks'))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Test Post')


class AuthViewTests(TestCase):

	def test_login_page_loads(self):
		self.assertEqual(self.client.get(reverse('login')).status_code, 200)

	def test_register_page_loads(self):
		self.assertEqual(self.client.get(reverse('register')).status_code, 200)

	def test_about_page_loads(self):
		self.assertEqual(self.client.get(reverse('about')).status_code, 200)

	def test_contact_page_loads(self):
		self.assertEqual(self.client.get(reverse('contact')).status_code, 200)

	def test_password_reset_loads(self):
		self.assertEqual(self.client.get(reverse('password_reset')).status_code, 200)


class AuthorProfileTests(ModelTestMixin, TestCase):

	def test_author_profile_loads(self):
		response = self.client.get(reverse('author_profile', args=['testuser']))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'testuser')

	def test_author_profile_shows_published_only(self):
		BlogPost.objects.create(
			title='Draft Secret', body='Hidden.', author=self.user, status='draft'
		)
		response = self.client.get(reverse('author_profile', args=['testuser']))
		self.assertNotContains(response, 'Draft Secret')
		self.assertContains(response, 'Test Post')

	def test_author_profile_404_for_nonexistent(self):
		response = self.client.get(reverse('author_profile', args=['nobody']))
		self.assertEqual(response.status_code, 404)


class CreatePostViewTests(ModelTestMixin, TestCase):

	def test_create_requires_auth(self):
		response = self.client.get(reverse('blog:create'))
		self.assertEqual(response.status_code, 302)

	def test_create_page_loads_for_authenticated(self):
		self.client.login(email='test@nyasablog.com', password='testpass123')
		response = self.client.get(reverse('blog:create'))
		self.assertEqual(response.status_code, 200)

	def test_create_post_submission(self):
		self.client.login(email='test@nyasablog.com', password='testpass123')
		response = self.client.post(reverse('blog:create'), {
			'title': 'New Blog Post',
			'body': 'This is the body of a new blog post with enough content.',
			'status': 'published',
			'category': self.category.pk,
		})
		self.assertEqual(response.status_code, 302)
		self.assertTrue(BlogPost.objects.filter(title='New Blog Post').exists())


class EditPostViewTests(ModelTestMixin, TestCase):

	def test_edit_requires_auth(self):
		response = self.client.get(reverse('blog:edit', args=[self.post.slug]))
		self.assertEqual(response.status_code, 302)

	def test_edit_denied_for_non_author(self):
		self.client.login(email='other@nyasablog.com', password='testpass123')
		response = self.client.get(reverse('blog:edit', args=[self.post.slug]))
		self.assertEqual(response.status_code, 403)

	def test_edit_page_loads_for_author(self):
		self.client.login(email='test@nyasablog.com', password='testpass123')
		response = self.client.get(reverse('blog:edit', args=[self.post.slug]))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Edit Story')

	def test_edit_post_submission(self):
		self.client.login(email='test@nyasablog.com', password='testpass123')
		response = self.client.post(reverse('blog:edit', args=[self.post.slug]), {
			'title': 'Updated Title',
			'body': 'Updated body content here.',
			'status': 'published',
		})
		self.assertEqual(response.status_code, 200)
		self.post.refresh_from_db()
		self.assertEqual(self.post.title, 'Updated Title')


class DeletePostViewTests(ModelTestMixin, TestCase):

	def test_delete_requires_auth(self):
		response = self.client.get(reverse('blog:delete', args=[self.post.pk]))
		self.assertEqual(response.status_code, 302)

	def test_delete_denied_for_non_author(self):
		self.client.login(email='other@nyasablog.com', password='testpass123')
		response = self.client.get(reverse('blog:delete', args=[self.post.pk]))
		self.assertEqual(response.status_code, 403)

	def test_delete_confirmation_page_loads(self):
		self.client.login(email='test@nyasablog.com', password='testpass123')
		response = self.client.get(reverse('blog:delete', args=[self.post.pk]))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'delete')

	def test_delete_post_submission(self):
		self.client.login(email='test@nyasablog.com', password='testpass123')
		post_pk = self.post.pk
		response = self.client.post(reverse('blog:delete', args=[post_pk]))
		self.assertEqual(response.status_code, 302)
		self.assertFalse(BlogPost.objects.filter(pk=post_pk).exists())


class CommentSubmissionTests(ModelTestMixin, TestCase):

	def test_comment_requires_auth(self):
		self.client.post(
			reverse('blog:detail', args=[self.post.slug]),
			{'body': 'Anonymous comment'}
		)
		# Unauthenticated POST redirects or ignores comment
		self.assertEqual(Comment.objects.count(), 0)

	def test_comment_submission(self):
		self.client.login(email='test@nyasablog.com', password='testpass123')
		response = self.client.post(
			reverse('blog:comment_create', args=[self.post.slug]),
			{'body': 'Great article!'},
			HTTP_HX_REQUEST='true',
		)
		self.assertEqual(response.status_code, 200)
		self.assertEqual(Comment.objects.count(), 1)
		self.assertEqual(Comment.objects.first().body, 'Great article!')

	def test_reply_submission(self):
		self.client.login(email='test@nyasablog.com', password='testpass123')
		parent = Comment.objects.create(post=self.post, author=self.user, body='Parent comment')
		response = self.client.post(
			reverse('blog:comment_create', args=[self.post.slug]),
			{'body': 'Reply to parent', 'parent_id': parent.pk},
			HTTP_HX_REQUEST='true',
		)
		self.assertEqual(response.status_code, 200)
		reply = Comment.objects.filter(parent=parent).first()
		self.assertIsNotNone(reply)
		self.assertEqual(reply.body, 'Reply to parent')

	def test_delete_comment_by_author(self):
		self.client.login(email='test@nyasablog.com', password='testpass123')
		comment = Comment.objects.create(post=self.post, author=self.user, body='To delete')
		response = self.client.post(reverse('blog:delete_comment', args=[comment.pk]))
		self.assertEqual(response.status_code, 302)
		self.assertFalse(Comment.objects.filter(pk=comment.pk).exists())

	def test_delete_comment_denied_for_non_author(self):
		self.client.login(email='other@nyasablog.com', password='testpass123')
		comment = Comment.objects.create(post=self.post, author=self.user, body='Not yours')
		response = self.client.post(reverse('blog:delete_comment', args=[comment.pk]))
		self.assertEqual(response.status_code, 403)


class BookmarkTogglePostMethodTests(ModelTestMixin, TestCase):

	def test_bookmark_requires_post_method(self):
		self.client.login(email='test@nyasablog.com', password='testpass123')
		response = self.client.get(reverse('blog:bookmark', args=[self.post.slug]))
		self.assertEqual(response.status_code, 405)


class SanitizeHtmlFilterTests(TestCase):
	"""nh3 filter must strip iframe tags and inline style attributes."""

	def _clean(self, raw):
		from blog.templatetags.sanitize import sanitize_html
		return str(sanitize_html(raw))

	def test_iframe_is_stripped(self):
		out = self._clean('<p>Hi</p><iframe src="https://attacker.com/phish"></iframe>')
		self.assertNotIn('<iframe', out)
		self.assertNotIn('attacker.com', out)

	def test_inline_style_is_stripped(self):
		raw = '<div style="position:absolute;top:0;left:0;width:100%;height:100%;background:red">x</div>'
		out = self._clean(raw)
		self.assertNotIn('style=', out)
		self.assertIn('<div', out)

	def test_safe_tags_preserved(self):
		out = self._clean('<p class="lead"><strong>hi</strong> <a href="https://x">link</a></p>')
		self.assertIn('<strong>hi</strong>', out)
		self.assertIn('href="https://x"', out)

	def test_javascript_url_blocked(self):
		out = self._clean('<a href="javascript:alert(1)">click</a>')
		self.assertNotIn('javascript:', out)


class BlogPostBodyPlainTests(ModelTestMixin, TestCase):
	"""body_plain mirrors body with HTML stripped, populated in pre_save."""

	def test_body_plain_strips_html_on_save(self):
		from blog.models import BlogPost
		post = BlogPost.objects.create(
			title='HTML test', body='<p>Hello <strong>world</strong></p>',
			author=self.user, status='published',
		)
		self.assertEqual(post.body_plain, 'Hello world')

	def test_body_plain_collapses_whitespace(self):
		from blog.models import BlogPost
		post = BlogPost.objects.create(
			title='WS test', body='<p>Hello\n\n\n   <span>  world  </span></p>',
			author=self.user, status='published',
		)
		self.assertEqual(post.body_plain, 'Hello world')

	def test_body_plain_updates_when_body_changes(self):
		self.post.body = '<div>Updated content</div>'
		self.post.save()
		self.post.refresh_from_db()
		self.assertEqual(self.post.body_plain, 'Updated content')

	def test_body_plain_empty_when_body_empty(self):
		from blog.models import BlogPost
		post = BlogPost.objects.create(
			title='Empty', body='', author=self.user, status='published',
		)
		self.assertEqual(post.body_plain, '')


class SearchQueryTests(ModelTestMixin, TestCase):
	"""get_blog_queryset must use body_plain, search across multiple fields,
	enforce min length, and AND across multi-word queries."""

	def setUp(self):
		super().setUp()
		from account.models import Account
		from blog.models import BlogPost, Category, Tag
		self.author2 = Account.objects.create_user(
			email='alice@nyasablog.com', username='alicefarmer', password='x'  # pragma: allowlist secret
		)
		self.cat_tourism, _ = Category.objects.get_or_create(
			name='Tourism', slug='tourism', defaults={'description': ''}
		)
		self.tag_tea, _ = Tag.objects.get_or_create(name='Tea', slug='tea')
		# Three posts with different content to exercise each field.
		self.malawi_post = BlogPost.objects.create(
			title='Lake Malawi facts', body='<p>The lake is deep.</p>',
			author=self.user, status='published', category=self.category,
		)
		self.tea_post = BlogPost.objects.create(
			title='Thyolo highlands', body='<p>Tea farming in the south.</p>',
			author=self.author2, status='published', category=self.cat_tourism,
		)
		self.tea_post.tags.add(self.tag_tea)
		self.combined_post = BlogPost.objects.create(
			title='Malawi tea industry', body='<p>Both topics covered.</p>',
			author=self.user, status='published', category=self.cat_tourism,
		)
		self.combined_post.tags.add(self.tag_tea)
		self.draft_post = BlogPost.objects.create(
			title='Draft about Malawi', body='<p>Unpublished.</p>',
			author=self.user, status='draft',
		)

	def _q(self, query):
		from blog.views import get_blog_queryset
		return list(get_blog_queryset(query))

	def test_html_tag_names_no_longer_match(self):
		# `body` contains <p>...</p> but body_plain doesn't, so 'div' must miss.
		self.assertEqual(self._q('div'), [])
		self.assertEqual(self._q('class'), [])
		self.assertEqual(self._q('style'), [])

	def test_min_length_returns_empty(self):
		self.assertEqual(self._q('a'), [])
		self.assertEqual(self._q(''), [])
		self.assertEqual(self._q('   '), [])

	def test_search_by_title(self):
		results = self._q('Lake')
		self.assertIn(self.malawi_post, results)

	def test_search_by_body_plain(self):
		results = self._q('farming')
		self.assertIn(self.tea_post, results)

	def test_search_by_author_username(self):
		results = self._q('alicefarmer')
		self.assertIn(self.tea_post, results)
		self.assertNotIn(self.malawi_post, results)

	def test_search_by_category_name(self):
		results = self._q('Tourism')
		self.assertIn(self.tea_post, results)
		self.assertIn(self.combined_post, results)
		# malawi_post is in 'Culture', not 'Tourism'
		self.assertNotIn(self.malawi_post, results)

	def test_search_by_tag_name(self):
		results = self._q('Tea')
		self.assertIn(self.tea_post, results)
		self.assertIn(self.combined_post, results)

	def test_multi_word_uses_AND_semantics(self):
		# 'malawi tea' must require BOTH terms to appear somewhere
		results = self._q('malawi tea')
		self.assertIn(self.combined_post, results)
		# malawi_post has 'Malawi' (title) but no 'tea' anywhere
		self.assertNotIn(self.malawi_post, results)
		# tea_post has 'tea' (body+tag) but no 'malawi'
		self.assertNotIn(self.tea_post, results)

	def test_drafts_never_returned(self):
		results = self._q('Malawi')
		self.assertNotIn(self.draft_post, results)

	def test_results_distinct_when_multiple_tag_matches(self):
		# Add a second matching tag so the join would otherwise duplicate
		from blog.models import Tag
		t2, _ = Tag.objects.get_or_create(name='Teatime', slug='teatime')
		self.combined_post.tags.add(t2)
		results = self._q('tea')
		self.assertEqual(results.count(self.combined_post), 1)

	def test_AND_across_terms_split_across_separate_tags(self):
		"""Regression: a post with tags=['malawi-region', 'tea-farming'] and
		nothing else matching must still match the query 'malawi tea'.

		The previous implementation combined per-term Qs with & and passed
		one filter() call to the ORM, which collapsed the tag join into a
		single row — making this case incorrectly miss.
		"""
		from account.models import Account
		from blog.models import BlogPost, Tag
		# Author username and post title/body deliberately contain neither term.
		neutral_author = Account.objects.create_user(
			email='neutral@nyasablog.com', username='neutral', password='x',  # pragma: allowlist secret
		)
		split_tag_post = BlogPost.objects.create(
			title='Highland farming',
			body='<p>A profile of two regional industries.</p>',
			author=neutral_author, status='published', category=self.category,
		)
		t_malawi, _ = Tag.objects.get_or_create(name='malawi-region', slug='malawi-region')
		t_tea, _ = Tag.objects.get_or_create(name='tea-farming', slug='tea-farming')
		split_tag_post.tags.add(t_malawi, t_tea)
		self.assertIn(split_tag_post, self._q('malawi tea'))


class BodyPlainEntityDecodingTests(ModelTestMixin, TestCase):
	"""body_plain should decode HTML entities so search 'and' matches '&amp;' bodies."""

	def test_entities_are_decoded(self):
		from blog.models import BlogPost
		post = BlogPost.objects.create(
			title='Tea & coffee',
			body='<p>Tea &amp; coffee &mdash; tradition.</p>',
			author=self.user, status='published',
		)
		self.assertEqual(post.body_plain, 'Tea & coffee — tradition.')

	def test_search_finds_entity_decoded_text(self):
		from blog.models import BlogPost
		from blog.views import get_blog_queryset
		post = BlogPost.objects.create(
			title='Title without amp', body='<p>Coffee &amp; tea</p>',
			author=self.user, status='published',
		)
		# Searching the literal text 'Coffee & tea' should hit (after decoding)
		results = list(get_blog_queryset('Coffee tea'))
		self.assertIn(post, results)


class SearchViewIntegrationTests(ModelTestMixin, TestCase):
	"""End-to-end through the search view: min-length hint, dropdown vs full page."""

	def test_full_page_short_query_shows_too_short_hint(self):
		response = self.client.get(reverse('search'), {'q': 'a'})
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Keep typing')
		self.assertContains(response, 'at least 2 characters')

	def test_full_page_no_query_shows_default_empty_state(self):
		response = self.client.get(reverse('search'))
		self.assertContains(response, 'Enter a search term')

	def test_full_page_normal_query_returns_match(self):
		response = self.client.get(reverse('search'), {'q': 'Test'})
		self.assertEqual(response.status_code, 200)
		# Test Post (from ModelTestMixin) should match by title
		self.assertContains(response, 'Test Post')

	def test_dropdown_short_query_shows_hint(self):
		response = self.client.get(
			reverse('search'),
			{'q': 'a', 'partial': 'search_dropdown'},
			HTTP_HX_REQUEST='true',
		)
		self.assertContains(response, 'Type at least 2 characters')
