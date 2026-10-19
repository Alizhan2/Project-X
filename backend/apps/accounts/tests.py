from django.test import Client, TestCase

from .models import User


def fresh(c):
    """Login/register rotate the CSRF token, so always re-read the cookie (as the SPA does)."""
    return {"HTTP_X_CSRFTOKEN": c.cookies["csrftoken"].value}


def csrf_client():
    c = Client(enforce_csrf_checks=True)
    token = c.get("/api/auth/csrf/").cookies["csrftoken"].value
    return c, {"HTTP_X_CSRFTOKEN": token}


class AuthTests(TestCase):
    def test_register_login_logout_flow_with_csrf(self):
        c, h = csrf_client()
        body = {"email": "Ann@Example.com", "full_name": "Ann Lee", "password": "correct-horse-42"}
        r = c.post("/api/auth/register/", body, content_type="application/json", **h)
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()["role"], "passenger")
        self.assertEqual(c.get("/api/auth/me/").json()["user"]["email"], "ann@example.com")
        self.assertEqual(c.post("/api/auth/logout/", **fresh(c)).status_code, 204)
        self.assertIsNone(c.get("/api/auth/me/").json()["user"])
        r = c.post("/api/auth/login/", {"email": "ann@example.com", "password": "correct-horse-42"}, content_type="application/json", **fresh(c))
        self.assertEqual(r.status_code, 200)

    def test_csrf_required_even_for_login_and_register(self):
        c = Client(enforce_csrf_checks=True)
        r = c.post("/api/auth/login/", {"email": "a@b.co", "password": "x"}, content_type="application/json")
        self.assertEqual(r.status_code, 403)
        r = c.post("/api/auth/register/", {"email": "a@b.co", "full_name": "A", "password": "correct-horse-42"}, content_type="application/json")
        self.assertEqual(r.status_code, 403)

    def test_wrong_password_and_weak_password_rejected(self):
        User.objects.create_user("a@b.co", "a@b.co", "correct-horse-42")
        c, h = csrf_client()
        r = c.post("/api/auth/login/", {"email": "a@b.co", "password": "nope"}, content_type="application/json", **h)
        self.assertEqual(r.status_code, 400)
        r = c.post("/api/auth/register/", {"email": "n@b.co", "full_name": "N", "password": "123"}, content_type="application/json", **h)
        self.assertEqual(r.status_code, 400)
        self.assertIn("password", r.json())

    def test_duplicate_email_rejected(self):
        User.objects.create_user("a@b.co", "a@b.co", "correct-horse-42")
        c, h = csrf_client()
        r = c.post("/api/auth/register/", {"email": "A@b.co", "full_name": "A", "password": "correct-horse-42"}, content_type="application/json", **h)
        self.assertEqual(r.status_code, 400)

    def test_cannot_self_register_as_operator(self):
        c, h = csrf_client()
        c.post("/api/auth/register/", {"email": "o@b.co", "full_name": "O", "password": "correct-horse-42", "role": "admin"}, content_type="application/json", **h)
        self.assertEqual(User.objects.get(email="o@b.co").role, "passenger")
