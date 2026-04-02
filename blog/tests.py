from django.test import TestCase, Client
from django.urls import reverse

from blog.models import BlogPost, Category, Tag, Comment, Like, Bookmark
from account.models import Account


class ModelTestMixin:
	"""Create shared test fixtures."""
	def setUp(self):
		self.user = Account.objects.create_user(
			email='test@nyasablog.com', username='testuser', password='testpass123'
		)
		self.user2 = Account.objects.create_user(
			email='other@nyasablog.com', username='otheruser', password='testpass123'
		)
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
		with self.assertRaises(Exception):
			Like.objects.create(post=self.post, user=self.user)

	def test_bookmark_creation(self):
		Bookmark.objects.create(post=self.post, user=self.user)
		self.assertEqual(self.post.bookmarks.count(), 1)

	def test_bookmark_unique_constraint(self):
		Bookmark.objects.create(post=self.post, user=self.user)
		with self.assertRaises(Exception):
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
		self.assertEqual(response.status_code, 401)

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
