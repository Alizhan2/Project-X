"""Operator permissions, service changes, disruption effects and notifications."""

from datetime import timedelta
from decimal import Decimal

from django.test import Client, TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.bookings.models import Booking
from apps.bookings.tests import BookingTestBase, checkout, client_for, dep_at, make_user, pay
from apps.core.models import AuditRecord
from apps.disruptions import services as dis
from apps.notifications.models import Notification
from apps.payments.models import Refund
from apps.transport import demo_data
from apps.transport.models import Departure, Fare, Operator, OperatorMembership, Route

DAY = demo_data.reference_date() + timedelta(days=1)


def make_operator_user(code, email=None):
    email = email or f"ops-{code}@example.com"
    u = User.objects.create_user(email, email, "correct-horse-42", role="operator")
    OperatorMembership.objects.create(user=u, operator=Operator.objects.get(code=code))
    return u


def chain_booking(client, first_hhmm="12:00", train_hhmm="13:45", passengers=1, pay_it=True):
    """VC1 (NG-BUS->RV-BUS) + DR1 (RV-RAIL->PM-RAIL) + taxi, found through the real search API."""
    res = client.get("/api/search/", {"origin": "NG-BUS", "destination": "PM-MARINA", "depart_after": f"{DAY}T{first_hhmm}", "passengers": passengers})
    it = next(r for r in res.json()["results"]
              if [l["route_code"] for l in r["legs"]] == ["VC1", "DR1", "TAXI"]
              and r["legs"][0]["departs_at"][11:16] == first_hhmm and r["legs"][1]["departs_at"][11:16] == train_hhmm)
    payload = {"passengers": passengers, "legs": it["selection"], "expected_total": it["total_price"],
               "contact_email": "pat@example.com", "travellers": [f"T{i}" for i in range(passengers)]}
    ref = checkout(client, payload).json()["reference"]
    if pay_it:
        pay(client, ref)
    return ref


def change(c, dep, action, minutes=0):
    return c.post(f"/api/operator/services/{dep.pk}/change/", {"action": action, "minutes": minutes}, content_type="application/json")


class OperatorPermissionTests(BookingTestBase, TestCase):
    def setUp(self):
        super().setUp()
        self.valley = client_for(make_operator_user("valley"))
        self.green = client_for(make_operator_user("greenline"))
        self.gl = dep_at("GL1", "09:30")           # Greenline's service
        self.vc = self.dep                         # Valley's service (VC1 12:00)

    def test_operator_sees_only_own_services(self):
        rows = self.valley.get("/api/operator/services/").json()["results"]
        self.assertTrue(rows)
        self.assertTrue(all(r["route_code"].startswith("VC") for r in rows))
        self.assertTrue(all(r["route_code"].startswith("GL") for r in self.green.get("/api/operator/services/").json()["results"]))

    def test_operator_cannot_touch_another_operators_service(self):
        for call in (
            lambda: self.valley.get(f"/api/operator/services/{self.gl.pk}/"),
            lambda: self.valley.patch(f"/api/operator/services/{self.gl.pk}/", {"capacity": 5}, content_type="application/json"),
            lambda: self.valley.post(f"/api/operator/services/{self.gl.pk}/impact/", {"action": "cancel"}, content_type="application/json"),
            lambda: change(self.valley, self.gl, "cancel"),
            lambda: change(self.valley, self.gl, "delay", 30),
        ):
            self.assertEqual(call().status_code, 404)
        self.gl.refresh_from_db()
        self.assertEqual((self.gl.status, self.gl.delay_minutes, self.gl.capacity), ("scheduled", 0, 16))

    def test_operator_cannot_edit_another_operators_fare_or_create_on_its_route(self):
        gl_fare = Fare.objects.filter(route__operator__code="greenline").first()
        before = gl_fare.price
        r = self.valley.patch(f"/api/operator/fares/{gl_fare.pk}/", {"price": "0.10"}, content_type="application/json")
        self.assertEqual(r.status_code, 404)
        gl_fare.refresh_from_db()
        self.assertEqual(gl_fare.price, before)
        gl_route = Route.objects.get(code="GL1")
        r = self.valley.post("/api/operator/services/", {"route_id": gl_route.pk, "departs_at": (timezone.now() + timedelta(days=3)).isoformat(), "capacity": 10}, content_type="application/json")
        self.assertEqual(r.status_code, 404)

    def test_passengers_and_anonymous_users_are_refused(self):
        self.assertEqual(self.c.get("/api/operator/services/").status_code, 403)
        self.assertEqual(change(self.c, self.vc, "cancel").status_code, 403)
        self.assertEqual(Client().get("/api/operator/services/").status_code, 403)
        self.vc.refresh_from_db()
        self.assertEqual(self.vc.status, "scheduled")

    def test_operator_user_without_membership_is_refused(self):
        u = User.objects.create_user("nomember@example.com", "nomember@example.com", "correct-horse-42", role="operator")
        self.assertEqual(client_for(u).get("/api/operator/services/").status_code, 403)

    def test_create_and_edit_own_service_with_validation(self):
        route = Route.objects.get(code="VC2")
        when = (timezone.now() + timedelta(days=4)).replace(second=0, microsecond=0)
        r = self.valley.post("/api/operator/services/", {"route_id": route.pk, "departs_at": when.isoformat(), "capacity": 30, "wheelchair_accessible": True}, content_type="application/json")
        self.assertEqual(r.status_code, 201, r.content)
        dup = self.valley.post("/api/operator/services/", {"route_id": route.pk, "departs_at": when.isoformat(), "capacity": 30}, content_type="application/json")
        self.assertEqual(dup.status_code, 400)
        sid = r.json()["id"]
        ok = self.valley.patch(f"/api/operator/services/{sid}/", {"capacity": 12}, content_type="application/json")
        self.assertEqual(ok.json()["capacity"], 12)
        self.assertTrue(AuditRecord.objects.filter(action="service.created", object_id=str(sid)).exists())

    def test_capacity_cannot_drop_below_booked_places_and_booked_service_cannot_move(self):
        checkout_ref = checkout(self.c, {"passengers": 3, "legs": [{"departure_id": self.vc.pk, "from_stop": "NG-BUS", "to_stop": "RV-BUS"}], "contact_email": "a@b.co", "travellers": ["a", "b", "c"]})
        self.assertEqual(checkout_ref.status_code, 201)
        r = self.valley.patch(f"/api/operator/services/{self.vc.pk}/", {"capacity": 2}, content_type="application/json")
        self.assertEqual(r.status_code, 400)
        r = self.valley.patch(f"/api/operator/services/{self.vc.pk}/", {"departs_at": (self.vc.departs_at + timedelta(hours=1)).isoformat()}, content_type="application/json")
        self.assertEqual((r.status_code, r.json()["code"]), (409, "has_bookings"))
        ok = self.valley.patch(f"/api/operator/services/{self.vc.pk}/", {"capacity": 3}, content_type="application/json")
        self.assertEqual(ok.status_code, 200)

    def test_fare_change_affects_new_searches_but_not_existing_purchases(self):
        ref = checkout(self.c, {"passengers": 1, "legs": [{"departure_id": self.vc.pk, "from_stop": "NG-BUS", "to_stop": "RV-BUS"}], "contact_email": "a@b.co", "travellers": ["a"]}).json()["reference"]
        pay(self.c, ref)
        fare = Fare.objects.get(route=self.vc.route, from_stop__code="NG-BUS", to_stop__code="RV-BUS")
        r = self.valley.patch(f"/api/operator/fares/{fare.pk}/", {"price": "9.50"}, content_type="application/json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.c.get(f"/api/bookings/{ref}/").json()["total_amount"], "7.00")
        it = self.c.get("/api/itinerary/", {"legs": f"d{self.vc.pk}:NG-BUS:RV-BUS"}).json()
        self.assertEqual(it["total_price"], "9.50")
        self.assertEqual(self.valley.patch(f"/api/operator/fares/{fare.pk}/", {"price": "-1"}, content_type="application/json").status_code, 400)


class ServiceChangeTests(BookingTestBase, TestCase):
    def setUp(self):
        super().setUp()
        self.valley = client_for(make_operator_user("valley"))
        self.ref = chain_booking(self.c)             # VC1 12:00 -> DR1 13:45 -> taxi; 40 min spare
        self.vc = dep_at("VC1", "12:00")

    def notes(self, kind=None):
        qs = Notification.objects.filter(user=self.user)
        return qs.filter(kind=kind) if kind else qs

    def test_small_delay_keeps_connection_and_notifies_delay(self):
        res = change(self.valley, self.vc, "delay", 20)
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(self.notes("journey_delayed").count(), 1)
        live = self.c.get(f"/api/bookings/{self.ref}/").json()["disruption"]
        self.assertEqual((live["status"], live["arrival_delay_minutes"]), ("delayed", 0))  # train unchanged: arrival time holds
        self.assertEqual(self.notes("journey_disrupted").count(), 0)

    def test_big_delay_breaks_connection_and_flags_the_booking(self):
        res = change(self.valley, self.vc, "delay", 45)   # arrives 13:40, +10 walk = 13:50 > 13:45 train
        self.assertEqual(res.json()["affected_bookings"], 1)
        n = self.notes("journey_disrupted").get()
        self.assertIn("connection", n.body)
        live = self.c.get(f"/api/bookings/{self.ref}/").json()["disruption"]
        self.assertEqual((live["status"], live["reason"], live["problem_sequence"]), ("broken", "connection_missed", 1))

    def test_repeating_the_same_change_is_a_noop_without_new_notifications(self):
        change(self.valley, self.vc, "delay", 45)
        again = change(self.valley, self.vc, "delay", 45)
        self.assertTrue(again.json()["noop"])
        self.assertEqual(self.notes().filter(kind="journey_disrupted").count(), 1)
        from apps.disruptions.models import DisruptionEvent
        self.assertEqual(DisruptionEvent.objects.count(), 1)

    def test_changing_the_delay_notifies_again_and_clearing_restores_state(self):
        change(self.valley, self.vc, "delay", 45)
        change(self.valley, self.vc, "delay", 60)
        self.assertEqual(self.notes("journey_disrupted").count(), 2)  # distinct events, distinct notifications
        change(self.valley, self.vc, "delay", 0)
        self.vc.refresh_from_db()
        self.assertEqual((self.vc.status, self.vc.delay_minutes), ("scheduled", 0))
        self.assertEqual(self.c.get(f"/api/bookings/{self.ref}/").json()["disruption"]["status"], "ok")

    def test_cancellation_notifies_removes_from_search_and_allows_full_refund(self):
        change(self.valley, self.vc, "cancel")
        self.assertTrue(self.notes("journey_disrupted").exists())
        res = self.c.get("/api/search/", {"origin": "NG-BUS", "destination": "RV-BUS", "depart_after": f"{DAY}T11:00"}).json()
        self.assertNotIn(self.vc.pk, [r["legs"][0]["departure_id"] for r in res["results"]])
        # Even 1h before departure (normally 0%): a disrupted journey refunds every unused leg in full.
        from apps.bookings.tests import depart_in
        depart_in(self.ref, 1)
        q = self.c.get(f"/api/bookings/{self.ref}/cancellation/").json()
        self.assertTrue(q["disrupted"])
        self.assertTrue(all(l["percent"] == 100 for l in q["lines"]))
        cancel = self.c.post(f"/api/bookings/{self.ref}/cancel/", {}, content_type="application/json").json()
        self.assertEqual(cancel["refunds"][0]["reason"], "Cancelled after disruption")
        self.assertEqual(Decimal(cancel["refunds"][0]["amount"]), Decimal(cancel["total_amount"]))

    def test_cancelling_twice_and_changing_a_cancelled_service(self):
        change(self.valley, self.vc, "cancel")
        self.assertTrue(change(self.valley, self.vc, "cancel").json()["noop"])
        r = change(self.valley, self.vc, "delay", 10)
        self.assertEqual((r.status_code, r.json()["code"]), (409, "already_cancelled"))

    def test_delay_validation_and_finished_services(self):
        self.assertEqual(self.valley.post(f"/api/operator/services/{self.vc.pk}/change/", {"action": "delay", "minutes": 100000}, content_type="application/json").status_code, 400)
        old = Departure.objects.filter(route__code="VC1", departs_at__lt=timezone.now() - timedelta(hours=3)).first()
        if old:
            self.assertEqual((change(self.valley, old, "delay", 5).status_code), 409)

    def test_impact_preview_changes_nothing_and_hides_personal_data(self):
        r = self.valley.post(f"/api/operator/services/{self.vc.pk}/impact/", {"action": "delay", "minutes": 45}, content_type="application/json").json()
        self.assertEqual((len(r["affected"]), r["broken"], r["passengers"]), (1, 1, 1))
        row = r["affected"][0]
        self.assertEqual((row["before"], row["after"], row["reason"]), ("ok", "broken", "connection_missed"))
        self.assertEqual(set(row), {"reference", "passengers", "booking_status", "before", "after", "reason", "arrival_delay_minutes"})
        self.vc.refresh_from_db()
        self.assertEqual((self.vc.status, self.vc.delay_minutes), ("scheduled", 0))
        self.assertEqual(Notification.objects.count(), 0)

    def test_delay_on_the_first_leg_of_a_three_leg_booking_flags_the_later_legs(self):
        a = dis.assess(Booking.objects.get(reference=self.ref), {self.vc.pk: ("delayed", 60)})
        self.assertEqual((a.status, a.reason, a.problem_sequence), ("broken", "connection_missed", 1))
        a = dis.assess(Booking.objects.get(reference=self.ref), {self.vc.pk: ("delayed", 5)})
        self.assertEqual((a.status, a.arrival_delay_minutes), ("delayed", 0))  # first leg is late but every connection holds

    def test_delay_pushing_a_taxi_pickup_outside_service_hours_breaks_the_journey(self):
        train = Departure.objects.get(pk=Booking.objects.get(reference=self.ref).legs.get(sequence=1).departure_id)
        a = dis.assess(Booking.objects.get(reference=self.ref), {train.pk: ("delayed", 12 * 60)})
        self.assertEqual((a.status, a.reason), ("broken", "taxi_unavailable"))

    def test_unpaid_reservation_on_a_cancelled_service_is_released(self):
        other = make_user("p2@example.com")
        oc = client_for(other)
        ref = checkout(oc, {"passengers": 2, "legs": [{"departure_id": self.vc.pk, "from_stop": "NG-BUS", "to_stop": "RV-BUS"}], "contact_email": "a@b.co", "travellers": ["a", "b"]}).json()["reference"]
        before = Departure.objects.get(pk=self.vc.pk).places_taken
        change(self.valley, self.vc, "cancel")
        self.assertEqual(Booking.objects.get(reference=ref).status, "cancelled")
        self.assertEqual(Departure.objects.get(pk=self.vc.pk).places_taken, before - 2)
        self.assertTrue(Notification.objects.filter(user=other, kind="reservation_released").exists())

    def test_changes_are_audited(self):
        change(self.valley, self.vc, "delay", 45)
        a = AuditRecord.objects.get(action="service.delay")
        self.assertEqual((a.object_id, a.detail["affected_bookings"]), (str(self.vc.pk), 1))


class NotificationTests(BookingTestBase, TestCase):
    def test_notifications_are_private_and_markable(self):
        from apps.notifications.services import notify
        other = make_user("p2@example.com")
        n1 = notify(self.user, "x", "Hello", "body", dedupe_key="a")
        notify(other, "x", "Secret", "body", dedupe_key="a")
        self.assertIsNone(notify(self.user, "x", "Hello", "body", dedupe_key="a"))  # idempotent
        data = self.c.get("/api/notifications/").json()
        self.assertEqual((data["unread"], [n["title"] for n in data["results"]]), (1, ["Hello"]))
        oc = client_for(other)
        oc.post(f"/api/notifications/{n1.pk}/read/")              # someone else's: silently ignored
        self.assertEqual(self.c.get("/api/notifications/").json()["unread"], 1)
        self.c.post(f"/api/notifications/{n1.pk}/read/")
        self.assertEqual(self.c.get("/api/notifications/").json()["unread"], 0)
        self.assertEqual(Client().get("/api/notifications/").status_code, 403)
