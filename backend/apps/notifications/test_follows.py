from datetime import timedelta

from django.test import Client, TestCase
from django.utils import timezone

from apps.bookings.tests import BookingTestBase, client_for, confirmed_booking, dep_at, make_user
from apps.disruptions.tests import change, make_operator_user
from apps.transport.models import Departure

from .models import LineFollow, Notification


def follow(c, code="VC1"):
    return c.post("/api/follows/", {"route_code": code}, content_type="application/json")


class FollowApiTests(BookingTestBase, TestCase):
    def test_follow_list_and_unfollow(self):
        r = follow(self.c)
        self.assertEqual(r.status_code, 201)
        f = r.json()
        self.assertEqual((f["route_code"], f["mode"], f["operator"], f["from"], f["to"]), ("VC1", "bus", "Valley Coaches", "Northgate Bus Station", "Riverton Bus Station"))
        self.assertEqual([x["route_code"] for x in self.c.get("/api/follows/").json()["results"]], ["VC1"])
        self.assertEqual(self.c.delete(f"/api/follows/{f['id']}/").status_code, 204)
        self.assertEqual(self.c.get("/api/follows/").json()["results"], [])

    def test_following_twice_is_one_follow(self):
        a, b = follow(self.c).json(), follow(self.c)
        self.assertEqual((b.status_code, b.json()["id"]), (200, a["id"]))
        self.assertEqual(LineFollow.objects.count(), 1)

    def test_unknown_lines_and_the_taxi_pseudo_line_are_refused(self):
        for code in ("NOPE", "TAXI", ""):
            self.assertEqual(follow(self.c, code).status_code, 400, code)

    def test_limit_of_ten(self):
        from apps.transport.models import Route
        codes = list(Route.objects.values_list("code", flat=True))
        self.assertGreaterEqual(len(codes), 8)
        from unittest import mock
        with mock.patch("apps.notifications.follows.MAX_FOLLOWS", 3):             # a small limit keeps the test fast
            for code in codes[:3]:
                self.assertEqual(follow(self.c, code).status_code, 201)
            self.assertEqual(follow(self.c, codes[3]).status_code, 400)
            self.assertEqual(follow(self.c, codes[0]).status_code, 200)           # an existing follow still succeeds

    def test_ownership_and_anonymous_access(self):
        f = follow(self.c).json()
        other = client_for(make_user("p2@example.com"))
        self.assertEqual(other.get("/api/follows/").json()["results"], [])
        self.assertEqual(other.delete(f"/api/follows/{f['id']}/").status_code, 404)
        self.assertEqual(LineFollow.objects.count(), 1)
        self.assertIn(Client().get("/api/follows/").status_code, (401, 403))

    def test_following_is_removed_with_the_account(self):
        follow(self.c)
        self.user.delete()
        self.assertEqual(LineFollow.objects.count(), 0)


class FollowNotificationTests(BookingTestBase, TestCase):
    def setUp(self):
        super().setUp()
        self.valley = client_for(make_operator_user("valley"))
        self.green = client_for(make_operator_user("greenline"))
        self.follower = make_user("follower@example.com")
        self.fc = client_for(self.follower)
        follow(self.fc, "VC1")

    def notes(self, kind=None):
        qs = Notification.objects.filter(user=self.follower)
        return qs.filter(kind=kind) if kind else qs

    def near(self):
        """A VC1 service leaving within the notification horizon (tests run at any time of day)."""
        dep = Departure.objects.filter(route__code="VC1", departs_at__gt=timezone.now() + timedelta(hours=1)).order_by("departs_at").first()
        self.assertIsNotNone(dep)
        self.assertLess(dep.departs_at, timezone.now() + timedelta(hours=48))
        return dep

    def test_a_delay_notifies_followers_once_without_a_booking(self):
        dep = self.near()
        change(self.valley, dep, "delay", 25)
        n = self.notes("line_delay").get()
        self.assertEqual(n.title, "Line VC1: delayed by 25 min")
        self.assertIn("You are following this line", n.body)
        self.assertEqual(n.link, "/alerts")
        change(self.valley, dep, "delay", 25)                                  # repeated: a no-op
        self.assertEqual(self.notes().count(), 1)
        change(self.valley, dep, "delay", 40)                                  # a new delay is a new event
        self.assertEqual(self.notes("line_delay").count(), 2)

    def test_cancellation_and_recovery_to_timetable(self):
        a, b = self.near(), Departure.objects.filter(route__code="VC1", departs_at__gt=self.near().departs_at).order_by("departs_at").first()
        change(self.valley, a, "cancel")
        self.assertEqual(self.notes("line_cancel").get().title, "Line VC1: cancelled")
        change(self.valley, b, "delay", 15)
        change(self.valley, b, "delay", 0)
        self.assertEqual(self.notes("line_clear").get().title, "Line VC1: back on time")

    def test_distant_services_other_lines_and_unfollowed_lines_stay_quiet(self):
        far = Departure.objects.filter(route__code="VC1", departs_at__gt=timezone.now() + timedelta(hours=60)).order_by("departs_at").first()
        change(self.valley, far, "delay", 20)
        gl = Departure.objects.filter(route__code="GL1", departs_at__gt=timezone.now() + timedelta(hours=1)).order_by("departs_at").first()
        change(self.green, gl, "delay", 20)
        self.assertEqual(self.notes().count(), 0)
        f = LineFollow.objects.get(user=self.follower)
        self.fc.delete(f"/api/follows/{f.pk}/")
        change(self.valley, self.near(), "delay", 30)
        self.assertEqual(self.notes().count(), 0)

    def test_a_passenger_with_a_booking_gets_the_booking_notice_not_a_second_one(self):
        # self.user holds a booking on the near departure and also follows the line.
        dep = self.near()
        confirmed_booking(self.c, dep)
        follow(self.c, "VC1")
        change(self.valley, dep, "delay", 20)
        mine = Notification.objects.filter(user=self.user)
        self.assertEqual(mine.filter(kind="line_delay").count(), 0)             # no duplicate for the same event
        self.assertEqual(self.notes("line_delay").count(), 1)                   # a pure follower still hears about it

    def test_followers_in_other_operators_cannot_be_reached_by_a_foreign_operator(self):
        dep = self.near()
        self.assertEqual(change(self.green, dep, "delay", 10).status_code, 404)   # not Greenline's service
        self.assertEqual(self.notes().count(), 0)
