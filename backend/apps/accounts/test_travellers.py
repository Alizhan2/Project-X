from django.test import Client, TestCase

from .models import SavedTraveller, User


def make(email):
    u = User.objects.create_user(email, email, "correct-horse-42")
    c = Client()
    c.force_login(u)
    return u, c


def post(c, name):
    return c.post("/api/travellers/", {"full_name": name}, content_type="application/json")


class SavedTravellerTests(TestCase):
    def test_save_list_and_delete(self):
        u, c = make("a@x.co")
        r = post(c, "  Anna   Lee ")
        self.assertEqual((r.status_code, r.json()["full_name"]), (201, "Anna Lee"))      # whitespace normalised
        self.assertEqual([t["full_name"] for t in c.get("/api/travellers/").json()], ["Anna Lee"])
        self.assertEqual(c.delete(f"/api/travellers/{r.json()['id']}/").status_code, 204)
        self.assertEqual(c.get("/api/travellers/").json(), [])

    def test_same_name_in_any_case_is_stored_once(self):
        u, c = make("a@x.co")
        first = post(c, "Anna Lee").json()
        second = post(c, "anna LEE")
        self.assertEqual((second.status_code, second.json()["id"]), (200, first["id"]))
        self.assertEqual(SavedTraveller.objects.filter(user=u).count(), 1)

    def test_limit_of_ten(self):
        u, c = make("a@x.co")
        for i in range(10):
            self.assertEqual(post(c, f"Traveller {i}").status_code, 201)
        r = post(c, "One too many")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(SavedTraveller.objects.filter(user=u).count(), 10)
        self.assertEqual(post(c, "traveller 3").status_code, 200)       # an existing name still succeeds

    def test_validation(self):
        _, c = make("a@x.co")
        for bad in ("", "   ", "x" * 151):
            self.assertEqual(post(c, bad).status_code, 400, bad)

    def test_ownership_and_anonymous_access(self):
        u1, c1 = make("a@x.co")
        u2, c2 = make("b@x.co")
        mine = post(c1, "Anna Lee").json()
        self.assertEqual(c2.get("/api/travellers/").json(), [])
        self.assertEqual(c2.delete(f"/api/travellers/{mine['id']}/").status_code, 404)
        self.assertEqual(SavedTraveller.objects.filter(user=u1).count(), 1)
        self.assertEqual(post(c2, "Anna Lee").status_code, 201)         # another account may hold the same name
        self.assertIn(Client().get("/api/travellers/").status_code, (401, 403))

    def test_names_vanish_with_the_account(self):
        u, c = make("a@x.co")
        post(c, "Anna Lee")
        u.delete()
        self.assertEqual(SavedTraveller.objects.count(), 0)
