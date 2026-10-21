import json
from datetime import timedelta
from decimal import Decimal

from django.test import Client, TestCase, TransactionTestCase
from django.utils import timezone

from apps.bookings import tests as booking_tests
from apps.bookings.tests import BookingTestBase, client_for, confirmed_booking, dep_at, make_user
from apps.core import jobs
from apps.core.models import Job
from apps.disruptions.tests import make_operator_user
from apps.transport import demo_data
from apps.transport.models import Departure, Fare

from . import watches
from .models import Notification, Watch

DAY = demo_data.reference_date() + timedelta(days=1)


def body(kind="price", origin="NG-BUS", destination="RV-BUS", date=None, time="06:00", passengers=1, modes="bus,train,taxi"):
    return {"kind": kind, "origin": origin, "destination": destination, "date": (date or DAY).isoformat(), "time": time,
            "passengers": passengers, "modes": modes}


def create(c, **kw):
    return c.post("/api/watches/", body(**kw), content_type="application/json")


def fill(route_codes):
    """Make every departure of the given routes sold out (for the demo window)."""
    for d in Departure.objects.filter(route__code__in=route_codes):
        Departure.objects.filter(pk=d.pk).update(places_taken=d.capacity, baseline_places=d.capacity)


class WatchCreationTests(BookingTestBase, TestCase):
    def test_price_watch_records_the_current_cheapest_total(self):
        r = create(self.c, passengers=2)
        self.assertEqual(r.status_code, 201, r.content)
        w = r.json()
        self.assertEqual((w["kind"], w["status"], w["baseline_price"], w["currency"]), ("price", "active", "14.00", "EUR"))
        self.assertTrue(w["link"].startswith("/?origin=NG-BUS&destination=RV-BUS"))
        self.assertIn("passengers=2", w["link"])

    def test_creating_the_same_watch_twice_returns_the_same_one(self):
        a, b = create(self.c).json(), create(self.c, modes="taxi,bus,train")
        self.assertEqual((b.status_code, b.json()["id"]), (200, a["id"]))     # mode order is canonicalised
        self.assertEqual(Watch.objects.count(), 1)

    def test_price_watch_needs_a_journey_and_availability_watch_needs_none(self):
        r = create(self.c, modes="taxi")                                      # no taxi serves NG-BUS -> RV-BUS
        self.assertEqual(r.status_code, 400)
        self.assertIn("kind", r.json())
        r = create(self.c, kind="availability")                                # journeys exist today
        self.assertEqual((r.status_code, "kind" in r.json()), (400, True))
        self.assertEqual(create(self.c, kind="availability", modes="taxi").status_code, 201)

    def test_validation(self):
        past = (timezone.localdate() - timedelta(days=1)).isoformat()
        far = (timezone.localdate() + timedelta(days=200)).isoformat()
        for patch in ({"date": past}, {"date": far}, {"time": "25:00"}, {"passengers": 0}, {"passengers": 10},
                      {"modes": "boat"}, {"modes": "bus,bus"}, {"destination": "NG-BUS"}, {"origin": "ZZZ"}, {"kind": "weather"}):
            data = {**body(), **patch}
            self.assertEqual(self.c.post("/api/watches/", data, content_type="application/json").status_code, 400, patch)

    def test_limit_of_ten_active_watches(self):
        for i in range(10):
            self.assertEqual(create(self.c, time=f"{i:02d}:00", passengers=1).status_code, 201, i)
        self.assertEqual(create(self.c, time="23:30").status_code, 400)
        w = Watch.objects.filter(user=self.user).first()
        self.assertEqual(self.c.delete(f"/api/watches/{w.pk}/").status_code, 204)
        self.assertEqual(create(self.c, time="23:30").status_code, 201)

    def test_ownership_and_anonymous_access(self):
        w = create(self.c).json()
        other = client_for(make_user("p2@example.com"))
        self.assertEqual(other.get("/api/watches/").json()["results"], [])
        self.assertEqual(other.delete(f"/api/watches/{w['id']}/").status_code, 404)
        self.assertEqual(Watch.objects.count(), 1)
        self.assertIn(Client().get("/api/watches/").status_code, (401, 403))


class WatchEvaluationTests(BookingTestBase, TestCase):
    def notes(self, kind):
        return Notification.objects.filter(user=self.user, kind=kind)

    def test_price_drop_notifies_once_then_follows_the_new_price(self):
        w = Watch.objects.get(pk=create(self.c, time="11:30").json()["id"])
        before = w.baseline_price
        self.assertFalse(watches.evaluate(w.pk))                                # nothing changed
        Fare.objects.filter(route__code="VC1", from_stop__code="NG-BUS", to_stop__code="RV-BUS").update(price=Decimal("3.00"))
        self.assertTrue(watches.evaluate(w.pk))
        n = self.notes("watch_price").get()
        self.assertIn("fell from EUR %s to EUR 3.00" % before, n.body)
        self.assertTrue(n.link.startswith("/?origin=NG-BUS"))
        w.refresh_from_db()
        self.assertEqual(w.baseline_price, Decimal("3.00"))
        self.assertFalse(watches.evaluate(w.pk))                                # same price: no duplicate
        self.assertEqual(self.notes("watch_price").count(), 1)

    def test_a_price_rise_is_silent_and_a_later_fall_is_a_new_drop(self):
        w = Watch.objects.get(pk=create(self.c, time="11:30", modes="bus").json()["id"])    # bus only: price follows the bus fares
        fares = Fare.objects.filter(route__code__in=["VC1", "GL1", "GL3"], from_stop__code="NG-BUS", to_stop__code="RV-BUS")
        fares.update(price=Decimal("20.00"))     # direct fares soar; the 2-bus change via Millford (8.40) becomes the cheapest
        self.assertFalse(watches.evaluate(w.pk))                                # went up: nothing to say
        self.assertEqual(Watch.objects.get(pk=w.pk).baseline_price, Decimal("8.40"))          # the baseline follows the latest price
        fares.update(price=Decimal("2.00"))
        self.assertTrue(watches.evaluate(w.pk))                                 # 8.40 -> 2.00 is a drop from the last price seen
        self.assertEqual(self.notes("watch_price").count(), 1)

    def test_availability_watch_fires_once_when_a_place_frees_up(self):
        fill(["VC1", "GL1", "GL3"])
        w = Watch.objects.get(pk=create(self.c, kind="availability", modes="bus").json()["id"])
        self.assertFalse(watches.evaluate(w.pk))
        Departure.objects.filter(route__code="VC1", departs_at=dep_at("VC1", "12:00").departs_at).update(places_taken=0, baseline_places=0)
        self.assertTrue(watches.evaluate(w.pk))
        self.assertIn("Journeys are now available", self.notes("watch_available").get().title)
        w.refresh_from_db()
        self.assertEqual(w.status, "triggered")
        self.assertFalse(watches.evaluate(w.pk))                                # one-shot: ended
        self.assertEqual(self.notes("watch_available").count(), 1)

    def test_cancelling_a_booking_frees_the_place_and_triggers_the_alert_end_to_end(self):
        last = dep_at("GL1", "07:30")
        fill(["VC1", "GL1", "GL3"])
        Departure.objects.filter(pk=last.pk).update(places_taken=last.capacity - 1, baseline_places=last.capacity - 1)   # one place left
        ref = confirmed_booking(self.c, last)                                   # takes it
        other = client_for(make_user("p2@example.com"))
        watcher = Watch.objects.get(pk=create(other, kind="availability", modes="bus").json()["id"])
        self.assertEqual(watcher.status, "active")
        with self.captureOnCommitCallbacks(execute=True):
            self.c.post(f"/api/bookings/{ref}/cancel/", {}, content_type="application/json")
        self.assertTrue(Job.objects.filter(kind="evaluate_watches").exists())    # cancellation queued a prompt evaluation
        jobs.run_pending()
        self.assertEqual(Notification.objects.filter(user__email="p2@example.com", kind="watch_available").count(), 1)

    def test_an_expired_watch_never_notifies(self):
        w = Watch.objects.get(pk=create(self.c).json()["id"])
        Watch.objects.filter(pk=w.pk).update(date=timezone.localdate() - timedelta(days=1))
        self.assertFalse(watches.evaluate(w.pk))
        w.refresh_from_db()
        self.assertEqual(w.status, "expired")

    def test_listing_evaluates_lazily_so_it_works_without_a_worker(self):
        create(self.c, time="11:30")
        Fare.objects.filter(route__code__in=["VC1", "GL1", "GL3"], from_stop__code="NG-BUS", to_stop__code="RV-BUS").update(price=Decimal("1.00"))
        listed = self.c.get("/api/watches/").json()
        self.assertEqual(listed["results"][0]["baseline_price"], "1.00")
        self.assertEqual(self.notes("watch_price").count(), 1)
        self.assertEqual(self.c.get("/api/notifications/").json()["results"][0]["link"][:2], "/?")

    def test_operator_edits_queue_a_prompt_evaluation_and_bursts_collapse(self):
        create(self.c, time="11:30")
        valley = client_for(make_operator_user("valley"))
        fare = Fare.objects.get(route__code="VC1", from_stop__code="NG-BUS", to_stop__code="RV-BUS")
        with self.captureOnCommitCallbacks(execute=True):
            for price in ("6.50", "6.00", "5.50"):
                valley.patch(f"/api/operator/fares/{fare.pk}/", {"price": price}, content_type="application/json")
        self.assertEqual(Job.objects.filter(kind="evaluate_watches").count(), 1)        # three edits, one job
        jobs.run_pending()
        self.assertEqual(self.notes("watch_price").count(), 1)

    def test_worker_periodic_job_is_created_once_per_window(self):
        watches.ensure_periodic()
        watches.ensure_periodic()
        self.assertEqual(Job.objects.filter(kind="evaluate_watches").count(), 1)

    def test_deleting_the_account_removes_watches(self):
        create(self.c)
        self.user.delete()
        self.assertEqual(Watch.objects.count(), 0)


class WatchConcurrencyTests(TransactionTestCase):
    def setUp(self):
        demo_data.reset_transport_data(demo_data.reference_date())

    def test_parallel_evaluations_notify_exactly_once(self):
        user = make_user()
        c = client_for(user)
        fill(["VC1", "GL1", "GL3"])
        w = Watch.objects.get(pk=create(c, kind="availability", modes="bus").json()["id"])
        Departure.objects.filter(route__code="VC1").update(places_taken=0, baseline_places=0)
        results = booking_tests.ConcurrencyTests.run_threads(self, [lambda: watches.evaluate(w.pk) for _ in range(6)])
        self.assertEqual(sum(1 for r in results if r), 1)
        self.assertEqual(Notification.objects.filter(user=user, kind="watch_available").count(), 1)


    def test_simultaneous_listings_both_see_the_finished_evaluation(self):
        user = make_user("lister@example.com")
        c = client_for(user)
        create(c, time="11:30", modes="bus")
        Fare.objects.filter(route__code="VC1", from_stop__code="NG-BUS", to_stop__code="RV-BUS").update(price=Decimal("1.00"))
        seen = booking_tests.ConcurrencyTests.run_threads(self, [lambda: client_for(user).get("/api/watches/").json()["results"][0]["baseline_price"] for _ in range(4)])
        self.assertEqual(seen, ["1.00"] * 4)                                     # nobody reads the stale price
        self.assertEqual(Notification.objects.filter(user=user, kind="watch_price").count(), 1)
