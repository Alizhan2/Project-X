"""Stage 6: disruption recovery against PostgreSQL."""

import uuid
from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.test import Client, TestCase, TransactionTestCase
from django.utils import timezone

from apps.bookings.models import Booking, BookingLeg, Reservation
from apps.bookings import tests as booking_tests  # module import: keeps its TestCases from being collected twice
from apps.bookings.tests import BookingTestBase, checkout, client_for, confirmed_booking, dep_at, make_user, pay
from apps.core import jobs
from apps.core.models import AuditRecord, Job
from apps.disruptions.models import ReplacementOffer
from apps.disruptions.tests import DAY, chain_booking, change, make_operator_user
from apps.notifications.models import Notification
from apps.payments.models import PaymentAttempt, Refund
from apps.transport import demo_data
from apps.transport.models import Departure


def offers(c, ref):
    r = c.get(f"/api/bookings/{ref}/replacements/")
    assert r.status_code == 200, r.content
    return r.json()


def accept(c, ref, offer_id, outcome="success", key=None):
    return c.post(f"/api/bookings/{ref}/replacements/{offer_id}/accept/", {"outcome": outcome}, content_type="application/json",
                  HTTP_IDEMPOTENCY_KEY=key or uuid.uuid4().hex)


def settlement(data, kind):
    return next(o for o in data["offers"] if o["settlement"] == kind)


def live_places(dep):
    """Places the reservation table says are live for a departure (held or consumed)."""
    from django.db.models import Sum
    return Reservation.objects.filter(departure=dep, status__in=["held", "consumed"]).aggregate(s=Sum("places"))["s"] or 0


class RecoveryBase(BookingTestBase):
    def setUp(self):
        super().setUp()
        self.valley = client_for(make_operator_user("valley"))
        self.green = client_for(make_operator_user("greenline"))
        self.rail = client_for(make_operator_user("rail"))

    def broken_chain(self):
        """VC1 12:00 + DR1 13:45 + taxi, then a 45 min delay on the bus breaks the train connection."""
        ref = chain_booking(self.c)
        change(self.valley, dep_at("VC1", "12:00"), "delay", 45)
        return ref


class DetectionTests(RecoveryBase, TestCase):
    def test_delay_that_preserves_the_connection_is_informational(self):
        ref = chain_booking(self.c)
        change(self.valley, dep_at("VC1", "12:00"), "delay", 20)
        self.assertFalse(Job.objects.filter(kind="recover_booking").exists())
        self.assertEqual(offers(self.c, ref)["state"], "not_disrupted")
        self.assertEqual(ReplacementOffer.objects.count(), 0)
        self.assertEqual(Notification.objects.filter(kind="journey_delayed").count(), 1)

    def test_delay_that_breaks_it_queues_one_recovery_job_and_worker_creates_offers_once(self):
        ref = self.broken_chain()
        self.assertEqual(Job.objects.filter(kind="recover_booking").count(), 1)
        self.assertEqual(jobs.run_pending(), 1)
        self.assertEqual(Notification.objects.filter(kind="replacement_options").count(), 1)
        n = ReplacementOffer.objects.count()
        self.assertTrue(n)
        change(self.valley, dep_at("VC1", "12:00"), "delay", 45)     # repeated: no-op
        self.assertEqual(jobs.run_pending(), 0)
        offers(self.c, ref)                                          # repeated refresh: same offers
        self.assertEqual(ReplacementOffer.objects.filter(status="proposed").count(), n)
        self.assertEqual(Notification.objects.filter(kind="replacement_options").count(), 1)
        self.assertEqual(Notification.objects.filter(kind="journey_disrupted").count(), 1)

    def test_offer_content_and_rules(self):
        ref = self.broken_chain()
        d = offers(self.c, ref)
        self.assertEqual(d["state"], "options")
        self.assertEqual([l["route_code"] for l in d["retained_legs"]], ["VC1"])
        self.assertEqual([l["route_code"] for l in d["affected_legs"]], ["DR1", "TAXI"])
        for o in d["offers"]:
            self.assertFalse(o["reserves_capacity"])
            self.assertIn("not held", o["availability_warning"])
            self.assertEqual(Decimal(o["difference"]), Decimal(o["replacement_price"]) - Decimal(o["replaced_value"]))
            self.assertTrue(o["legs"] and o["expires_at"])
            first = o["legs"][0]
            self.assertGreaterEqual(first["departs_at"][11:16], "13:45")      # nothing the passenger already missed
            self.assertNotEqual(first["status"], "cancelled")
            self.assertIn("accessibility", first)
            self.assertLessEqual(len(o["legs"]) + 1, 3)                      # retained + replacement <= 3 legs
        self.assertTrue(all(o["arrives_at"] <= f"{DAY + timedelta(days=1)}" for o in d["offers"]))

    def test_cancelled_service_is_excluded_from_offers(self):
        ref = confirmed_booking(self.c, dep_at("VC1", "12:00"))
        change(self.valley, dep_at("VC1", "12:00"), "cancel")
        d = offers(self.c, ref)
        self.assertTrue(d["offers"])
        used = {l["departure_id"] for o in d["offers"] for l in o["legs"]}
        self.assertNotIn(dep_at("VC1", "12:00").pk, used)

    def test_no_alternative_explains_and_offers_full_refund_cancellation(self):
        # Last Lakeside bus (VC2 19:30) can no longer be reached after a long train delay; nothing else gets there in time.
        train, bus = dep_at("DR1", "18:10"), dep_at("VC2", "19:30")
        c = self.c
        sel = [{"departure_id": train.pk, "from_stop": "NG-RAIL", "to_stop": "RV-RAIL"}, {"departure_id": bus.pk, "from_stop": "RV-BUS", "to_stop": "LK-BUS"}]
        ref = checkout(c, {"passengers": 1, "legs": sel, "contact_email": "a@b.co", "travellers": ["a"]}).json()["reference"]
        pay(c, ref)
        change(self.rail, train, "delay", 60)
        d = offers(c, ref)
        self.assertEqual((d["state"], d["offers"], d["reason"]), ("none", [], "connection_missed"))
        self.assertTrue(d["cancellation"]["disrupted"])
        self.assertTrue(all(l["percent"] == 100 for l in d["cancellation"]["lines"]))
        jobs.run_pending()
        self.assertEqual(Notification.objects.filter(kind="no_replacement").count(), 1)
        self.assertEqual(c.post(f"/api/bookings/{ref}/cancel/", {}, content_type="application/json").json()["status"], "cancelled")

    def test_recovery_job_retries_and_recovers_after_restart(self):
        ref = self.broken_chain()
        job = Job.objects.get(kind="recover_booking")
        with mock.patch("apps.disruptions.recovery.ensure_offers", side_effect=RuntimeError("boom")):
            self.assertEqual(jobs.run_pending(), 1)
        job.refresh_from_db()
        self.assertEqual((job.status, job.attempts), ("pending", 1))
        recover = Job.objects.filter(kind="recover_booking")
        recover.update(run_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(jobs.run_pending(), 1)
        self.assertEqual(recover.get().status, "done")
        # A worker that died mid-run: running + stale lock is reclaimed.
        recover.update(status="running", locked_at=timezone.now() - timedelta(minutes=10), run_at=timezone.now() - timedelta(minutes=10))
        self.assertEqual(jobs.run_pending(), 1)
        self.assertEqual(ReplacementOffer.objects.filter(status="proposed", booking__reference=ref).count(), len(offers(self.c, ref)["offers"]))


class AcceptanceTests(RecoveryBase, TestCase):
    def test_accept_equal_price_replacement_preserves_history(self):
        ref = self.broken_chain()
        before = Booking.objects.get(reference=ref)
        kept_leg = before.legs.get(sequence=0)
        old_train_dep = dep_at("DR1", "13:10")
        d = offers(self.c, ref)
        offer = settlement(d, "none")
        new_ids = [l["departure_id"] for l in offer["legs"] if l["departure_id"]]
        res = accept(self.c, ref, offer["id"])
        self.assertEqual(res.status_code, 200, res.content)
        b = Booking.objects.get(reference=ref)
        legs = list(b.legs.order_by("sequence"))
        self.assertEqual([l.status for l in legs[:3]], ["booked", "replaced", "replaced"])     # original history kept
        self.assertEqual(legs[0].pk, kept_leg.pk)
        self.assertEqual((legs[0].unit_price, legs[0].departs_at), (kept_leg.unit_price, kept_leg.departs_at))
        self.assertEqual({l.status for l in legs[3:]}, {"booked"})
        self.assertEqual(b.total_amount, before.total_amount)
        self.assertEqual(Departure.objects.get(pk=old_train_dep.pk).places_taken, 0)           # old places released
        for pk in new_ids:
            self.assertEqual(Departure.objects.get(pk=pk).places_taken, 1)
        self.assertEqual(self.c.get(f"/api/bookings/{ref}/").json()["disruption"]["status"], "delayed")  # no longer broken
        self.assertTrue(AuditRecord.objects.filter(action="booking.replacement_accepted", object_id=ref).exists())
        self.assertEqual(Notification.objects.filter(kind="replacement_confirmed").count(), 1)
        self.assertEqual(ReplacementOffer.objects.filter(status="proposed").count(), 0)         # siblings superseded

    def test_duplicate_acceptance_changes_nothing_twice(self):
        ref = self.broken_chain()
        offer = offers(self.c, ref)["offers"][0]
        first = accept(self.c, ref, offer["id"])
        again = accept(self.c, ref, offer["id"])
        self.assertEqual((first.json()["replayed"], again.json()["replayed"]), (False, True))
        self.assertEqual(Booking.objects.get(reference=ref).legs.count(), 3 + len(offer["legs"]))
        self.assertEqual(Notification.objects.filter(kind="replacement_confirmed").count(), 1)

    def cancelled_vc1(self):
        ref = confirmed_booking(self.c, dep_at("VC1", "12:00"))
        change(self.valley, dep_at("VC1", "12:00"), "cancel")
        return ref

    def test_replacement_that_costs_more_needs_a_simulated_top_up(self):
        ref = self.cancelled_vc1()
        offer = settlement(offers(self.c, ref), "pay")
        self.assertEqual(offer["difference"], "0.10")
        bad = accept(self.c, ref, offer["id"], "failure")
        self.assertEqual((bad.status_code, bad.json()["code"]), (409, "payment_failed"))
        b = Booking.objects.get(reference=ref)                       # coherent: nothing changed except the failed attempt
        self.assertEqual((b.total_amount, b.legs.count(), ReplacementOffer.objects.get(pk=offer["id"]).status), (Decimal("7.00"), 1, "proposed"))
        self.assertEqual(Departure.objects.get(pk=dep_at("VC1", "12:00").pk).places_taken, 1)
        self.assertEqual(PaymentAttempt.objects.filter(purpose="replacement", status="failed").count(), 1)
        key = uuid.uuid4().hex
        ok = accept(self.c, ref, offer["id"], "success", key)
        self.assertEqual(ok.status_code, 200, ok.content)
        accept(self.c, ref, offer["id"], "success", key)              # repeat: no second charge
        top_ups = PaymentAttempt.objects.filter(purpose="replacement", status="succeeded")
        self.assertEqual((top_ups.count(), top_ups.get().amount), (1, Decimal("0.10")))
        self.assertEqual(Booking.objects.get(reference=ref).total_amount, Decimal("7.10"))
        self.assertEqual(PaymentAttempt.objects.filter(purpose="initial", status="succeeded").count(), 1)

    def test_failed_payment_attempt_with_same_key_is_replayed_not_retried(self):
        ref = self.cancelled_vc1()
        offer = settlement(offers(self.c, ref), "pay")
        key = uuid.uuid4().hex
        self.assertEqual(accept(self.c, ref, offer["id"], "failure", key).status_code, 409)
        self.assertEqual(accept(self.c, ref, offer["id"], "success", key).json()["code"], "payment_failed")
        self.assertEqual(PaymentAttempt.objects.filter(purpose="replacement").count(), 1)

    def test_cheaper_replacement_refunds_the_difference_once(self):
        ref = confirmed_booking(self.c, dep_at("GL1", "12:30"))        # 7.10
        change(self.green, dep_at("GL1", "12:30"), "cancel")
        offer = settlement(offers(self.c, ref), "refund")
        self.assertEqual(offer["difference"], "-0.10")
        for _ in range(3):
            self.assertEqual(accept(self.c, ref, offer["id"]).status_code, 200)
        r = Refund.objects.get(booking__reference=ref)
        self.assertEqual((r.amount, r.reason, r.status), (Decimal("0.10"), "replacement_difference", "completed"))
        self.assertEqual(Booking.objects.get(reference=ref).total_amount, Decimal("7.00"))
        # Cancelling afterwards refunds by the new legs' own policy; the earlier refund is untouched.
        self.c.post(f"/api/bookings/{ref}/cancel/", {}, content_type="application/json")
        self.assertEqual(Refund.objects.filter(booking__reference=ref).count(), 2)

    def test_expired_offer_cannot_be_accepted_and_is_regenerated(self):
        ref = self.broken_chain()
        offer = offers(self.c, ref)["offers"][0]
        ReplacementOffer.objects.filter(pk=offer["id"]).update(expires_at=timezone.now() - timedelta(seconds=1))
        r = accept(self.c, ref, offer["id"])
        self.assertEqual((r.status_code, r.json()["code"]), (409, "offer_expired"))
        self.assertEqual(ReplacementOffer.objects.get(pk=offer["id"]).status, "expired")
        fresh = offers(self.c, ref)
        self.assertTrue(fresh["offers"])
        self.assertNotIn(offer["id"], [o["id"] for o in fresh["offers"]])
        self.assertEqual(Booking.objects.get(reference=ref).legs.count(), 3)

    def test_service_changing_again_before_acceptance_invalidates_the_offer(self):
        ref = self.broken_chain()
        d = offers(self.c, ref)
        target = d["offers"][0]
        replacement_dep = next(l["departure_id"] for l in target["legs"] if l["departure_id"])
        # (a) detected by the job: the replacement service itself is cancelled
        op = {"rail": self.rail, "valley": self.valley}[ "rail" if Departure.objects.get(pk=replacement_dep).route.operator.code == "rail" else "valley"]
        change(op, Departure.objects.get(pk=replacement_dep), "cancel")
        jobs.run_pending()
        self.assertEqual(ReplacementOffer.objects.get(pk=target["id"]).status, "invalidated")
        r = accept(self.c, ref, target["id"])
        self.assertEqual((r.status_code, r.json()["code"]), (409, "offer_unavailable"))

    def test_change_between_generation_and_acceptance_without_the_job_is_caught_at_acceptance(self):
        ref = self.broken_chain()
        target = offers(self.c, ref)["offers"][0]
        replacement_dep = next(l["departure_id"] for l in target["legs"] if l["departure_id"])
        Departure.objects.filter(pk=replacement_dep).update(status="cancelled")      # no job run
        r = accept(self.c, ref, target["id"])
        self.assertEqual((r.status_code, r.json()["code"]), (409, "offer_outdated"))
        self.assertEqual(ReplacementOffer.objects.get(pk=target["id"]).status, "invalidated")
        self.assertEqual(Booking.objects.get(reference=ref).legs.filter(status="replaced").count(), 0)

    def test_price_change_after_offer_is_caught(self):
        ref = self.broken_chain()
        target = offers(self.c, ref)["offers"][0]
        from apps.transport.models import Fare
        Fare.objects.filter(route__code="DR1").update(price=Decimal("9.99"))
        r = accept(self.c, ref, target["id"])
        self.assertEqual((r.status_code, r.json()["code"]), (409, "offer_outdated"))
        self.assertEqual(Booking.objects.get(reference=ref).total_amount, Booking.objects.get(reference=ref).total_amount)

    def test_clearing_the_delay_invalidates_offers_and_keeps_the_original_itinerary(self):
        ref = self.broken_chain()
        target = offers(self.c, ref)["offers"][0]
        change(self.valley, dep_at("VC1", "12:00"), "delay", 0)
        self.assertEqual(offers(self.c, ref)["state"], "not_disrupted")
        r = accept(self.c, ref, target["id"])
        self.assertEqual((r.status_code, r.json()["code"]), (409, "offer_unavailable"))
        self.assertEqual(Booking.objects.get(reference=ref).legs.filter(status="booked").count(), 3)

    def test_insufficient_capacity_at_acceptance(self):
        ref = self.broken_chain()
        target = offers(self.c, ref)["offers"][0]
        for l in target["legs"]:
            if l["departure_id"]:
                d = Departure.objects.get(pk=l["departure_id"])
                Departure.objects.filter(pk=d.pk).update(places_taken=d.capacity)
        r = accept(self.c, ref, target["id"])
        self.assertEqual((r.status_code, r.json()["code"]), (409, "no_capacity"))
        b = Booking.objects.get(reference=ref)
        self.assertEqual((b.legs.count(), b.legs.filter(status="replaced").count()), (3, 0))
        self.assertEqual(Departure.objects.get(pk=dep_at("DR1", "13:10").pk).places_taken, 1)  # original reservation intact

    def test_cannot_accept_after_cancelling_the_booking(self):
        ref = self.broken_chain()
        target = offers(self.c, ref)["offers"][0]
        self.c.post(f"/api/bookings/{ref}/cancel/", {}, content_type="application/json")
        r = accept(self.c, ref, target["id"])
        self.assertEqual((r.status_code, r.json()["code"]), (409, "booking_not_active"))

    def test_another_passenger_cannot_see_accept_or_decline_my_offer(self):
        ref = self.broken_chain()
        target = offers(self.c, ref)["offers"][0]
        other = client_for(make_user("p2@example.com"))
        self.assertEqual(other.get(f"/api/bookings/{ref}/replacements/").status_code, 404)
        self.assertEqual(accept(other, ref, target["id"]).status_code, 404)
        self.assertEqual(other.post(f"/api/bookings/{ref}/replacements/{target['id']}/decline/").status_code, 404)
        self.assertEqual(Client().get(f"/api/bookings/{ref}/replacements/").status_code, 403)
        # an offer id from my booking used under someone else's booking is also 404
        ref2 = confirmed_booking(other, dep_at("VC1", "14:00"))
        self.assertEqual(accept(other, ref2, target["id"]).status_code, 404)
        self.assertEqual(ReplacementOffer.objects.get(pk=target["id"]).status, "proposed")

    def test_decline(self):
        ref = self.broken_chain()
        target = offers(self.c, ref)["offers"][0]
        self.assertEqual(self.c.post(f"/api/bookings/{ref}/replacements/{target['id']}/decline/").json()["status"], "declined")
        self.assertEqual(accept(self.c, ref, target["id"]).json()["code"], "offer_unavailable")


class RecoveryConcurrencyTests(TransactionTestCase):
    def setUp(self):
        demo_data.reset_transport_data(demo_data.reference_date())
        self.valley = client_for(make_operator_user("valley"))

    def run_threads(self, fns):
        return booking_tests.ConcurrencyTests.run_threads(self, fns)

    def cancelled_vc1_bookings(self, n):
        users = [make_user(f"r{i}@example.com") for i in range(n)]
        refs = [confirmed_booking(client_for(u), dep_at("VC1", "12:00")) for u in users]
        change(self.valley, dep_at("VC1", "12:00"), "cancel")
        return users, refs

    def test_two_passengers_competing_for_the_last_replacement_place(self):
        users, refs = self.cancelled_vc1_bookings(2)
        # Replacement service GL1 17:30 has exactly one place left; both passengers hold an offer for it.
        gl = dep_at("GL1", "17:30")
        Departure.objects.filter(pk=gl.pk).update(places_taken=gl.capacity - 1)
        chosen = []
        for u, ref in zip(users, refs):
            d = offers(client_for(u), ref)
            offer = next(o for o in d["offers"] if any(l["departure_id"] == gl.pk for l in o["legs"]))
            chosen.append(offer["id"])
        codes = sorted(self.run_threads([lambda u=u, r=r, o=o: accept(client_for(u), r, o).status_code for u, r, o in zip(users, refs, chosen)]))
        self.assertEqual(codes, [200, 409])
        gl.refresh_from_db()
        self.assertEqual(gl.places_taken, gl.capacity)
        self.assertEqual(Booking.objects.filter(legs__status="booked", legs__departure=gl).distinct().count(), 1)

    def test_concurrent_duplicate_acceptance_applies_once(self):
        users, refs = self.cancelled_vc1_bookings(1)
        u, ref = users[0], refs[0]
        offer = settlement(offers(client_for(u), ref), "pay")
        codes = self.run_threads([lambda: accept(client_for(u), ref, offer["id"]).status_code for _ in range(6)])
        self.assertEqual(set(codes), {200})
        self.assertEqual(PaymentAttempt.objects.filter(purpose="replacement", status="succeeded").count(), 1)
        self.assertEqual(Booking.objects.get(reference=ref).legs.filter(status="booked").count(), len(offer["legs"]))
        self.assertEqual(Booking.objects.get(reference=ref).total_amount, Decimal("7.10"))

    def test_acceptance_racing_with_cancellation_leaves_a_consistent_state(self):
        users, refs = self.cancelled_vc1_bookings(1)
        u, ref = users[0], refs[0]
        offer = offers(client_for(u), ref)["offers"][0]
        results = self.run_threads([
            lambda: accept(client_for(u), ref, offer["id"]).status_code,
            lambda: client_for(u).post(f"/api/bookings/{ref}/cancel/", {}, content_type="application/json").status_code,
        ])
        self.assertTrue(set(results) <= {200, 409}, results)
        b = Booking.objects.get(reference=ref)
        self.assertEqual(Refund.objects.filter(booking=b, key="cancel").count(), 1 if b.status == "cancelled" else 0)
        for dep in Departure.objects.filter(pk__in=[l["departure_id"] for l in offer["legs"] if l["departure_id"]] + [dep_at("VC1", "12:00").pk]):
            expected = live_places(dep) + (dep.capacity - 1 if dep.route.code == "GL1" and dep.departs_at == dep_at("GL1", "07:30").departs_at else 0)
            self.assertEqual(dep.places_taken, expected, dep)
        if b.status == "cancelled":
            self.assertEqual(Reservation.objects.filter(leg__booking=b, status__in=["held", "consumed"]).count(), 0)
