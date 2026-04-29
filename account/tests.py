from django.core import mail
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase, RequestFactory
from django.urls import reverse
from rest_framework.test import APITestCase, APIClient
from rest_framework.authtoken.models import Token

from account.models import Account, UserProfile
from blog.models import BlogPost


class EmailVerifiedFieldTests(TestCase):
    def test_email_verified_defaults_to_false(self):
        from account.models import Account
        user = Account.objects.create_user(
            email='newuser@nyasablog.com', username='newuser', password='testpass123'  # pragma: allowlist secret
        )
        self.assertFalse(user.email_verified)


class AccountAPITestMixin:
    """Shared fixtures for account API tests."""

    def setUp(self):
        self.user = Account.objects.create_user(
            email='test@nyasablog.com', username='testuser', password='testpass123'
        )
        self.user2 = Account.objects.create_user(
            email='other@nyasablog.com', username='otheruser', password='testpass123'
        )
        self.token = Token.objects.get(user=self.user)
        self.token2 = Token.objects.get(user=self.user2)
        self.client = APIClient()

    def authenticate(self, user=None):
        token = Token.objects.get(user=user or self.user)
        self.client.credentials(HTTP_AUTHORIZATION='Token ' + token.key)

    def clear_auth(self):
        self.client.credentials()


class RegistrationAPITests(AccountAPITestMixin, APITestCase):

    def test_register_success(self):
        url = reverse('account_api:register')
        data = {
            'email': 'new@nyasablog.com',
            'username': 'newuser',
            'password': 'securepass123',
            'password2': 'securepass123',
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['response'], 'successfully registered new user.')
        self.assertIn('token', response.data)
        self.assertEqual(response.data['email'], 'new@nyasablog.com')
        self.assertEqual(response.data['username'], 'newuser')
        self.assertTrue(Account.objects.filter(email='new@nyasablog.com').exists())

    def test_register_duplicate_email(self):
        url = reverse('account_api:register')
        data = {
            'email': 'test@nyasablog.com',
            'username': 'differentuser',
            'password': 'securepass123',
            'password2': 'securepass123',
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['response'], 'Error')
        self.assertIn('email', response.data['error_message'].lower())

    def test_register_duplicate_username(self):
        url = reverse('account_api:register')
        data = {
            'email': 'unique@nyasablog.com',
            'username': 'testuser',
            'password': 'securepass123',
            'password2': 'securepass123',
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['response'], 'Error')
        self.assertIn('username', response.data['error_message'].lower())

    def test_register_password_mismatch(self):
        url = reverse('account_api:register')
        data = {
            'email': 'new@nyasablog.com',
            'username': 'newuser',
            'password': 'securepass123',
            'password2': 'differentpass',
        }
        response = self.client.post(url, data)
        self.assertIn('password', response.data)

    def test_register_missing_fields(self):
        url = reverse('account_api:register')
        response = self.client.post(url, {})
        self.assertEqual(response.status_code, 200)
        self.assertTrue('email' in response.data or 'username' in response.data)


class LoginAPITests(AccountAPITestMixin, APITestCase):

    def test_login_success(self):
        url = reverse('account_api:login')
        # Login view uses request.POST, so send form-encoded data
        response = self.client.post(url, {
            'username': 'test@nyasablog.com',
            'password': 'testpass123',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['response'], 'Successfully authenticated.')
        self.assertIn('token', response.data)
        self.assertEqual(response.data['pk'], self.user.pk)

    def test_login_invalid_password(self):
        url = reverse('account_api:login')
        response = self.client.post(url, {
            'username': 'test@nyasablog.com',
            'password': 'wrongpassword',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['response'], 'Error')
        self.assertEqual(response.data['error_message'], 'Invalid credentials')

    def test_login_nonexistent_email(self):
        url = reverse('account_api:login')
        response = self.client.post(url, {
            'username': 'nobody@nyasablog.com',
            'password': 'testpass123',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['response'], 'Error')


class AccountPropertiesAPITests(AccountAPITestMixin, APITestCase):

    def test_get_properties_success(self):
        self.authenticate()
        url = reverse('account_api:properties')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['pk'], self.user.pk)
        self.assertEqual(response.data['email'], 'test@nyasablog.com')
        self.assertEqual(response.data['username'], 'testuser')

    def test_get_properties_no_auth(self):
        url = reverse('account_api:properties')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 401)


class UpdateAccountAPITests(AccountAPITestMixin, APITestCase):

    def test_update_username_success(self):
        self.authenticate()
        url = reverse('account_api:update')
        response = self.client.put(url, {
            'email': 'test@nyasablog.com',
            'username': 'updateduser',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['response'], 'Account update success')
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, 'updateduser')

    def test_update_no_auth(self):
        url = reverse('account_api:update')
        response = self.client.put(url, {'username': 'hacker'})
        self.assertEqual(response.status_code, 401)

    def test_update_duplicate_email(self):
        self.authenticate()
        url = reverse('account_api:update')
        response = self.client.put(url, {
            'email': 'other@nyasablog.com',
            'username': 'testuser',
        })
        self.assertEqual(response.status_code, 400)


class ChangePasswordAPITests(AccountAPITestMixin, APITestCase):

    def test_change_password_success(self):
        self.authenticate()
        url = reverse('account_api:change_password')
        response = self.client.put(url, {
            'old_password': 'testpass123',
            'new_password': 'newsecurepass456',
            'confirm_new_password': 'newsecurepass456',
        })
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('newsecurepass456'))

    def test_change_password_wrong_old(self):
        self.authenticate()
        url = reverse('account_api:change_password')
        response = self.client.put(url, {
            'old_password': 'wrongpassword',
            'new_password': 'newsecurepass456',
            'confirm_new_password': 'newsecurepass456',
        })
        self.assertEqual(response.status_code, 400)
        self.assertIn('old_password', response.data)

    def test_change_password_mismatch_new(self):
        self.authenticate()
        url = reverse('account_api:change_password')
        response = self.client.put(url, {
            'old_password': 'testpass123',
            'new_password': 'newsecurepass456',
            'confirm_new_password': 'different789',
        })
        self.assertEqual(response.status_code, 400)

    def test_change_password_no_auth(self):
        url = reverse('account_api:change_password')
        response = self.client.put(url, {
            'old_password': 'testpass123',
            'new_password': 'new123',
            'confirm_new_password': 'new123',
        })
        self.assertEqual(response.status_code, 401)


class CheckAccountExistsAPITests(AccountAPITestMixin, APITestCase):

    def test_account_exists(self):
        url = reverse('account_api:check_if_account_exists')
        response = self.client.get(url, {'email': 'test@nyasablog.com'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['response'], 'test@nyasablog.com')

    def test_account_does_not_exist(self):
        url = reverse('account_api:check_if_account_exists')
        response = self.client.get(url, {'email': 'nobody@nyasablog.com'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['response'], 'Account does not exist')


class AuthorProfileAPITests(AccountAPITestMixin, APITestCase):

    def test_author_profile_success(self):
        BlogPost.objects.create(
            title='Test Post', body='Content for the test post.',
            author=self.user, status='published'
        )
        url = reverse('account_api:author_profile', args=['testuser'])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['username'], 'testuser')
        self.assertEqual(response.data['post_count'], 1)
        self.assertEqual(response.data['total_views'], 0)

    def test_author_profile_excludes_drafts(self):
        BlogPost.objects.create(
            title='Published', body='Content.', author=self.user, status='published'
        )
        BlogPost.objects.create(
            title='Draft', body='Hidden.', author=self.user, status='draft'
        )
        url = reverse('account_api:author_profile', args=['testuser'])
        response = self.client.get(url)
        self.assertEqual(response.data['post_count'], 1)

    def test_author_profile_not_found(self):
        url = reverse('account_api:author_profile', args=['nobody'])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_author_profile_no_auth_required(self):
        self.clear_auth()
        url = reverse('account_api:author_profile', args=['testuser'])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)


class UpdateProfileAPITests(AccountAPITestMixin, APITestCase):

    def test_update_profile_success(self):
        self.authenticate()
        url = reverse('account_api:update_profile')
        response = self.client.put(url, {
            'bio': 'Malawian blogger',
            'location': 'Lilongwe',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['bio'], 'Malawian blogger')
        self.assertEqual(response.data['location'], 'Lilongwe')

    def test_update_profile_partial(self):
        self.authenticate()
        url = reverse('account_api:update_profile')
        response = self.client.put(url, {'bio': 'Just a bio'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['bio'], 'Just a bio')

    def test_update_profile_no_auth(self):
        url = reverse('account_api:update_profile')
        response = self.client.put(url, {'bio': 'Hacked bio'})
        self.assertEqual(response.status_code, 401)


class GrandfatherMigrationTests(TransactionTestCase):
    """Test the grandfather data migration in isolation."""

    migrate_from = ("account", "0005_account_email_verified")
    migrate_to = ("account", "0006_grandfather_existing_users")

    def setUp(self):
        executor = MigrationExecutor(connection)
        # Roll back to the state just before the grandfather migration.
        executor.migrate([self.migrate_from])
        # Build the historical apps state including the blog app (which has its
        # latest migration applied — only the account app is rolled back).
        blog_leaf = next(
            node for node in executor.loader.graph.leaf_nodes()
            if node[0] == "blog"
        )
        old_apps = executor.loader.project_state(
            [self.migrate_from, blog_leaf]
        ).apps
        Account = old_apps.get_model("account", "Account")
        BlogPost = old_apps.get_model("blog", "BlogPost")
        # Staff user (no posts)
        self.staff = Account.objects.create(
            email='staff@nyasablog.com', username='staff', password='x',  # pragma: allowlist secret
            is_staff=True, email_verified=False,
        )
        # Contributor (has a post)
        self.author = Account.objects.create(
            email='author@nyasablog.com', username='author', password='x',  # pragma: allowlist secret
            email_verified=False,
        )
        BlogPost.objects.create(
            title='Post', body='Body', author=self.author, status='published',
            slug='author-post',
        )
        # Lurker (no posts, not staff)
        self.lurker = Account.objects.create(
            email='lurker@nyasablog.com', username='lurker', password='x',  # pragma: allowlist secret
            email_verified=False,
        )
        # Apply the grandfather migration
        executor.loader.build_graph()
        executor.migrate([self.migrate_to])
        new_apps = executor.loader.project_state([self.migrate_to]).apps
        self.Account = new_apps.get_model("account", "Account")

    def test_grandfather_migration_marks_staff_verified(self):
        self.assertTrue(self.Account.objects.get(pk=self.staff.pk).email_verified)

    def test_grandfather_migration_marks_contributor_verified(self):
        self.assertTrue(self.Account.objects.get(pk=self.author.pk).email_verified)

    def test_grandfather_migration_leaves_lurker_unverified(self):
        self.assertFalse(self.Account.objects.get(pk=self.lurker.pk).email_verified)

    def test_grandfather_migration_idempotent(self):
        # Re-applying the migration must not regress anyone's state.
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate([self.migrate_from])
        executor.loader.build_graph()
        executor.migrate([self.migrate_to])
        self.assertTrue(self.Account.objects.get(pk=self.staff.pk).email_verified)
        self.assertTrue(self.Account.objects.get(pk=self.author.pk).email_verified)
        self.assertFalse(self.Account.objects.get(pk=self.lurker.pk).email_verified)


class EmailVerificationTokenTests(TestCase):
    def setUp(self):
        from account.models import Account
        self.user = Account.objects.create_user(
            email='token@nyasablog.com', username='tokenuser', password='testpass123'  # pragma: allowlist secret
        )

    def test_token_invalidated_after_first_use(self):
        from account.tokens import email_verification_token
        token = email_verification_token.make_token(self.user)
        self.assertTrue(email_verification_token.check_token(self.user, token))
        # Simulate verification:
        self.user.email_verified = True
        self.user.save()
        self.assertFalse(email_verification_token.check_token(self.user, token))

    def test_token_valid_for_unverified_user(self):
        from account.tokens import email_verification_token
        token = email_verification_token.make_token(self.user)
        self.assertTrue(email_verification_token.check_token(self.user, token))


class SendVerificationEmailTests(TestCase):
    def setUp(self):
        from account.models import Account
        self.user = Account.objects.create_user(
            email='mailto@nyasablog.com', username='mailtouser', password='testpass123'  # pragma: allowlist secret
        )
        self.factory = RequestFactory()

    def test_send_verification_email_appends_to_outbox(self):
        from account.emails import send_verification_email
        request = self.factory.get('/')
        request.META['HTTP_HOST'] = 'nyasablog.com'
        send_verification_email(self.user, request)
        self.assertEqual(len(mail.outbox), 1)
        msg = mail.outbox[0]
        self.assertEqual(msg.to, [self.user.email])
        self.assertIn('confirm-email', msg.body)
        self.assertIn('nyasablog.com', msg.body)
