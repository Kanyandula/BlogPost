import io
import tempfile
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from PIL import Image

TEMP_MEDIA_ROOT = tempfile.mkdtemp()
from rest_framework.test import APITestCase, APIClient
from rest_framework.authtoken.models import Token

from account.models import Account
from blog.models import BlogPost, Category, Tag, Comment, Like, Bookmark


def create_test_image(name='test.jpg', size=(200, 100)):
    """Create a real in-memory JPEG image for upload tests."""
    img = Image.new('RGB', size, color='red')
    buf = io.BytesIO()
    img.save(buf, format='JPEG')
    buf.seek(0)
    return SimpleUploadedFile(name, buf.read(), content_type='image/jpeg')


class BlogAPITestMixin:
    """Shared fixtures for blog API tests."""

    def setUp(self):
        self.user = Account.objects.create_user(
            email='test@nyasablog.com', username='testuser', password='testpass123'
        )
        self.user2 = Account.objects.create_user(
            email='other@nyasablog.com', username='otheruser', password='testpass123'
        )
        self.token = Token.objects.get(user=self.user)
        self.token2 = Token.objects.get(user=self.user2)
        self.category, _ = Category.objects.get_or_create(name='Culture', slug='culture', defaults={'description': 'Test'})
        self.tag, _ = Tag.objects.get_or_create(name='Malawi', slug='malawi')
        self.published_post = BlogPost.objects.create(
            title='Published Post',
            body='This is a published blog post with enough content for validation to pass easily.',
            author=self.user, status='published', category=self.category
        )
        self.published_post.tags.add(self.tag)
        self.draft_post = BlogPost.objects.create(
            title='Draft Post',
            body='This is a draft blog post content.',
            author=self.user, status='draft'
        )
        self.client = APIClient()

    def authenticate(self, user=None):
        token = Token.objects.get(user=user or self.user)
        self.client.credentials(HTTP_AUTHORIZATION='Token ' + token.key)

    def clear_auth(self):
        self.client.credentials()


# --- Blog Post CRUD ---

class BlogPostCreateAPITests(BlogAPITestMixin, APITestCase):

    @override_settings(MEDIA_ROOT=TEMP_MEDIA_ROOT)
    @patch('blog.api.serializers.is_image_aspect_ratio_valid', return_value=True)
    @patch('blog.api.serializers.validate_image_upload', return_value=(True, None))
    @patch('blog.api.serializers.FileSystemStorage')
    def test_create_post_success(self, mock_storage, mock_validate, mock_aspect):
        mock_storage.return_value.open.return_value.__enter__ = lambda s: s
        mock_storage.return_value.open.return_value.__exit__ = lambda s, *a: None
        mock_storage.return_value.open.return_value.write = lambda *a: None
        self.authenticate()
        image = create_test_image()
        url = reverse('blog_api:create')
        response = self.client.post(url, {
            'title': 'A New Blog Post Title',
            'body': 'This is the body of a new blog post with enough content to pass the fifty character minimum validation requirement.',
            'image': image,
        }, format='multipart')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['response'], 'created')
        self.assertIn('pk', response.data)
        self.assertIn('slug', response.data)
        self.assertEqual(response.data['username'], 'testuser')

    def test_create_post_no_auth(self):
        url = reverse('blog_api:create')
        response = self.client.post(url, {'title': 'Test', 'body': 'Content'})
        self.assertEqual(response.status_code, 401)

    def test_create_post_missing_image(self):
        self.authenticate()
        url = reverse('blog_api:create')
        response = self.client.post(url, {
            'title': 'A Valid Title',
            'body': 'This body has more than fifty characters so it should pass validation easily.',
        }, format='multipart')
        self.assertEqual(response.status_code, 400)

    def test_create_post_title_too_short(self):
        self.authenticate()
        image = create_test_image()
        url = reverse('blog_api:create')
        response = self.client.post(url, {
            'title': 'Hi',
            'body': 'This body has more than fifty characters so it should pass validation easily.',
            'image': image,
        }, format='multipart')
        self.assertEqual(response.status_code, 400)


class BlogPostListAPITests(BlogAPITestMixin, APITestCase):

    def test_list_posts_success(self):
        self.authenticate()
        url = reverse('blog_api:list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn('results', response.data)
        slugs = [p['slug'] for p in response.data['results']]
        self.assertIn(self.published_post.slug, slugs)

    def test_list_posts_hides_drafts_from_non_staff(self):
        self.authenticate()
        url = reverse('blog_api:list')
        response = self.client.get(url)
        slugs = [p['slug'] for p in response.data['results']]
        self.assertNotIn(self.draft_post.slug, slugs)

    def test_list_posts_no_auth(self):
        url = reverse('blog_api:list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 401)

    def test_list_posts_pagination(self):
        self.authenticate()
        # Create 12 more published posts (total 13 with setUp's 1 published)
        for i in range(12):
            BlogPost.objects.create(
                title=f'Post Number {i}',
                body='Content for pagination test.',
                author=self.user, status='published'
            )
        url = reverse('blog_api:list')
        response = self.client.get(url)
        self.assertEqual(len(response.data['results']), 10)  # PAGE_SIZE=10
        response2 = self.client.get(url, {'page': 2})
        self.assertEqual(response2.status_code, 200)
        self.assertGreater(len(response2.data['results']), 0)

    def test_list_posts_search(self):
        self.authenticate()
        url = reverse('blog_api:list')
        response = self.client.get(url, {'search': 'Published Post'})
        self.assertEqual(response.status_code, 200)
        self.assertGreater(response.data['count'], 0)

    def test_list_posts_category_filter(self):
        self.authenticate()
        url = reverse('blog_api:list')
        response = self.client.get(url, {'category': 'culture'})
        self.assertEqual(response.status_code, 200)
        for post in response.data['results']:
            self.assertEqual(post['category']['slug'], 'culture')

    def test_list_posts_staff_sees_drafts(self):
        self.user.is_staff = True
        self.user.save()
        self.authenticate()
        url = reverse('blog_api:list')
        response = self.client.get(url)
        slugs = [p['slug'] for p in response.data['results']]
        self.assertIn(self.draft_post.slug, slugs)

    def test_list_posts_staff_status_filter(self):
        self.user.is_staff = True
        self.user.save()
        self.authenticate()
        url = reverse('blog_api:list')
        response = self.client.get(url, {'status': 'draft'})
        for post in response.data['results']:
            self.assertEqual(post['status'], 'draft')

    def test_list_posts_ordering(self):
        self.authenticate()
        BlogPost.objects.create(
            title='Popular Post', body='Content.',
            author=self.user, status='published', view_count=100
        )
        url = reverse('blog_api:list')
        response = self.client.get(url, {'ordering': '-view_count'})
        self.assertEqual(response.status_code, 200)
        views = [p['view_count'] for p in response.data['results']]
        self.assertEqual(views, sorted(views, reverse=True))


class BlogPostDetailAPITests(BlogAPITestMixin, APITestCase):

    def test_detail_success(self):
        self.authenticate()
        url = reverse('blog_api:detail', args=[self.published_post.slug])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['title'], 'Published Post')
        self.assertEqual(response.data['username'], 'testuser')
        # Verify nested serializer fields
        self.assertIn('category', response.data)
        self.assertIn('tags', response.data)
        self.assertIn('like_count', response.data)
        self.assertIn('comment_count', response.data)
        self.assertIn('reading_time', response.data)

    def test_detail_no_auth(self):
        url = reverse('blog_api:detail', args=[self.published_post.slug])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 401)

    def test_detail_not_found(self):
        self.authenticate()
        url = reverse('blog_api:detail', args=['nonexistent-slug'])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)


class BlogPostUpdateAPITests(BlogAPITestMixin, APITestCase):

    def test_update_post_success(self):
        self.authenticate()
        url = reverse('blog_api:update', args=[self.published_post.slug])
        response = self.client.put(url, {
            'title': 'Updated Title Here',
            'body': 'This is the updated body content with enough characters to pass the fifty character minimum.',
        }, format='multipart')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['response'], 'updated')
        self.published_post.refresh_from_db()
        self.assertEqual(self.published_post.title, 'Updated Title Here')

    def test_update_post_no_auth(self):
        url = reverse('blog_api:update', args=[self.published_post.slug])
        response = self.client.put(url, {'title': 'Hacked'})
        self.assertEqual(response.status_code, 401)

    def test_update_post_non_author(self):
        self.authenticate(self.user2)
        url = reverse('blog_api:update', args=[self.published_post.slug])
        response = self.client.put(url, {'title': 'Not My Post'})
        # API returns 200 with error message (known quirk)
        self.assertEqual(response.status_code, 200)
        self.assertIn("don't have permission", response.data['response'])

    def test_update_post_not_found(self):
        self.authenticate()
        url = reverse('blog_api:update', args=['nonexistent-slug'])
        response = self.client.put(url, {'title': 'Test'})
        self.assertEqual(response.status_code, 404)


class BlogPostDeleteAPITests(BlogAPITestMixin, APITestCase):

    def test_delete_post_success(self):
        self.authenticate()
        slug = self.published_post.slug
        url = reverse('blog_api:delete', args=[slug])
        response = self.client.delete(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['response'], 'deleted')
        self.assertFalse(BlogPost.objects.filter(slug=slug).exists())

    def test_delete_post_no_auth(self):
        url = reverse('blog_api:delete', args=[self.published_post.slug])
        response = self.client.delete(url)
        self.assertEqual(response.status_code, 401)

    def test_delete_post_non_author(self):
        self.authenticate(self.user2)
        url = reverse('blog_api:delete', args=[self.published_post.slug])
        response = self.client.delete(url)
        # API returns 200 with error message (known quirk)
        self.assertEqual(response.status_code, 200)
        self.assertIn("don't have permission", response.data['response'])
        self.assertTrue(BlogPost.objects.filter(slug=self.published_post.slug).exists())

    def test_delete_post_not_found(self):
        self.authenticate()
        url = reverse('blog_api:delete', args=['nonexistent-slug'])
        response = self.client.delete(url)
        self.assertEqual(response.status_code, 404)


class BlogPostIsAuthorAPITests(BlogAPITestMixin, APITestCase):

    def test_is_author_true(self):
        self.authenticate()
        url = reverse('blog_api:is_author', args=[self.published_post.slug])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn('permission to edit', response.data['response'])

    def test_is_author_false(self):
        self.authenticate(self.user2)
        url = reverse('blog_api:is_author', args=[self.published_post.slug])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("don't have permission", response.data['response'])

    def test_is_author_no_auth(self):
        url = reverse('blog_api:is_author', args=[self.published_post.slug])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 401)

    def test_is_author_not_found(self):
        self.authenticate()
        url = reverse('blog_api:is_author', args=['nonexistent-slug'])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)


# --- Categories & Tags ---

class CategoriesAPITests(BlogAPITestMixin, APITestCase):

    def test_list_categories(self):
        url = reverse('blog_api:categories')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertGreater(len(response.data), 0)
        self.assertEqual(response.data[0]['name'], 'Culture')

    def test_list_categories_no_auth_required(self):
        self.clear_auth()
        url = reverse('blog_api:categories')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)


class TagsAPITests(BlogAPITestMixin, APITestCase):

    def test_list_tags(self):
        url = reverse('blog_api:tags')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertGreater(len(response.data), 0)
        self.assertEqual(response.data[0]['name'], 'Malawi')

    def test_list_tags_no_auth_required(self):
        self.clear_auth()
        url = reverse('blog_api:tags')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)


# --- Comments ---

class CommentsAPITests(BlogAPITestMixin, APITestCase):

    def test_get_comments_success(self):
        Comment.objects.create(post=self.published_post, author=self.user, body='Great post!')
        url = reverse('blog_api:comments', args=[self.published_post.slug])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['body'], 'Great post!')
        self.assertEqual(response.data[0]['username'], 'testuser')

    def test_get_comments_no_auth_required(self):
        url = reverse('blog_api:comments', args=[self.published_post.slug])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_get_comments_post_not_found(self):
        url = reverse('blog_api:comments', args=['nonexistent-slug'])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_get_comments_with_replies(self):
        parent = Comment.objects.create(post=self.published_post, author=self.user, body='Parent')
        Comment.objects.create(post=self.published_post, author=self.user2, body='Reply', parent=parent)
        url = reverse('blog_api:comments', args=[self.published_post.slug])
        response = self.client.get(url)
        self.assertEqual(len(response.data), 1)  # Only top-level
        self.assertEqual(len(response.data[0]['replies']), 1)

    def test_get_comments_excludes_inactive(self):
        Comment.objects.create(
            post=self.published_post, author=self.user, body='Hidden', is_active=False
        )
        url = reverse('blog_api:comments', args=[self.published_post.slug])
        response = self.client.get(url)
        self.assertEqual(len(response.data), 0)

    def test_create_comment_success(self):
        self.authenticate()
        url = reverse('blog_api:create_comment', args=[self.published_post.slug])
        response = self.client.post(url, {'body': 'Nice article!'})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['body'], 'Nice article!')
        self.assertEqual(Comment.objects.count(), 1)

    def test_create_comment_no_auth(self):
        url = reverse('blog_api:create_comment', args=[self.published_post.slug])
        response = self.client.post(url, {'body': 'Anonymous'})
        self.assertEqual(response.status_code, 401)

    def test_create_comment_post_not_found(self):
        self.authenticate()
        url = reverse('blog_api:create_comment', args=['nonexistent-slug'])
        response = self.client.post(url, {'body': 'Test'})
        self.assertEqual(response.status_code, 404)

    def test_create_reply_success(self):
        self.authenticate()
        parent = Comment.objects.create(post=self.published_post, author=self.user, body='Parent')
        url = reverse('blog_api:create_comment', args=[self.published_post.slug])
        response = self.client.post(url, {'body': 'Reply here', 'parent': parent.pk})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Comment.objects.filter(parent=parent).count(), 1)

    def test_create_nested_reply_rejected(self):
        self.authenticate()
        parent = Comment.objects.create(post=self.published_post, author=self.user, body='Parent')
        reply = Comment.objects.create(
            post=self.published_post, author=self.user2, body='Reply', parent=parent
        )
        url = reverse('blog_api:create_comment', args=[self.published_post.slug])
        response = self.client.post(url, {'body': 'Nested reply', 'parent': reply.pk})
        self.assertEqual(response.status_code, 400)

    def test_delete_comment_success(self):
        self.authenticate()
        comment = Comment.objects.create(post=self.published_post, author=self.user, body='To delete')
        url = reverse('blog_api:delete_comment', args=[comment.pk])
        response = self.client.delete(url)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Comment.objects.filter(pk=comment.pk).exists())

    def test_delete_comment_non_author(self):
        self.authenticate(self.user2)
        comment = Comment.objects.create(post=self.published_post, author=self.user, body='Not yours')
        url = reverse('blog_api:delete_comment', args=[comment.pk])
        response = self.client.delete(url)
        self.assertEqual(response.status_code, 403)

    def test_delete_comment_no_auth(self):
        comment = Comment.objects.create(post=self.published_post, author=self.user, body='Test')
        url = reverse('blog_api:delete_comment', args=[comment.pk])
        response = self.client.delete(url)
        self.assertEqual(response.status_code, 401)

    def test_delete_comment_not_found(self):
        self.authenticate()
        url = reverse('blog_api:delete_comment', args=[99999])
        response = self.client.delete(url)
        self.assertEqual(response.status_code, 404)


# --- Likes ---

class LikeAPITests(BlogAPITestMixin, APITestCase):

    def test_like_toggle_on(self):
        self.authenticate()
        url = reverse('blog_api:like', args=[self.published_post.slug])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['liked'])
        self.assertEqual(response.data['count'], 1)

    def test_like_toggle_off(self):
        self.authenticate()
        url = reverse('blog_api:like', args=[self.published_post.slug])
        self.client.post(url)  # Like
        response = self.client.post(url)  # Unlike
        self.assertFalse(response.data['liked'])
        self.assertEqual(response.data['count'], 0)

    def test_like_no_auth(self):
        url = reverse('blog_api:like', args=[self.published_post.slug])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 401)

    def test_like_post_not_found(self):
        self.authenticate()
        url = reverse('blog_api:like', args=['nonexistent-slug'])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 404)

    def test_like_count_multiple_users(self):
        self.authenticate()
        url = reverse('blog_api:like', args=[self.published_post.slug])
        self.client.post(url)
        self.authenticate(self.user2)
        response = self.client.post(url)
        self.assertEqual(response.data['count'], 2)


# --- Bookmarks ---

class BookmarkAPITests(BlogAPITestMixin, APITestCase):

    def test_bookmark_toggle_on(self):
        self.authenticate()
        url = reverse('blog_api:bookmark', args=[self.published_post.slug])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['bookmarked'])

    def test_bookmark_toggle_off(self):
        self.authenticate()
        url = reverse('blog_api:bookmark', args=[self.published_post.slug])
        self.client.post(url)  # Bookmark
        response = self.client.post(url)  # Unbookmark
        self.assertFalse(response.data['bookmarked'])

    def test_bookmark_no_auth(self):
        url = reverse('blog_api:bookmark', args=[self.published_post.slug])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 401)

    def test_bookmark_post_not_found(self):
        self.authenticate()
        url = reverse('blog_api:bookmark', args=['nonexistent-slug'])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 404)

    def test_get_bookmarks_success(self):
        self.authenticate()
        Bookmark.objects.create(post=self.published_post, user=self.user)
        url = reverse('blog_api:bookmarks')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['slug'], self.published_post.slug)

    def test_get_bookmarks_empty(self):
        self.authenticate()
        url = reverse('blog_api:bookmarks')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 0)

    def test_get_bookmarks_no_auth(self):
        url = reverse('blog_api:bookmarks')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 401)

    def test_bookmarks_user_isolation(self):
        Bookmark.objects.create(post=self.published_post, user=self.user)
        self.authenticate(self.user2)
        url = reverse('blog_api:bookmarks')
        response = self.client.get(url)
        self.assertEqual(len(response.data), 0)
