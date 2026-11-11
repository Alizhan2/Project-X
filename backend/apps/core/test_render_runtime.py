import hashlib
from io import StringIO
import os
import signal
import subprocess
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase, override_settings

from apps.accounts.models import User
from apps.bookings.models import Booking
from apps.core.models import AuditRecord
from apps.core.management.commands.bootstrap_hosted_demo import MARKER_ACTION, MARKER_ID
from apps.transport.models import Stop
import render_start


class RenderEnvironmentTests(SimpleTestCase):
    def base(self):
        return {"RENDER_EXTERNAL_HOSTNAME": "doedu-test.onrender.com", "DOEDU_SECRET_SEED": "x" * 44,
                "POSTGRES_HOST": "db.example.org", "POSTGRES_PORT": "5433", "POSTGRES_USER": "demo",
                "POSTGRES_PASSWORD": "p@ss:word", "POSTGRES_DB": "doedu_demo"}  # pragma: allowlist secret - synthetic test fixture

    def test_generated_seed_expands_without_weakening_explicit_secret_validation(self):
        environment = render_start.render_environment(self.base())
        self.assertEqual(environment["DJANGO_SECRET_KEY"], hashlib.sha512(b"Doedu Render demo Django secret v1\0" + ("x" * 44).encode()).hexdigest())
        self.assertEqual(environment["POSTGRES_PASSWORD"], "p@ss:word")
        self.assertEqual((environment["POSTGRES_DB"], environment["POSTGRES_PORT"]), ("doedu_demo", "5433"))
        self.assertEqual((environment["DOEDU_ENV"], environment["DJANGO_SECURE_SSL"], environment["WEB_CONCURRENCY"]),
                         ("production", "true", "1"))
        self.assertEqual(environment["GUNICORN_BIND"], "0.0.0.0:10000")
        self.assertEqual(environment["DJANGO_CSRF_TRUSTED_ORIGINS"], "https://doedu-test.onrender.com")
        explicit = render_start.render_environment({**self.base(), "DJANGO_SECRET_KEY": "short"})
        self.assertEqual(explicit["DJANGO_SECRET_KEY"], "short")  # Django's existing startup gate still rejects this.

    def test_missing_or_unsafe_host_and_missing_secret_refused(self):
        for host in ("", "*", "https://demo.onrender.com", "demo.onrender.com:443", "demo.onrender.com/path"):
            with self.subTest(host=host), self.assertRaisesMessage(ValueError, "exact public DNS"):
                render_start.render_environment({**self.base(), "RENDER_EXTERNAL_HOSTNAME": host})
        with self.assertRaisesMessage(ValueError, "SECRET"):
            render_start.render_environment({**self.base(), "DOEDU_SECRET_SEED": ""})

    def test_explicit_database_fields_and_port_are_preserved(self):
        source = self.base()
        source.update(PORT="8080", POSTGRES_HOST="private-db", POSTGRES_PASSWORD="synthetic")  # pragma: allowlist secret - synthetic test fixture
        environment = render_start.render_environment(source)
        self.assertEqual(environment["POSTGRES_HOST"], "private-db")
        self.assertEqual(environment["GUNICORN_BIND"], "0.0.0.0:8080")
        with self.assertRaisesMessage(ValueError, "valid TCP port"):
            render_start.render_environment({**source, "PORT": "0"})


class SupervisorTests(SimpleTestCase):
    @mock.patch("render_start.signal.signal")
    @mock.patch("render_start.os.killpg")
    @mock.patch("render_start.time.sleep")
    @mock.patch("render_start.subprocess.Popen")
    def test_unexpected_exit_stops_sibling_and_returns_failure(self, popen, sleep, killpg, install_signal):
        web, worker = mock.Mock(pid=101), mock.Mock(pid=102)
        web.poll.return_value = 0
        worker.poll.return_value = None
        popen.side_effect = [web, worker]
        self.assertEqual(render_start.supervise({}), 1)
        self.assertIn(mock.call(102, signal.SIGTERM), killpg.call_args_list)
        self.assertTrue(all(call.kwargs["start_new_session"] for call in popen.call_args_list))

    @mock.patch("render_start.os.killpg")
    @mock.patch("render_start.time.sleep")
    @mock.patch("render_start.subprocess.Popen")
    def test_platform_shutdown_forwards_term_and_escalates_only_timed_out_child(self, popen, sleep, killpg):
        web, worker = mock.Mock(pid=201), mock.Mock(pid=202)
        web.poll.return_value = worker.poll.return_value = None
        web.wait.side_effect = [subprocess.TimeoutExpired("web", 30), 0]
        popen.side_effect = [web, worker]
        installed = {}

        def install(sig, handler):
            installed[sig] = handler
            return None

        sleep.side_effect = lambda _seconds: installed[signal.SIGTERM](signal.SIGTERM, None)
        with mock.patch("render_start.signal.signal", side_effect=install):
            self.assertEqual(render_start.supervise({}), 0)
        for pid in (201, 202):
            self.assertIn(mock.call(pid, signal.SIGTERM), killpg.call_args_list)
        self.assertIn(mock.call(201, signal.SIGKILL), killpg.call_args_list)
        self.assertNotIn(mock.call(202, signal.SIGKILL), killpg.call_args_list)

    @mock.patch("render_start.supervise", return_value=0)
    @mock.patch("render_start.subprocess.run")
    @mock.patch("render_start.render_environment")
    def test_bootstrap_is_explicit_and_migrations_precede_children(self, prepare, run, supervise):
        prepare.return_value = {"DOEDU_BOOTSTRAP_DEMO": "true"}
        self.assertEqual(render_start.main(), 0)
        self.assertEqual([call.args[0][-1] for call in run.call_args_list], ["safe_migrate", "bootstrap_hosted_demo"])
        supervise.assert_called_once_with(prepare.return_value)
        run.reset_mock()
        prepare.return_value = {}
        self.assertEqual(render_start.main(), 0)
        self.assertEqual([call.args[0][-1] for call in run.call_args_list], ["safe_migrate"])

    @mock.patch("render_start.supervise", return_value=0)
    @mock.patch("render_start.subprocess.run")
    @mock.patch("render_start.render_environment")
    def test_kazakhstan_setup_runs_after_existing_bootstrap(self, prepare, run, _supervise):
        prepare.return_value = {"DOEDU_BOOTSTRAP_DEMO": "true", "DOEDU_LAUNCH_MODE": "demo"}
        self.assertEqual(render_start.main(), 0)
        self.assertEqual([call.args[0][-1] for call in run.call_args_list],
                         ["safe_migrate", "bootstrap_hosted_demo", "prepare_kazakhstan_demo"])


@override_settings(IS_DEPLOYED=True, LAUNCH_MODE="demo", SIMULATION_ENABLED=True, ALLOW_DEMO_TOOLS=False)
class HostedBootstrapTests(TestCase):
    def setUp(self):
        self.passwords = mock.patch.dict(os.environ, {
            "DOEDU_BOOTSTRAP_DEMO": "true", "DEMO_USER_PASSWORD": "x" * 32, "DEMO_ADMIN_PASSWORD": "y" * 32,
        })
        self.passwords.start()
        self.addCleanup(self.passwords.stop)

    def bootstrap(self):
        output = StringIO()
        call_command("bootstrap_hosted_demo", stdout=output)
        return output.getvalue()

    def test_fresh_bootstrap_has_separate_admin_password_and_restart_never_resets_data(self):
        text = self.bootstrap()
        self.assertEqual((User.objects.count(), Booking.objects.count()), (8, 4))
        administrator = User.objects.get(username="admin@doedu.test")
        operator = User.objects.get(username="ops.valley@doedu.test")
        self.assertTrue(administrator.check_password("y" * 32))
        self.assertFalse(administrator.check_password("x" * 32))
        self.assertTrue(operator.check_password("x" * 32))
        self.assertNotIn("x" * 32, text)
        operator.set_password("new-private-test-password")
        operator.save()
        reference = Booking.objects.first().reference
        self.assertIn("already initialized", self.bootstrap())
        operator.refresh_from_db()
        self.assertTrue(operator.check_password("new-private-test-password"))
        self.assertEqual(Booking.objects.count(), 4)
        self.assertTrue(Booking.objects.filter(reference=reference).exists())
        self.assertEqual(AuditRecord.objects.filter(action=MARKER_ACTION, object_id=MARKER_ID).count(), 1)

    def test_existing_account_is_not_modified(self):
        user = User.objects.create_user("private@example.test", "Private", "private-test-password")
        password_hash = user.password
        with self.assertRaisesMessage(CommandError, "not empty"):
            self.bootstrap()
        user.refresh_from_db()
        self.assertEqual(user.password, password_hash)
        self.assertEqual(Stop.objects.count(), 0)

    def test_existing_transport_without_accounts_is_also_refused(self):
        Stop.objects.create(code="EXISTING", name="Existing stop", kind="bus")
        with self.assertRaisesMessage(CommandError, "not empty"):
            self.bootstrap()
        self.assertEqual((User.objects.count(), Stop.objects.count()), (0, 1))

    def test_disabled_wrong_launch_and_missing_password_are_refused(self):
        with mock.patch.dict(os.environ, {"DOEDU_BOOTSTRAP_DEMO": "false"}), self.assertRaisesMessage(CommandError, "explicitly enabled"):
            self.bootstrap()
        with override_settings(LAUNCH_MODE="development"), self.assertRaisesMessage(CommandError, "deployed demo"):
            self.bootstrap()
        for admin in ("", "x" * 32):
            with mock.patch.dict(os.environ, {"DEMO_ADMIN_PASSWORD": admin}), self.assertRaisesMessage(CommandError, "distinct generated"):
                self.bootstrap()
        self.assertEqual(User.objects.count(), 0)

    @mock.patch("apps.transport.demo_data._seed_demo_bookings", side_effect=RuntimeError("fixture failed"))
    def test_bootstrap_failure_rolls_back_data_and_marker(self, _seed):
        with self.assertRaisesMessage(RuntimeError, "fixture failed"):
            self.bootstrap()
        self.assertEqual((User.objects.count(), Stop.objects.count(), AuditRecord.objects.count()), (0, 0, 0))
