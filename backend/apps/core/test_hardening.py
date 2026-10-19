"""Production hardening: startup validation, abuse resistance, log hygiene."""

import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from unittest import mock

from django.core.cache import cache
from django.test import SimpleTestCase, TestCase
from rest_framework.throttling import ScopedRateThrottle

from apps.core.throttling import IpScopedRateThrottle

from apps.accounts.models import User
from apps.core.logging import JsonFormatter, redact

BACKEND = Path(__file__).resolve().parents[2]
GOOD_PROD = {
    "DOEDU_ENV": "production", "DOEDU_LAUNCH_MODE": "demo", "DJANGO_DEBUG": "false", "DJANGO_SECRET_KEY": "k" * 64,
    "DJANGO_ALLOWED_HOSTS": "demo.example.org", "DJANGO_CSRF_TRUSTED_ORIGINS": "https://demo.example.org",
    "DJANGO_SECURE_SSL": "true", "POSTGRES_PASSWORD": "a-real-secret-value", "DOEDU_TRUSTED_PROXIES": "1",
}


def run_settings(overrides, code="import django; django.setup(); from django.conf import settings; print('OK', settings.ENVIRONMENT)"):
    env = {k: v for k, v in os.environ.items() if not k.startswith(("DOEDU_", "DJANGO_", "POSTGRES_"))}
    env.update({"DJANGO_SETTINGS_MODULE": "config.settings", "PATH": os.environ["PATH"], **overrides})
    return subprocess.run([sys.executable, "-c", code], cwd=BACKEND, env=env, capture_output=True, text=True)


class StartupValidationTests(SimpleTestCase):
    def test_a_correct_production_configuration_starts(self):
        r = run_settings(GOOD_PROD)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("OK production", r.stdout)

    def test_each_unsafe_production_setting_is_refused_with_a_clear_message(self):
        cases = {
            "DJANGO_DEBUG": ("true", "DEBUG must be off"),
            "DJANGO_SECRET_KEY": ("short", "SECRET_KEY must be at least 50"),
            "DJANGO_ALLOWED_HOSTS": ("*", "ALLOWED_HOSTS must list explicit"),
            "DJANGO_SECURE_SSL": ("false", "SECURE_SSL=true is required"),
            "DJANGO_CSRF_TRUSTED_ORIGINS": ("http://demo.example.org", "must be https://"),
            "POSTGRES_PASSWORD": ("change-me-dev-only", "POSTGRES_PASSWORD must be set"),
            "DOEDU_ALLOW_DEMO_TOOLS": ("true", "Demo tools must not be enabled in production"),
        }
        for key, (bad, message) in cases.items():
            r = run_settings({**GOOD_PROD, key: bad})
            self.assertNotEqual(r.returncode, 0, key)
            self.assertIn(message, r.stderr, key)

    def test_missing_secrets_are_refused(self):
        r = run_settings({k: v for k, v in GOOD_PROD.items() if k not in ("DJANGO_SECRET_KEY", "POSTGRES_PASSWORD", "DJANGO_ALLOWED_HOSTS")})
        self.assertNotEqual(r.returncode, 0)
        for text in ("DJANGO_SECRET_KEY is required", "POSTGRES_PASSWORD must be set", "ALLOWED_HOSTS must list"):
            self.assertIn(text, r.stderr)

    def test_commercial_launch_mode_refuses_to_start_because_no_real_integrations_exist(self):
        r = run_settings({**GOOD_PROD, "DOEDU_LAUNCH_MODE": "commercial"})
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("authorised transport and payment integrations", r.stderr)

    def test_unknown_environment_is_refused(self):
        self.assertNotEqual(run_settings({**GOOD_PROD, "DOEDU_ENV": "prod"}).returncode, 0)

    def test_deployed_cookies_are_secure_and_demo_tools_are_off(self):
        r = run_settings(GOOD_PROD, "import django; django.setup(); from django.conf import settings as s; "
                                    "print(s.SESSION_COOKIE_SECURE, s.CSRF_COOKIE_SECURE, s.ALLOW_DEMO_TOOLS, s.ENABLE_API_DOCS, s.SECURE_SSL_REDIRECT)")
        self.assertEqual(r.stdout.split(), ["True", "True", "False", "False", "True"], r.stderr)

    def test_seed_command_is_unavailable_in_production(self):
        r = run_settings(GOOD_PROD, "import django; django.setup(); from django.core.management import call_command; call_command('seed_demo')")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("Refusing to reset data", r.stderr)

    def test_django_deploy_checks_are_clean_apart_from_hsts_preload(self):
        r = run_settings(GOOD_PROD, "import django; django.setup(); from django.core.management import call_command; call_command('check', deploy=True)")
        self.assertNotIn("W004", r.stderr + r.stdout)
        self.assertNotIn("W008", r.stderr + r.stdout)
        self.assertNotIn("W012", r.stderr + r.stdout)
        self.assertNotIn("W016", r.stderr + r.stdout)


class AbuseResistanceTests(TestCase):
    def setUp(self):
        cache.clear()

    def post_login(self, email, password):
        return self.client.post("/api/auth/login/", {"email": email, "password": password}, content_type="application/json")

    def test_account_lockout_after_repeated_failures_even_with_the_right_password(self):
        User.objects.create_user("v@x.co", "v@x.co", "correct-horse-42")
        for _ in range(5):
            self.assertEqual(self.post_login("v@x.co", "wrong-password").status_code, 400)
        self.assertEqual(self.post_login("v@x.co", "correct-horse-42").status_code, 429)
        self.assertEqual(self.post_login("someone-else@x.co", "whatever").status_code, 400)   # other accounts unaffected

    def test_successful_login_resets_the_failure_counter(self):
        User.objects.create_user("v@x.co", "v@x.co", "correct-horse-42")
        for _ in range(4):
            self.post_login("v@x.co", "wrong-password")
        self.assertEqual(self.post_login("v@x.co", "correct-horse-42").status_code, 200)
        for _ in range(4):
            self.assertEqual(self.post_login("v@x.co", "wrong-password").status_code, 400)

    def test_rate_limits_apply_per_scope(self):
        rates = {"login": "3/min", "register": "2/min", "search": "4/min", "booking": "2/min"}
        with mock.patch.object(ScopedRateThrottle, "THROTTLE_RATES", rates):
            codes = [self.client.get("/api/search/", {"origin": "x"}).status_code for _ in range(6)]
            self.assertEqual(codes[:4], [400] * 4)             # validated (invalid) but counted
            self.assertEqual(codes[4:], [429, 429])
            self.assertIn("Retry-After", self.client.get("/api/search/", {"origin": "x"}))
            cache.clear()
            reg = [self.client.post("/api/auth/register/", {"email": f"n{i}@x.co", "full_name": "N", "password": "correct-horse-42"}, content_type="application/json").status_code for i in range(3)]
            self.assertEqual(reg, [201, 201, 429])

    def test_booking_endpoints_are_rate_limited_per_user(self):
        u = User.objects.create_user("b@x.co", "b@x.co", "correct-horse-42")
        self.client.force_login(u)
        with mock.patch.object(ScopedRateThrottle, "THROTTLE_RATES", {"booking": "3/min", "search": "1000/min", "login": "1000/min", "register": "1000/min"}):
            codes = [self.client.get("/api/bookings/").status_code for _ in range(5)]
        self.assertEqual(codes, [200, 200, 200, 429, 429])


class LogHygieneTests(SimpleTestCase):
    def test_redaction(self):
        text = "failed for anna@example.com password=hunter2 Authorization: Bearer abc.def sessionid=xyz"
        out = redact(text)
        self.assertNotIn("anna@example.com", out)
        for secret in ("hunter2", "abc.def", "xyz"):
            self.assertNotIn(secret, out)

    def test_json_log_lines_are_structured_redacted_and_drop_unknown_fields(self):
        rec = logging.LogRecord("doedu.access", logging.INFO, __file__, 1, "login by %s", ("bob@example.com",), None)
        rec.request_id, rec.status, rec.password = "rid123456", 200, "must-not-appear"
        line = json.loads(JsonFormatter().format(rec))
        self.assertEqual((line["request_id"], line["status"], line["level"]), ("rid123456", 200, "INFO"))
        self.assertNotIn("bob@example.com", line["message"])
        self.assertNotIn("password", line)
        self.assertNotIn("must-not-appear", json.dumps(line))


class AccessLogTests(TestCase):
    def test_access_log_has_no_query_string_body_or_ip(self):
        with self.assertLogs("doedu.access", level="INFO") as cm:
            self.client.post("/api/auth/login/", {"email": "q@x.co", "password": "topsecret-pw"}, content_type="application/json")
            self.client.get("/api/stops/?secret=1")
        joined = " ".join(cm.output) + " ".join(str(r.__dict__) for r in cm.records)
        self.assertNotIn("topsecret-pw", joined)
        self.assertNotIn("secret=1", joined)
        self.assertNotIn("127.0.0.1", joined)
        paths = [r.path for r in cm.records]
        self.assertEqual(paths, ["/api/auth/login/", "/api/stops/"])


class DatabaseOutageTests(TestCase):
    def test_a_database_failure_is_a_retryable_503_without_internals(self):
        from django.db import OperationalError
        with mock.patch("apps.planning.views.Stop.objects") as stops:
            stops.select_related.side_effect = OperationalError("connection to server at \"10.0.0.5\", port 5432 failed")
            res = self.client.get("/api/stops/")
        self.assertEqual((res.status_code, res.json()["code"]), (503, "service_unavailable"))
        self.assertEqual(res["Retry-After"], "5")
        self.assertNotIn("10.0.0.5", res.content.decode())


from django.test import TransactionTestCase  # noqa: E402


class MultiWorkerTests(TransactionTestCase):
    """Several workers polling the same queue must run each job exactly once (FOR UPDATE SKIP LOCKED)."""

    def test_concurrent_workers_never_double_run_a_job(self):
        import threading
        from datetime import timedelta
        from django.db import connection
        from django.utils import timezone
        from apps.core import jobs
        from apps.core.models import Job

        ran, lock = [], threading.Lock()

        @jobs.handler("test_count")
        def _handler(n):
            with lock:
                ran.append(n)

        past = timezone.now() - timedelta(seconds=1)
        Job.objects.bulk_create([Job(kind="test_count", payload={"n": i}, run_at=past) for i in range(60)])
        barrier = threading.Barrier(5)

        def worker():
            try:
                barrier.wait()
                jobs.run_pending()
            finally:
                connection.close()

        ts = [threading.Thread(target=worker) for _ in range(5)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertEqual(sorted(ran), list(range(60)))                         # every job ran, none twice
        self.assertEqual(Job.objects.filter(status="done").count(), 60)

    def test_a_permanently_failing_job_is_bounded_and_visible(self):
        from datetime import timedelta
        from django.utils import timezone
        from apps.core import jobs
        from apps.core.models import Job

        @jobs.handler("test_always_fails")
        def _boom():
            raise RuntimeError("nope")

        Job.objects.create(kind="test_always_fails", payload={}, run_at=timezone.now() - timedelta(seconds=1))
        for _ in range(jobs.MAX_ATTEMPTS + 2):
            Job.objects.filter(kind="test_always_fails", status="pending").update(run_at=timezone.now() - timedelta(seconds=1))
            jobs.run_pending()
        job = Job.objects.get(kind="test_always_fails")
        self.assertEqual((job.status, job.attempts), ("failed", jobs.MAX_ATTEMPTS))   # stops retrying, stays queryable
        from apps.core import ops
        self.assertEqual(ops.snapshot()["jobs"]["failed"], 1)                          # visible in metrics/ops_status
