import json

from django.test import TestCase

from apps.bookings.tests import BookingTestBase, body, checkout, client_for, confirmed_booking, depart_in, make_user, pay
from apps.disruptions.tests import chain_booking, change, make_operator_user
from apps.transport.models import Departure


def titles(client, ref):
    return [e["title"] for e in client.get(f"/api/bookings/{ref}/").json()["activity"]]


class ActivityTests(BookingTestBase, TestCase):
    def test_reserved_then_paid_in_order_with_simulated_labels(self):
        ref = checkout(self.c, body(self.dep)).json()["reference"]
        self.assertEqual(titles(self.c, ref), ["Places reserved"])
        pay(self.c, ref)
        events = self.c.get(f"/api/bookings/{ref}/").json()["activity"]
        self.assertEqual([e["title"] for e in events], ["Places reserved", "Payment confirmed (simulated)"])
        self.assertEqual((events[1]["amount"], events[1]["currency"]), ("7.00", "EUR"))
        self.assertEqual([e["at"] for e in events], sorted(e["at"] for e in events))

    def test_failed_payment_is_visible_before_the_successful_one(self):
        ref = checkout(self.c, body(self.dep)).json()["reference"]
        pay(self.c, ref, "failure")
        pay(self.c, ref, "success")
        self.assertEqual(titles(self.c, ref), ["Places reserved", "Payment failed (simulated)", "Payment confirmed (simulated)"])

    def test_disruption_cancellation_and_refund_appear_in_time_order(self):
        valley = client_for(make_operator_user("valley"))
        ref = chain_booking(self.c)
        change(valley, Departure.objects.get(route__code="VC1", departs_at=self.dep.departs_at), "delay", 45)
        depart_in(ref, 1)
        self.c.post(f"/api/bookings/{ref}/cancel/", {}, content_type="application/json")
        events = self.c.get(f"/api/bookings/{ref}/").json()["activity"]
        kinds = [e["kind"] for e in events]
        self.assertEqual(kinds[:2], ["reserved", "payment"])
        self.assertIn("journey_disrupted", kinds)
        self.assertEqual(kinds[-2:], ["refund", "cancelled"])   # same instant: the refund is listed before the cancellation it belongs to
        self.assertEqual([e["at"] for e in events], sorted(e["at"] for e in events))
        refund = next(e for e in events if e["kind"] == "refund")
        self.assertEqual(refund["title"], "Refund issued (simulated)")

    def test_activity_contains_no_personal_data(self):
        ref = confirmed_booking(self.c, self.dep)
        text = json.dumps(self.c.get(f"/api/bookings/{ref}/").json()["activity"])
        self.assertNotIn("@", text)
        self.assertNotIn(self.user.email, text)

    def test_other_passengers_cannot_read_it(self):
        ref = confirmed_booking(self.c, self.dep)
        other = client_for(make_user("p2@example.com"))
        self.assertEqual(other.get(f"/api/bookings/{ref}/").status_code, 404)
