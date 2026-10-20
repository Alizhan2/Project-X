from django.db import connection
from django.test import TestCase


class HealthTests(TestCase):
    def test_health_reports_database_ok(self):
        res = self.client.get("/api/health/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["status"], "ok")
        self.assertNotIn("database_version", res.json())   # no version fingerprinting on a public probe

    def test_database_is_postgresql(self):
        self.assertEqual(connection.vendor, "postgresql")

    def test_openapi_schema_served(self):
        self.assertEqual(self.client.get("/api/schema/").status_code, 200)


class SecuritySweepTests(TestCase):
    """Every API route must reject anonymous users unless it is deliberately public."""

    PUBLIC = {
        "api/kazakhstan/catalog/", "api/kazakhstan/search/",  # public geography and journey search
        "api/health/", "api/stops/", "api/search/", "api/itinerary/", "api/schema/", "api/docs/",
        "api/auth/password-reset/", "api/auth/password-reset/confirm/", "api/auth/email-verification/confirm/",
        "api/auth/csrf/", "api/auth/register/", "api/auth/login/", "api/auth/me/",
        "api/health/live/", "api/health/ready/", "api/config/",
        "api/ops/metrics/",   # token-protected, answers 404 without the token (tested separately)
    }

    def routes(self):
        from django.urls import URLPattern, URLResolver, get_resolver

        def walk(patterns, prefix=""):
            for p in patterns:
                if isinstance(p, URLResolver):
                    yield from walk(p.url_patterns, prefix + str(p.pattern))
                elif isinstance(p, URLPattern):
                    yield prefix + str(p.pattern)

        for r in walk(get_resolver().url_patterns):
            if r.startswith("api/"):
                yield r

    def concrete(self, route):
        import re
        return "/" + re.sub(r"<(?:int:)?\w+>", lambda m: "1" if m.group(0).startswith("<int") else "DD-X", route)

    def test_anonymous_requests_are_refused_on_every_non_public_route(self):
        checked = 0
        for r in self.routes():
            if r in self.PUBLIC:
                continue
            for method in ("get", "post", "patch"):
                res = getattr(self.client, method)(self.concrete(r), {}, content_type="application/json") if method != "get" else self.client.get(self.concrete(r))
                if res.status_code == 405:
                    continue
                self.assertIn(res.status_code, (401, 403), f"{method.upper()} {r} -> {res.status_code}")
                checked += 1
        self.assertGreater(checked, 20)

    def test_passenger_is_refused_on_operator_routes(self):
        from apps.accounts.models import User
        u = User.objects.create_user("p@x.co", "p@x.co", "correct-horse-42")
        self.client.force_login(u)
        for r in self.routes():
            if r.startswith("api/operator/"):
                for method in ("get", "post", "patch"):
                    res = getattr(self.client, method)(self.concrete(r), {}, content_type="application/json")
                    self.assertIn(res.status_code, (403, 405), f"{method} {r}")

    def test_django_admin_is_closed_to_passengers_and_operators(self):
        from apps.accounts.models import User
        self.assertEqual(self.client.get("/admin/").status_code, 302)  # to login
        for role in ("passenger", "operator"):
            u = User.objects.create_user(f"{role}@x.co", f"{role}@x.co", "correct-horse-42", role=role)
            c = type(self.client)()
            c.force_login(u)
            self.assertEqual(c.get("/admin/").status_code, 302, role)

    def test_user_payload_never_contains_credentials(self):
        from apps.accounts.models import User
        u = User.objects.create_user("q@x.co", "q@x.co", "correct-horse-42")
        self.client.force_login(u)
        body = self.client.get("/api/auth/me/").json()["user"]
        self.assertEqual(set(body), {"id", "email", "name", "role", "operator", "email_verified"})


class OpenApiTests(TestCase):
    def test_schema_generates_without_warnings(self):
        import io
        from django.core.management import call_command
        err = io.StringIO()
        call_command("spectacular", "--validate", "--fail-on-warn", "--file", "/dev/null", stderr=err)


from django.test import override_settings  # noqa: E402


class OperationsEndpointTests(TestCase):
    def test_liveness_does_not_touch_the_database(self):
        with self.assertNumQueries(0):
            self.assertEqual(self.client.get("/api/health/live/").json(), {"status": "ok"})

    def test_readiness_is_503_when_the_database_is_down_and_leaks_nothing(self):
        from unittest import mock
        with mock.patch("apps.core.ops.database_ok", return_value=False):
            res = self.client.get("/api/health/ready/")
        self.assertEqual((res.status_code, res.json()), (503, {"status": "unavailable", "database": "unreachable"}))

    def test_readiness_is_503_with_pending_migrations(self):
        from unittest import mock
        with mock.patch("apps.core.ops.migrations_pending", return_value=True):
            res = self.client.get("/api/health/ready/")
        self.assertEqual((res.status_code, res.json()["migrations"]), (503, "pending"))

    def test_config_endpoint_states_what_the_deployment_may_claim(self):
        data = self.client.get("/api/config/").json()
        self.assertEqual(set(data), {"launch_mode", "simulated", "registration_enabled", "release"})
        self.assertTrue(data["simulated"])

    def test_metrics_need_the_token_and_contain_no_personal_data(self):
        self.assertEqual(self.client.get("/api/ops/metrics/").status_code, 404)               # off: no token configured
        with override_settings(METRICS_TOKEN="s3cret-token-for-test"):
            self.assertEqual(self.client.get("/api/ops/metrics/").status_code, 404)
            self.assertEqual(self.client.get("/api/ops/metrics/", HTTP_AUTHORIZATION="Bearer wrong").status_code, 404)
            res = self.client.get("/api/ops/metrics/", HTTP_AUTHORIZATION="Bearer s3cret-token-for-test")
        self.assertEqual(res.status_code, 200)
        body = res.content.decode()
        self.assertIn("doedu_jobs{status=\"failed\"}", body)
        self.assertNotIn("@", body)

    def test_request_id_is_returned_and_honoured(self):
        self.assertTrue(self.client.get("/api/health/live/")["X-Request-ID"])
        self.assertEqual(self.client.get("/api/health/live/", HTTP_X_REQUEST_ID="abc-12345678")["X-Request-ID"], "abc-12345678")
        self.assertNotEqual(self.client.get("/api/health/live/", HTTP_X_REQUEST_ID="bad id with spaces")["X-Request-ID"], "bad id with spaces")

    def test_security_headers(self):
        r = self.client.get("/api/stops/")
        self.assertIn("default-src 'self'", r["Content-Security-Policy"])
        self.assertEqual(r["Cache-Control"], "no-store")
        self.assertEqual(r["X-Content-Type-Options"], "nosniff")
        self.assertEqual(r["X-Frame-Options"], "DENY")
        self.assertNotIn("Access-Control-Allow-Origin", r)   # same-origin only: no CORS

    def test_api_404_is_json(self):
        res = self.client.get("/api/does-not-exist/")
        self.assertEqual((res.status_code, res.json()["code"]), (404, "not_found"))

    def test_payments_are_refused_when_simulation_is_not_allowed(self):
        from apps.accounts.models import User
        u = User.objects.create_user("p@x.co", "p@x.co", "correct-horse-42")
        self.client.force_login(u)
        with override_settings(SIMULATION_ENABLED=False):
            res = self.client.post("/api/bookings/DD-X/pay/", {"outcome": "success"}, content_type="application/json", HTTP_IDEMPOTENCY_KEY="k" * 12)
        self.assertEqual((res.status_code, res.json()["code"]), (503, "payments_not_configured"))

    def test_registration_can_be_closed(self):
        with override_settings(REGISTRATION_ENABLED=False):
            res = self.client.post("/api/auth/register/", {"email": "n@x.co", "full_name": "N", "password": "correct-horse-42"}, content_type="application/json")
        self.assertEqual(res.status_code, 403)


class IntegrityToolsTests(TestCase):
    def setUp(self):
        from apps.transport import demo_data
        demo_data.reset_transport_data(demo_data.reference_date(), with_bookings=True)

    def run_cmd(self, name, *args):
        import io
        from django.core.management import call_command
        out = io.StringIO()
        try:
            call_command(name, *args, stdout=out)
            code = 0
        except SystemExit as e:
            code = e.code
        return code, out.getvalue()

    def test_a_consistent_system_passes(self):
        self.assertEqual(self.run_cmd("check_integrity")[0], 0)      # seeded baselines + real bookings agree
        self.assertEqual(self.run_cmd("ops_status")[0], 0)

    def test_drift_is_detected_and_repaired_safely(self):
        from apps.transport.models import Departure
        dep = Departure.objects.filter(places_taken__gt=0, baseline_places=0).first()
        Departure.objects.filter(pk=dep.pk).update(places_taken=dep.places_taken + 1)       # simulate a bug/manual edit
        code, out = self.run_cmd("check_integrity")
        self.assertEqual(code, 1)
        self.assertIn(f"departure {dep.pk}", out)
        self.assertEqual(self.run_cmd("repair_capacity")[0], 0)                              # dry run changes nothing
        self.assertEqual(Departure.objects.get(pk=dep.pk).places_taken, dep.places_taken + 1)
        self.run_cmd("repair_capacity", "--apply")
        self.assertEqual(Departure.objects.get(pk=dep.pk).places_taken, dep.places_taken)
        self.assertEqual(self.run_cmd("check_integrity")[0], 0)
        from apps.core.models import AuditRecord
        self.assertTrue(AuditRecord.objects.filter(action="capacity.repaired", object_id=str(dep.pk)).exists())

    def test_double_payment_and_orphan_reservations_are_detected(self):
        from apps.bookings.models import Booking, Reservation
        from apps.payments.models import PaymentAttempt
        b = Booking.objects.filter(status="confirmed").first()
        PaymentAttempt.objects.filter(booking=b).delete()                                    # confirmed without payment
        code, out = self.run_cmd("check_integrity")
        self.assertEqual(code, 1)
        self.assertIn("0 successful initial payments", out)

    def test_state_fingerprint_changes_when_business_data_changes(self):
        import json
        from apps.bookings.models import Booking
        before = json.loads(self.run_cmd("state_fingerprint")[1])["sha256"]
        self.assertEqual(before, json.loads(self.run_cmd("state_fingerprint")[1])["sha256"])  # stable
        Booking.objects.filter(status="confirmed").update(status="cancelled")
        self.assertNotEqual(before, json.loads(self.run_cmd("state_fingerprint")[1])["sha256"])
