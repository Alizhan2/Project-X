from io import StringIO
import os
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from apps.accounts.models import User
from apps.core.models import AuditRecord
from apps.transport.models import OperatorMembership, Stop


@override_settings(IS_DEPLOYED=True, SIMULATION_ENABLED=True)
class KazakhstanSetupTests(TestCase):
    def prepare(self):
        output, errors = StringIO(), StringIO()
        with mock.patch.dict(os.environ, {"DEMO_USER_PASSWORD": "x" * 32}):
            call_command("prepare_kazakhstan_demo", stdout=output, stderr=errors)
        return output.getvalue(), errors.getvalue()

    def test_restarts_preserve_passwords_accounts_and_geography(self):
        private = User.objects.create_user(username="private@example.test")
        private.set_unusable_password()
        private.save()
        original_hash = private.password
        self.prepare()
        operator = User.objects.get(username="ops.kzbus@doedu.test")
        self.assertTrue(operator.check_password("x" * 32))
        self.assertEqual(operator.membership.operator.code, "kz-demo-bus")
        operator.set_unusable_password()
        operator.save()
        changed_hash = operator.password
        self.prepare()
        private.refresh_from_db()
        operator.refresh_from_db()
        self.assertEqual(private.password, original_hash)
        self.assertEqual(operator.password, changed_hash)
        self.assertEqual(Stop.objects.filter(code__startswith="KZ-").count(), 180)
        self.assertEqual(OperatorMembership.objects.count(), 2)
        self.assertEqual(AuditRecord.objects.filter(action="demo.kz_prepared").count(), 1)
        self.assertEqual(User.objects.count(), 3)

    def test_existing_passenger_is_not_promoted_to_operator(self):
        user = User.objects.create_user(username="ops.kzbus@doedu.test")
        original_hash = user.password
        _, errors = self.prepare()
        user.refresh_from_db()
        self.assertEqual((user.role, user.password), (User.Role.PASSENGER, original_hash))
        self.assertFalse(OperatorMembership.objects.filter(user=user).exists())
        self.assertIn("conflicting existing account", errors)

    def test_disabled_simulation_and_weak_hosted_password_do_not_write(self):
        with override_settings(SIMULATION_ENABLED=False), self.assertRaises(CommandError):
            self.prepare()
        with mock.patch.dict(os.environ, {"DEMO_USER_PASSWORD": "short"}), self.assertRaises(CommandError):  # pragma: allowlist secret - rejected test fixture
            call_command("prepare_kazakhstan_demo")
        self.assertEqual((User.objects.count(), Stop.objects.count()), (0, 0))

    def test_restart_does_not_restore_revoked_operator_membership(self):
        self.prepare()
        user = User.objects.get(username="ops.kzbus@doedu.test")
        OperatorMembership.objects.filter(user=user).delete()
        _, errors = self.prepare()
        self.assertFalse(OperatorMembership.objects.filter(user=user).exists())
        self.assertIn("membership was left unchanged", errors)
