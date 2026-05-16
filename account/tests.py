from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.conf import settings
from django.core import mail
from django.core.cache import cache
from django.core.mail import get_connection
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import RequestFactory, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient, APIRequestFactory, APITestCase
from rest_framework.views import APIView

from account.models import Account
from blog.models import BlogPost


class WebRegistrationTests(TestCase):
    def test_registration_creates_inactive_unverified_account(self):
        response = self.client.post(reverse('register'), {
            'email': 'fresh@nyasablog.com',
            'username': 'freshuser',
            'password1': 'testpass123!',  # pragma: allowlist secret
            'password2': 'testpass123!',  # pragma: allowlist secret
        })
        user = Account.objects.get(email='fresh@nyasablog.com')
        self.assertFalse(user.is_active)
        self.assertFalse(user.email_verified)
        self.assertRedirects(response, reverse('verification_sent') + '?email=fresh%40nyasablog.com')

    def test_registration_sends_verification_email(self):
        self.client.post(reverse('register'), {
            'email': 'fresh@nyasablog.com',
            'username': 'freshuser',
            'password1': 'testpass123!',  # pragma: allowlist secret
            'password2': 'testpass123!',  # pragma: allowlist secret
        })
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('Verify your', mail.outbox[0].subject)

    def test_registration_does_not_log_user_in(self):
        self.client.post(reverse('register'), {
            'email': 'fresh@nyasablog.com',
            'username': 'freshuser',
            'password1': 'testpass123!',  # pragma: allowlist secret
            'password2': 'testpass123!',  # pragma: allowlist secret
        })
        # Subsequent request should be unauthenticated
        response = self.client.get(reverse('home'))
        self.assertFalse(response.wsgi_request.user.is_authenticated)


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

        self.user.email_verified = True
        self.user.save()
        self.user2.email_verified = True
        self.user2.save()

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


class AccountPropertiesEmailVerifiedTests(AccountAPITestMixin, APITestCase):
    def test_api_properties_includes_email_verified_field(self):
        self.user.email_verified = True
        self.user.save()
        self.authenticate()
        url = reverse('account_api:properties')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn('email_verified', response.data)
        self.assertTrue(response.data['email_verified'])


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

    @override_settings(SITE_DOMAIN='nyasablog.com', SITE_PROTOCOL='https')
    def test_send_verification_email_appends_to_outbox(self):
        from account.emails import send_verification_email
        send_verification_email(self.user)
        self.assertEqual(len(mail.outbox), 1)
        msg = mail.outbox[0]
        self.assertEqual(msg.to, [self.user.email])
        self.assertIn('confirm-email', msg.body)
        self.assertIn('https://nyasablog.com/confirm-email/', msg.body)

    @override_settings(SITE_DOMAIN='nyasablog.com', SITE_PROTOCOL='https')
    def test_send_verification_email_ignores_request_host_header(self):
        """Forged Host header must not influence the verification link."""
        from account.emails import send_verification_email
        request = self.factory.get('/')
        request.META['HTTP_HOST'] = 'attacker.example'
        send_verification_email(self.user, request)
        msg = mail.outbox[0]
        self.assertNotIn('attacker.example', msg.body)
        self.assertIn('https://nyasablog.com/', msg.body)


class ConfirmEmailViewTests(TestCase):
    def setUp(self):
        from account.models import Account
        self.user = Account.objects.create_user(
            email='confirm@nyasablog.com', username='confirmuser', password='testpass123'  # pragma: allowlist secret
        )
        self.user.is_active = False
        self.user.save()
        self.uidb64 = urlsafe_base64_encode(force_bytes(self.user.pk))
        from account.tokens import email_verification_token
        self.valid_token = email_verification_token.make_token(self.user)

    def test_confirm_email_with_valid_token_activates_account(self):
        url = reverse('confirm_email', kwargs={'uidb64': self.uidb64, 'token': self.valid_token})
        self.client.get(url)
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)
        self.assertTrue(self.user.email_verified)

    def test_confirm_email_with_invalid_token_shows_error_page(self):
        url = reverse('confirm_email', kwargs={'uidb64': self.uidb64, 'token': 'bogus-token'})
        response = self.client.get(url)
        self.assertTemplateUsed(response, 'account/verification_invalid.html')
        self.user.refresh_from_db()
        self.assertFalse(self.user.email_verified)

    def test_confirm_email_with_expired_token_shows_error_page(self):
        from datetime import datetime

        from account.tokens import email_verification_token
        token = email_verification_token.make_token(self.user)
        future = datetime.now() + timedelta(days=4)
        with patch('django.contrib.auth.tokens.PasswordResetTokenGenerator._now', return_value=future):
            url = reverse('confirm_email', kwargs={'uidb64': self.uidb64, 'token': token})
            response = self.client.get(url)
        self.assertTemplateUsed(response, 'account/verification_invalid.html')

    def test_token_invalidated_after_first_use_via_view(self):
        url = reverse('confirm_email', kwargs={'uidb64': self.uidb64, 'token': self.valid_token})
        self.client.get(url)  # first use — succeeds
        self.client.logout()
        # Second use: user is already verified, so the early-return redirects to login
        # rather than re-running activation.
        response = self.client.get(url)
        self.assertRedirects(response, reverse('login'))
        self.user.refresh_from_db()
        self.assertTrue(self.user.email_verified)

    def test_confirm_email_success_sets_messages_framework(self):
        url = reverse('confirm_email', kwargs={'uidb64': self.uidb64, 'token': self.valid_token})
        response = self.client.get(url, follow=True)
        messages = list(response.context['messages'])
        self.assertEqual(len(messages), 1)
        self.assertIn('verified', str(messages[0]).lower())

    def test_confirm_email_success_renders_toast_message_in_html(self):
        url = reverse('confirm_email', kwargs={'uidb64': self.uidb64, 'token': self.valid_token})
        response = self.client.get(url, follow=True)
        # The actual message text should appear in the toast script block in base.html
        self.assertContains(response, 'Email verified')

    def test_confirm_email_when_already_verified_redirects_to_login(self):
        self.user.email_verified = True
        self.user.is_active = True
        self.user.save()
        # Make a fresh token (pre-flip token would be invalidated)
        from account.tokens import email_verification_token
        token = email_verification_token.make_token(self.user)
        # But since the token is for an already-verified user, we test the early-return path.
        # Actually with email_verified=True, the token will check successfully (since hash includes
        # email_verified=True at make-time). The early-return ensures the user is redirected to
        # login rather than re-running the activation.
        url = reverse('confirm_email', kwargs={'uidb64': self.uidb64, 'token': token})
        response = self.client.get(url)
        self.assertRedirects(response, reverse('login'))


class WebLoginTests(TestCase):
    def setUp(self):
        from account.models import Account
        # Verified user
        self.verified = Account.objects.create_user(
            email='verified@nyasablog.com', username='verifieduser', password='testpass123'  # pragma: allowlist secret
        )
        self.verified.email_verified = True
        self.verified.save()
        # Unverified user (is_active=True since create_user defaults that)
        self.unverified = Account.objects.create_user(
            email='unverified@nyasablog.com', username='unverifieduser', password='testpass123'  # pragma: allowlist secret
        )

    def test_unverified_user_cannot_log_in(self):
        response = self.client.post(reverse('login'), {
            'email': 'unverified@nyasablog.com',
            'password': 'testpass123',  # pragma: allowlist secret
        }, follow=False)
        self.assertFalse(response.wsgi_request.user.is_authenticated)
        self.assertContains(response, 'Invalid email or password.', status_code=200)
        self.assertContains(response, 'Resend')

    def test_failed_login_with_wrong_password_shows_error_message(self):
        response = self.client.post(reverse('login'), {
            'email': 'verified@nyasablog.com',
            'password': 'wrongpassword',  # pragma: allowlist secret
        })
        self.assertFalse(response.wsgi_request.user.is_authenticated)
        self.assertContains(response, 'Invalid email or password.', status_code=200)

    def test_inactive_unverified_user_cannot_log_in(self):
        # Mirrors what web registration_view produces (is_active=False, email_verified=False).
        # Locks in that the email_verified gate works regardless of is_active state, since
        # AllowAllUsersModelBackend lets inactive users through authenticate().
        self.unverified.is_active = False
        self.unverified.save()
        response = self.client.post(reverse('login'), {
            'email': 'unverified@nyasablog.com',
            'password': 'testpass123',  # pragma: allowlist secret
        })
        self.assertFalse(response.wsgi_request.user.is_authenticated)
        self.assertContains(response, 'Invalid email or password.', status_code=200)

    def test_unverified_and_wrong_password_render_identical_error(self):
        wrong_pw = self.client.post(reverse('login'), {
            'email': 'verified@nyasablog.com',
            'password': 'wrongpassword',  # pragma: allowlist secret
        })
        unverified = self.client.post(reverse('login'), {
            'email': 'unverified@nyasablog.com',
            'password': 'testpass123',  # pragma: allowlist secret
        })
        # Both should render the exact same error text — no enumeration leak.
        self.assertContains(wrong_pw, 'Invalid email or password.')
        self.assertContains(unverified, 'Invalid email or password.')

    def test_login_with_wrong_password_for_unverified_account_does_not_send_email(self):
        from django.core import mail
        before = len(mail.outbox)
        self.client.post(reverse('login'), {
            'email': 'unverified@nyasablog.com',
            'password': 'wrongpassword',  # pragma: allowlist secret
        })
        self.assertEqual(len(mail.outbox), before)

    def test_verified_user_logs_in_successfully(self):
        response = self.client.post(reverse('login'), {
            'email': 'verified@nyasablog.com',
            'password': 'testpass123',  # pragma: allowlist secret
        }, follow=True)
        self.assertTrue(response.wsgi_request.user.is_authenticated)


class ResendVerificationViewTests(TestCase):
    def setUp(self):
        from account.models import Account
        self.unverified = Account.objects.create_user(
            email='resend@nyasablog.com', username='resenduser', password='testpass123'  # pragma: allowlist secret
        )
        self.verified = Account.objects.create_user(
            email='already@nyasablog.com', username='alreadyuser', password='testpass123'  # pragma: allowlist secret
        )
        self.verified.email_verified = True
        self.verified.save()
        cache.clear()

    def test_resend_verification_sends_for_unverified(self):
        from django.core import mail
        before = len(mail.outbox)
        self.client.post(reverse('resend_verification'), {'email': 'resend@nyasablog.com'})
        self.assertEqual(len(mail.outbox), before + 1)
        self.assertEqual(mail.outbox[-1].to, ['resend@nyasablog.com'])

    def test_resend_verification_silent_for_unknown_email(self):
        from django.core import mail
        before = len(mail.outbox)
        self.client.post(reverse('resend_verification'), {'email': 'nobody@nyasablog.com'})
        self.assertEqual(len(mail.outbox), before)

    def test_resend_verification_silent_for_verified_email(self):
        from django.core import mail
        before = len(mail.outbox)
        self.client.post(reverse('resend_verification'), {'email': 'already@nyasablog.com'})
        self.assertEqual(len(mail.outbox), before)

    def test_resend_response_identical_for_known_and_unknown(self):
        # Hit the same email, once when the account exists, once after deletion.
        # Bodies must be byte-identical to prevent enumeration via response content.
        r1 = self.client.post(reverse('resend_verification'), {'email': 'resend@nyasablog.com'})
        self.unverified.delete()
        cache.clear()
        r2 = self.client.post(reverse('resend_verification'), {'email': 'resend@nyasablog.com'})
        self.assertEqual(r1.status_code, r2.status_code)
        self.assertEqual(r1.content, r2.content)

    def test_resend_post_renders_verification_sent_template(self):
        response = self.client.post(reverse('resend_verification'), {'email': 'resend@nyasablog.com'})
        self.assertTemplateUsed(response, 'account/verification_sent.html')

    def test_resend_rate_limited_within_cooldown(self):
        from django.core import mail
        before = len(mail.outbox)
        self.client.post(reverse('resend_verification'), {'email': 'resend@nyasablog.com'})
        self.assertEqual(len(mail.outbox), before + 1)
        # Second attempt within cooldown — still returns 200 but no new email.
        self.client.post(reverse('resend_verification'), {'email': 'resend@nyasablog.com'})
        self.assertEqual(len(mail.outbox), before + 1)
        cache.clear()  # simulates time advancing past cooldown
        self.client.post(reverse('resend_verification'), {'email': 'resend@nyasablog.com'})
        self.assertEqual(len(mail.outbox), before + 2)

    def test_resend_case_insensitive_email_lookup(self):
        from django.core import mail
        before = len(mail.outbox)
        self.client.post(reverse('resend_verification'), {'email': 'RESEND@NYASABLOG.COM'})
        self.assertEqual(len(mail.outbox), before + 1)


class PurgeUnverifiedAccountsTests(TestCase):
    def setUp(self):
        from account.models import Account
        now = timezone.now()
        old = now - timedelta(days=8)
        recent = now - timedelta(days=1)

        self.old_unverified = Account.objects.create_user(
            email='old_unverified@x.com', username='ou', password='testpass123'  # pragma: allowlist secret
        )
        Account.objects.filter(pk=self.old_unverified.pk).update(date_joined=old)

        self.old_verified = Account.objects.create_user(
            email='old_verified@x.com', username='ov', password='testpass123'  # pragma: allowlist secret
        )
        Account.objects.filter(pk=self.old_verified.pk).update(date_joined=old, email_verified=True)

        self.recent_unverified = Account.objects.create_user(
            email='recent_unverified@x.com', username='ru', password='testpass123'  # pragma: allowlist secret
        )
        Account.objects.filter(pk=self.recent_unverified.pk).update(date_joined=recent)

        self.recent_verified = Account.objects.create_user(
            email='recent_verified@x.com', username='rv', password='testpass123'  # pragma: allowlist secret
        )
        Account.objects.filter(pk=self.recent_verified.pk).update(date_joined=recent, email_verified=True)

    def test_purge_deletes_only_old_unverified(self):
        from account.models import Account
        call_command('purge_unverified_accounts', stdout=StringIO())
        self.assertFalse(Account.objects.filter(pk=self.old_unverified.pk).exists())
        self.assertTrue(Account.objects.filter(pk=self.old_verified.pk).exists())
        self.assertTrue(Account.objects.filter(pk=self.recent_unverified.pk).exists())
        self.assertTrue(Account.objects.filter(pk=self.recent_verified.pk).exists())

    def test_purge_dry_run_does_not_delete(self):
        from account.models import Account
        out = StringIO()
        call_command('purge_unverified_accounts', '--dry-run', stdout=out)
        self.assertTrue(Account.objects.filter(pk=self.old_unverified.pk).exists())
        self.assertIn('Would delete', out.getvalue())

    def test_purged_email_can_be_reregistered(self):
        from account.models import Account
        call_command('purge_unverified_accounts', stdout=StringIO())
        # Now register a brand-new account with the freed email.
        self.client.post(reverse('register'), {
            'email': 'old_unverified@x.com',
            'username': 'newowner',
            'password1': 'testpass123!',  # pragma: allowlist secret
            'password2': 'testpass123!',  # pragma: allowlist secret
        })
        self.assertTrue(Account.objects.filter(email='old_unverified@x.com').exists())


class RegistrationAPIVersionTests(APITestCase):

    def test_api_register_v1_returns_token_and_unverified(self):
        from django.core import mail

        from account.models import Account
        before = len(mail.outbox)
        url = reverse('account_api:register')
        response = self.client.post(url, {
            'email': 'apinew@nyasablog.com', 'username': 'apinewuser',
            'password': 'testpass123', 'password2': 'testpass123',  # pragma: allowlist secret
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn('token', response.data)
        u = Account.objects.get(email='apinew@nyasablog.com')
        self.assertFalse(u.email_verified)
        self.assertTrue(u.is_active)  # v1 keeps is_active=True for back-compat
        self.assertEqual(len(mail.outbox), before + 1)

    def test_api_register_v2_no_token_unverified_inactive(self):
        from django.core import mail

        from account.models import Account
        before = len(mail.outbox)
        url = reverse('account_api:register')
        response = self.client.post(
            url,
            {'email': 'v2@nyasablog.com', 'username': 'v2user',
             'password': 'testpass123', 'password2': 'testpass123'},  # pragma: allowlist secret
            HTTP_ACCEPT='application/json; version=2',
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('token', response.data)
        self.assertNotIn('username', response.data)
        self.assertNotIn('pk', response.data)
        self.assertEqual(response.data['response'], 'verification_email_sent')
        u = Account.objects.get(email='v2@nyasablog.com')
        self.assertFalse(u.email_verified)
        self.assertFalse(u.is_active)
        self.assertEqual(len(mail.outbox), before + 1)


class LoginAPIVersionTests(APITestCase):
    def setUp(self):
        # Active-unverified - matches v1 API register output
        self.unverified = Account.objects.create_user(
            email='un@x.com', username='un', password='testpass123'  # pragma: allowlist secret
        )
        # Inactive-unverified - matches v2 API register output and web register output
        self.inactive_unverified = Account.objects.create_user(
            email='inv@x.com', username='inv', password='testpass123'  # pragma: allowlist secret
        )
        self.inactive_unverified.is_active = False
        self.inactive_unverified.save()
        # Verified happy-path user
        self.verified = Account.objects.create_user(
            email='ver@x.com', username='ver', password='testpass123'  # pragma: allowlist secret
        )
        self.verified.email_verified = True
        self.verified.save()

    def test_api_login_v1_allows_unverified_with_email_verified_field(self):
        client = APIClient()
        url = reverse('account_api:login')
        response = client.post(url, {'username': 'un@x.com', 'password': 'testpass123'})  # pragma: allowlist secret
        self.assertEqual(response.data['response'], 'Successfully authenticated.')
        self.assertIn('token', response.data)
        self.assertIn('email_verified', response.data)
        self.assertFalse(response.data['email_verified'])

    def test_api_login_v2_rejects_unverified_with_error_code(self):
        client = APIClient()
        url = reverse('account_api:login')
        response = client.post(
            url, {'username': 'un@x.com', 'password': 'testpass123'},  # pragma: allowlist secret
            HTTP_ACCEPT='application/json; version=2',
        )
        self.assertEqual(response.data['response'], 'Error')
        self.assertEqual(response.data.get('error_code'), 'email_not_verified')
        self.assertNotIn('token', response.data)

    def test_api_login_v2_succeeds_for_verified_user(self):
        client = APIClient()
        url = reverse('account_api:login')
        response = client.post(
            url, {'username': 'ver@x.com', 'password': 'testpass123'},  # pragma: allowlist secret
            HTTP_ACCEPT='application/json; version=2',
        )
        self.assertEqual(response.data['response'], 'Successfully authenticated.')
        self.assertIn('token', response.data)
        self.assertTrue(response.data['email_verified'])

    def test_api_login_v2_rejects_inactive_unverified_with_error_code(self):
        # Mirrors v2 API register output (is_active=False, email_verified=False).
        # The view must give the explicit `email_not_verified` code rather than masking as "Invalid credentials".
        client = APIClient()
        url = reverse('account_api:login')
        response = client.post(
            url, {'username': 'inv@x.com', 'password': 'testpass123'},  # pragma: allowlist secret
            HTTP_ACCEPT='application/json; version=2',
        )
        self.assertEqual(response.data['response'], 'Error')
        self.assertEqual(response.data.get('error_code'), 'email_not_verified')
        self.assertNotIn('token', response.data)


class DRFVersioningTests(TestCase):
    def test_default_version_is_v1(self):
        from rest_framework.authtoken.models import Token

        from account.models import Account
        u = Account.objects.create_user(email='ver@x.com', username='ver', password='testpass123')  # pragma: allowlist secret
        u.email_verified = True
        u.save()
        token = Token.objects.get(user=u)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION='Token ' + token.key)
        # Hit the existing properties endpoint with no Accept header.
        # `request.version='1'` resolution is locked in by Tasks 12+ tests that
        # branch on request.version directly; here we only verify the request
        # doesn't error out under default versioning.
        response = client.get(reverse('account_api:properties'))
        self.assertEqual(response.status_code, 200)

    def test_v2_accept_header_resolves_cleanly(self):
        from rest_framework.authtoken.models import Token

        from account.models import Account
        u = Account.objects.create_user(email='v2@x.com', username='v2', password='testpass123')  # pragma: allowlist secret
        u.email_verified = True
        u.save()
        token = Token.objects.get(user=u)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION='Token ' + token.key)
        response = client.get(
            reverse('account_api:properties'),
            HTTP_ACCEPT='application/json; version=2'
        )
        self.assertEqual(response.status_code, 200)

    def test_unknown_version_rejected(self):
        from rest_framework.authtoken.models import Token

        from account.models import Account
        u = Account.objects.create_user(email='vu@x.com', username='vu', password='testpass123')  # pragma: allowlist secret
        u.email_verified = True
        u.save()
        token = Token.objects.get(user=u)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION='Token ' + token.key)
        response = client.get(
            reverse('account_api:properties'),
            HTTP_ACCEPT='application/json; version=99'
        )
        self.assertEqual(response.status_code, 406)  # Not Acceptable


class ResendVerificationAPITests(APITestCase):
    def setUp(self):
        cache.clear()
        self.unverified = Account.objects.create_user(
            email='r@x.com', username='r', password='testpass123'  # pragma: allowlist secret
        )

    def test_api_resend_sends_for_unverified(self):
        before = len(mail.outbox)
        client = APIClient()
        response = client.post(reverse('account_api:resend_verification'),
                               {'email': 'r@x.com'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), before + 1)

    def test_api_resend_silent_for_unknown(self):
        before = len(mail.outbox)
        client = APIClient()
        client.post(reverse('account_api:resend_verification'), {'email': 'nobody@x.com'})
        self.assertEqual(len(mail.outbox), before)

    def test_api_resend_silent_for_already_verified(self):
        self.unverified.email_verified = True
        self.unverified.save()
        before = len(mail.outbox)
        client = APIClient()
        client.post(reverse('account_api:resend_verification'), {'email': 'r@x.com'})
        self.assertEqual(len(mail.outbox), before)

    def test_api_resend_rate_limited(self):
        before = len(mail.outbox)
        client = APIClient()
        client.post(reverse('account_api:resend_verification'), {'email': 'r@x.com'})
        client.post(reverse('account_api:resend_verification'), {'email': 'r@x.com'})
        self.assertEqual(len(mail.outbox), before + 1)


class ConfirmEmailAPITests(APITestCase):
    def setUp(self):
        from account.tokens import email_verification_token
        self.user = Account.objects.create_user(
            email='c@x.com', username='c', password='testpass123'  # pragma: allowlist secret
        )
        self.user.is_active = False
        self.user.save()
        self.uidb64 = urlsafe_base64_encode(force_bytes(self.user.pk))
        self.token = email_verification_token.make_token(self.user)

    def test_api_confirm_valid_token_returns_token(self):
        client = APIClient()
        response = client.post(reverse('account_api:confirm_email'),
                               {'uid': self.uidb64, 'token': self.token})
        self.assertEqual(response.status_code, 200)
        self.assertIn('token', response.data)
        self.user.refresh_from_db()
        self.assertTrue(self.user.email_verified)
        self.assertTrue(self.user.is_active)

    def test_api_confirm_invalid_token_returns_400(self):
        client = APIClient()
        response = client.post(reverse('account_api:confirm_email'),
                               {'uid': self.uidb64, 'token': 'bogus'})
        self.assertEqual(response.status_code, 400)
        self.user.refresh_from_db()
        self.assertFalse(self.user.email_verified)

    def test_api_confirm_already_verified_is_idempotent(self):
        # Mobile clients on flaky networks retry. A retry on an already-verified account
        # must return the auth token rather than 400, so the client can recover gracefully.
        client = APIClient()
        first = client.post(reverse('account_api:confirm_email'),
                            {'uid': self.uidb64, 'token': self.token})
        self.assertEqual(first.status_code, 200)
        # Same payload, second call. Old token is now invalid (email_verified flipped),
        # but the early-return path bypasses the token check.
        second = client.post(reverse('account_api:confirm_email'),
                             {'uid': self.uidb64, 'token': self.token})
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.data['token'], first.data['token'])


class IsEmailVerifiedPermissionTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.unverified = Account.objects.create_user(
            email='unv@x.com', username='unv', password='testpass123'  # pragma: allowlist secret
        )
        self.verified = Account.objects.create_user(
            email='ver@x.com', username='ver', password='testpass123'  # pragma: allowlist secret
        )
        self.verified.email_verified = True
        self.verified.save()

    def test_permission_allows_verified_user(self):
        from account.api.permissions import IsEmailVerified
        permission = IsEmailVerified()
        request = self.factory.get('/')
        request.user = self.verified
        self.assertTrue(permission.has_permission(request, APIView()))

    def test_permission_denies_unverified_user(self):
        from account.api.permissions import IsEmailVerified
        permission = IsEmailVerified()
        request = self.factory.get('/')
        request.user = self.unverified
        self.assertFalse(permission.has_permission(request, APIView()))

    def test_permission_denies_anonymous(self):
        from django.contrib.auth.models import AnonymousUser

        from account.api.permissions import IsEmailVerified
        permission = IsEmailVerified()
        request = self.factory.get('/')
        request.user = AnonymousUser()
        self.assertFalse(permission.has_permission(request, APIView()))


class BlogWriteEndpointGatingTests(APITestCase):
    def setUp(self):
        from blog.models import BlogPost, Category
        self.unverified = Account.objects.create_user(
            email='un@x.com', username='un', password='testpass123'  # pragma: allowlist secret
        )
        self.verified = Account.objects.create_user(
            email='ver@x.com', username='ver', password='testpass123'  # pragma: allowlist secret
        )
        self.verified.email_verified = True
        self.verified.save()
        self.un_token = Token.objects.get(user=self.unverified)
        self.ver_token = Token.objects.get(user=self.verified)
        self.category = Category.objects.create(name='News', slug='news')
        self.post = BlogPost.objects.create(
            title='Existing', body='Body', author=self.verified, status='published',
            category=self.category, slug='existing',
        )

    def _client_for(self, token):
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION='Token ' + token.key)
        return c

    def test_unverified_blocked_from_create_post(self):
        client = self._client_for(self.un_token)
        response = client.post(reverse('blog_api:create'), {
            'title': 'Spam', 'body': 'Spam body', 'category': self.category.pk,
        })
        self.assertEqual(response.status_code, 403)

    def test_unverified_blocked_from_create_comment(self):
        client = self._client_for(self.un_token)
        response = client.post(
            reverse('blog_api:create_comment', args=[self.post.slug]),
            {'body': 'Spam comment'},
        )
        self.assertEqual(response.status_code, 403)

    def test_unverified_blocked_from_toggle_like(self):
        client = self._client_for(self.un_token)
        response = client.post(reverse('blog_api:like', args=[self.post.slug]))
        self.assertEqual(response.status_code, 403)

    def test_verified_user_can_create_post(self):
        client = self._client_for(self.ver_token)
        response = client.post(reverse('blog_api:create'), {
            'title': 'OK Post', 'body': 'Body', 'category': self.category.pk,
        })
        # 200 or 201 — anything but 403.
        self.assertNotEqual(response.status_code, 403)

    def test_unverified_can_still_read_blog_detail(self):
        client = self._client_for(self.un_token)
        response = client.get(reverse('blog_api:detail', args=[self.post.slug]))
        self.assertEqual(response.status_code, 200)

    def test_unverified_can_still_read_comments(self):
        client = self._client_for(self.un_token)
        response = client.get(reverse('blog_api:comments', args=[self.post.slug]))
        self.assertEqual(response.status_code, 200)


class AccountWriteEndpointGatingTests(APITestCase):
    def setUp(self):
        self.unverified = Account.objects.create_user(
            email='un@x.com', username='un', password='testpass123'  # pragma: allowlist secret
        )
        self.un_token = Token.objects.get(user=self.unverified)

    def _client(self):
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION='Token ' + self.un_token.key)
        return c

    def test_unverified_blocked_from_change_password(self):
        response = self._client().put(reverse('account_api:change_password'), {
            'old_password': 'testpass123',  # pragma: allowlist secret
            'new_password': 'newtestpass123',  # pragma: allowlist secret
            'confirm_new_password': 'newtestpass123',  # pragma: allowlist secret
        })
        self.assertEqual(response.status_code, 403)

    def test_unverified_blocked_from_update_profile(self):
        response = self._client().put(reverse('account_api:update_profile'),
                                       {'bio': 'Spammy bio'})
        self.assertEqual(response.status_code, 403)

    def test_unverified_blocked_from_update_account(self):
        response = self._client().put(reverse('account_api:update'), {
            'email': 'un@x.com', 'username': 'newun',
        })
        self.assertEqual(response.status_code, 403)


class HTMLViewEmailVerifiedGatingTests(TestCase):
    """Confirms web write views redirect unverified users to verification_sent."""

    def setUp(self):
        self.unverified = Account.objects.create_user(
            email='unv@x.com', username='unvuser', password='testpass123'  # pragma: allowlist secret
        )  # is_active=True, email_verified=False — mirrors API v1 register output
        self.verified = Account.objects.create_user(
            email='ver@x.com', username='veruser', password='testpass123'  # pragma: allowlist secret
        )
        self.verified.email_verified = True
        self.verified.save()

    def _login(self, user):
        self.client.force_login(user, backend='account.backends.CaseInsensitiveModelBackend')

    def test_unverified_redirected_from_create_blog(self):
        self._login(self.unverified)
        response = self.client.get(reverse('blog:create'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('verification', response['Location'])

    def test_unverified_redirected_from_account_view(self):
        self._login(self.unverified)
        response = self.client.get(reverse('account'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('verification', response['Location'])

    def test_verified_can_access_create_blog(self):
        self._login(self.verified)
        response = self.client.get(reverse('blog:create'))
        self.assertEqual(response.status_code, 200)

    def test_verified_can_access_account_view(self):
        self._login(self.verified)
        response = self.client.get(reverse('account'))
        self.assertEqual(response.status_code, 200)


@override_settings(
    EMAIL_BACKEND='anymail.backends.postmark.EmailBackend',
    ANYMAIL={'POSTMARK_SERVER_TOKEN': 'test-token'},
)
class PostmarkBackendTests(TestCase):
    def test_anymail_postmark_backend_is_resolvable(self):
        conn = get_connection()
        self.assertEqual(
            conn.__class__.__module__,
            'anymail.backends.postmark',
        )


@override_settings(
    EMAIL_BACKEND='anymail.backends.test.EmailBackend',
    ANYMAIL={'POSTMARK_SERVER_TOKEN': 'test-token'},
    SUPPORT_EMAIL='hello@nyasablog.com',
)
class VerificationEmailTaggingTests(TestCase):
    def setUp(self):
        self.user = Account.objects.create_user(
            email='tag-test@example.com', username='tagtester', password='x',  # pragma: allowlist secret
        )

    def test_verification_email_is_tagged_for_postmark(self):
        from account.emails import send_verification_email
        send_verification_email(self.user)
        sent = mail.outbox[0]
        self.assertEqual(sent.anymail_test_params['tags'], ['email-verification'])

    def test_verification_email_includes_user_id_metadata(self):
        from account.emails import send_verification_email
        send_verification_email(self.user)
        sent = mail.outbox[0]
        self.assertEqual(
            sent.anymail_test_params['metadata'],
            {'user_id': str(self.user.pk)},
        )

    def test_verification_email_has_reply_to_set(self):
        from account.emails import send_verification_email
        send_verification_email(self.user)
        sent = mail.outbox[0]
        self.assertEqual(sent.reply_to, [settings.SUPPORT_EMAIL])

    @override_settings(DEFAULT_FROM_EMAIL='NyasaBlog <hello@nyasablog.com>')
    def test_verification_email_from_address_is_a_nyasablog_address(self):
        from account.emails import send_verification_email
        send_verification_email(self.user)
        sent = mail.outbox[0]
        self.assertIn('@nyasablog.com', sent.from_email)


class PasswordToggleTests(TestCase):
    def setUp(self):
        self.user = Account.objects.create_user(
            email='toggle@nyasablog.com', username='toggleuser', password='Str0ngPass!9'
        )
        self.user.email_verified = True
        self.user.save()

    def test_login_page_has_exactly_one_password_toggle(self):
        resp = self.client.get(reverse('login'))
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertEqual(body.count('data-pw-toggle'), 1)
        self.assertIn('type="button"', body)
        self.assertIn('aria-label="Show password"', body)
