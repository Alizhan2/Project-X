from datetime import timedelta
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from .email_flows import TOKENS, deliver
from .models import User
from apps.core.jobs import run_pending
from apps.core.models import Job
from .tests import csrf_client, fresh


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend', PUBLIC_APP_URL='https://doedu.example', IS_DEPLOYED=False)
class EmailFlowTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user('mail@example.com', 'mail@example.com', 'old-passphrase-456')
        self.c, self.headers = csrf_client()

    def post(self, path, data=None):
        return self.c.post('/api/auth/' + path, data or {}, content_type='application/json', **fresh(self.c))

    def token_data(self, purpose):
        deliver(self.user, purpose)
        url = next(line for line in mail.outbox[-1].body.splitlines() if line.startswith('https://'))
        self.assertEqual(urlsplit(url).netloc, 'doedu.example')
        return {key: values[0] for key, values in parse_qs(urlsplit(url).fragment).items()}

    def test_reset_changes_password_invalidates_token_and_old_session(self):
        self.c.force_login(self.user)
        data = self.token_data('reset') | {'password': 'new-passphrase-987'}  # pragma: allowlist secret - synthetic test password
        self.assertEqual(self.post('password-reset/confirm/', data).status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(data['password']))
        self.assertIsNotNone(self.user.email_verified_at)
        self.assertIsNone(self.c.get('/api/auth/me/').json()['user'])
        self.assertEqual(self.post('password-reset/confirm/', data).status_code, 400)

    def test_verify_one_use_and_does_not_sign_in(self):
        data = self.token_data('verify')
        self.assertEqual(self.post('email-verification/confirm/', data).status_code, 200)
        self.assertEqual(self.post('email-verification/confirm/', data).status_code, 400)
        self.assertIsNone(self.c.get('/api/auth/me/').json()['user'])

    def test_tokens_are_purpose_bound(self):
        data = self.token_data('verify') | {'password': 'new-passphrase-987'}  # pragma: allowlist secret - synthetic test password
        self.assertEqual(self.post('password-reset/confirm/', data).status_code, 400)
        data = self.token_data('reset')
        self.assertEqual(self.post('email-verification/confirm/', data).status_code, 400)

    def test_weak_password_does_not_consume_token(self):
        data = self.token_data('reset')
        self.assertEqual(self.post('password-reset/confirm/', data | {'password': '123'}).status_code, 400)
        self.assertEqual(self.post('password-reset/confirm/', data | {'password': 'new-passphrase-987'}).status_code, 200)  # pragma: allowlist secret - synthetic test password

    def test_expiry_for_both_purposes(self):
        for purpose, path in [('reset', 'password-reset/confirm/'), ('verify', 'email-verification/confirm/')]:
            with patch.object(TOKENS[purpose], '_now', return_value=timezone.now().replace(tzinfo=None) - timedelta(hours=2)):
                data = self.token_data(purpose)
            self.assertEqual(self.post(path, data | {'password': 'new-passphrase-987'}).status_code, 400)  # pragma: allowlist secret - synthetic test password

    def test_changed_email_invalidates_verification(self):
        data = self.token_data('verify')
        self.user.email = 'changed@example.com'
        self.user.save()
        self.assertEqual(self.post('email-verification/confirm/', data).status_code, 400)

    def test_request_response_identical_and_cooldown(self):
        known = self.post('password-reset/', {'email': 'MAIL@example.com'})
        unknown = self.post('password-reset/', {'email': 'missing@example.com'})
        self.assertEqual(known.status_code, 202)
        self.assertEqual(known.content, unknown.content)
        self.post('password-reset/', {'email': self.user.email})
        run_pending()
        self.assertEqual(len(mail.outbox), 1)

    def test_verification_requires_authenticated_user(self):
        self.assertEqual(self.post('email-verification/').status_code, 403)
        self.c.force_login(self.user)
        self.assertEqual(self.post('email-verification/').status_code, 202)
        run_pending()
        self.assertEqual(len(mail.outbox), 1)

    def test_all_new_endpoints_require_csrf(self):
        from django.test import Client
        for path in ['password-reset/', 'password-reset/confirm/', 'email-verification/', 'email-verification/confirm/']:
            self.assertEqual(Client(enforce_csrf_checks=True).post('/api/auth/' + path).status_code, 403)

    def test_invalid_uid_and_inactive_user(self):
        data = self.token_data('reset') | {'password': 'new-passphrase-987'}  # pragma: allowlist secret - synthetic test password
        self.assertEqual(self.post('password-reset/confirm/', data | {'uid': '!'}).status_code, 400)
        self.user.is_active = False
        self.user.save()
        self.assertEqual(self.post('password-reset/confirm/', data).status_code, 400)

    def test_mail_failure_does_not_disclose_account(self):
        with patch('apps.accounts.email_flows.send_mail', side_effect=OSError('secret smtp error')):
            known = self.post('password-reset/', {'email': self.user.email})
            run_pending()
            job = Job.objects.get(kind='account_email')
            self.assertEqual(job.status, 'pending')
            self.assertNotIn('secret smtp error', job.last_error)
        unknown = self.post('password-reset/', {'email': 'missing@example.com'})
        self.assertEqual(known.content, unknown.content)

    @override_settings(IS_DEPLOYED=True, ACCOUNT_EMAIL_CONFIGURED=False)
    def test_unconfigured_deployment_returns_unavailable_for_everyone(self):
        for email in [self.user.email, 'missing@example.com']:
            self.assertEqual(self.post('password-reset/', {'email': email}).status_code, 503)

    def test_pending_mail_cancelled_after_password_change(self):
        self.post('password-reset/', {'email': self.user.email})
        self.user.set_password('changed-in-meantime-123')
        self.user.save()
        run_pending()
        self.assertEqual(len(mail.outbox), 0)

    def test_local_mail_preview_is_private(self):
        import stat
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as folder:
            with override_settings(EMAIL_BACKEND='apps.accounts.mail_backend.EmailBackend', EMAIL_FILE_PATH=folder):
                deliver(self.user, 'verify')
            files = list(Path(folder).iterdir())
            self.assertEqual(len(files), 1)
            self.assertEqual(stat.S_IMODE(files[0].stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(Path(folder).stat().st_mode), 0o700)
            self.assertIn('https://doedu.example/verify-email#', files[0].read_text())
