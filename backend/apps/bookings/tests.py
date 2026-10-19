"""Booking, payment and concurrency tests. All run against PostgreSQL (the only supported database)."""

import threading
import uuid
from datetime import timedelta

from django.test import Client, TestCase, TransactionTestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.core import jobs
from apps.core.models import Job
from apps.payments.models import PaymentAttempt
from apps.transport import demo_data
from apps.transport.models import Departure

from .models import Booking, Reservation
from . import services


def make_user(email="p1@example.com"):
    return User.objects.create_user(email, email, "correct-horse-42", first_name="Pat")


def client_for(user):
    c = Client()
    c.force_login(user)
    return c


def dep_at(code, hhmm, day_off=1):
    ref = demo_data.reference_date()
    return Departure.objects.get(route__code=code, departs_at=demo_data._local(ref + timedelta(days=day_off), hhmm))


def body(dep, passengers=1, total=None, from_stop="NG-BUS", to_stop="RV-BUS", names=None):
    return {
        "passengers": passengers,
        "legs": [{"departure_id": dep.pk, "from_stop": from_stop, "to_stop": to_stop}],
        "contact_email": "pat@example.com",
        "travellers": names or [f"Traveller {i}" for i in range(passengers)],
        **({"expected_total": total} if total is not None else {}),
    }


def checkout(c, payload, key=None):
    return c.post("/api/bookings/", payload, content_type="application/json", HTTP_IDEMPOTENCY_KEY=key or uuid.uuid4().hex)


def pay(c, ref, outcome="success", key=None):
    return c.post(f"/api/bookings/{ref}/pay/", {"outcome": outcome}, content_type="application/json", HTTP_IDEMPOTENCY_KEY=key or uuid.uuid4().hex)


class BookingTestBase:
    def setUp(self):
        demo_data.reset_transport_data(demo_data.reference_date())
        self.user = make_user()
        self.c = client_for(self.user)
        self.dep = dep_at("VC1", "12:00")  # 7.00 EUR per passenger NG-BUS -> RV-BUS

    def fresh(self, dep=None):
        return Departure.objects.get(pk=(dep or self.dep).pk)


class CheckoutTests(BookingTestBase, TestCase):
    def test_checkout_holds_capacity_and_snapshots_purchase(self):
        res = checkout(self.c, body(self.dep, passengers=2, total="14.00"))
        self.assertEqual(res.status_code, 201, res.content)
        b = res.json()
        self.assertEqual(b["status"], "pending_payment")
        self.assertEqual(b["total_amount"], "14.00")
        self.assertEqual(self.fresh().places_taken, 2)
        self.assertEqual(Reservation.objects.get().status, "held")
        self.assertEqual(b["legs"][0]["route_code"], "VC1")
        self.assertTrue(Job.objects.filter(kind="expire_booking").exists())

    def test_snapshot_survives_later_fare_and_policy_edits(self):
        ref = checkout(self.c, body(self.dep)).json()["reference"]
        from apps.transport.models import Fare
        Fare.objects.all().update(price=99)
        self.dep.route.policy.partial_refund_percent = 0
        self.dep.route.policy.save()
        detail = self.c.get(f"/api/bookings/{ref}/").json()
        self.assertEqual(detail["total_amount"], "7.00")
        self.assertEqual(detail["legs"][0]["unit_price"], "7.00")
        self.assertEqual(Booking.objects.get(reference=ref).legs.get().policy_partial_percent, 50)

    def test_repeated_checkout_same_key_creates_one_booking(self):
        key = uuid.uuid4().hex
        a = checkout(self.c, body(self.dep), key)
        b = checkout(self.c, body(self.dep), key)
        self.assertEqual((a.status_code, b.status_code), (201, 200))
        self.assertEqual(a.json()["reference"], b.json()["reference"])
        self.assertEqual(Booking.objects.count(), 1)
        self.assertEqual(self.fresh().places_taken, 1)

    def test_changed_price_is_rejected_with_new_total_and_holds_nothing(self):
        from apps.transport.models import Fare
        Fare.objects.filter(route=self.dep.route).update(price=8)
        res = checkout(self.c, body(self.dep, total="7.00"))
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()["code"], "offer_changed")
        self.assertEqual(res.json()["new_total"], "8.00")
        self.assertEqual(self.fresh().places_taken, 0)
        self.assertEqual(Booking.objects.count(), 0)

    def test_not_enough_places(self):
        last = dep_at("GL1", "07:30")
        res = checkout(self.c, body(last, passengers=2))
        self.assertEqual((res.status_code, res.json()["code"]), (409, "no_capacity"))
        self.assertEqual(self.fresh(last).places_taken, last.capacity - 1)

    def test_cancelled_and_departed_services_rejected(self):
        cancelled = dep_at("VC1", "10:00")
        self.assertEqual(checkout(self.c, body(cancelled)).json()["code"], "unavailable")
        self.dep.departs_at = timezone.now() - timedelta(hours=1)
        self.dep.save()
        self.assertEqual(checkout(self.c, body(self.dep)).json()["code"], "unavailable")

    def test_wrong_stop_order_and_bad_input(self):
        r = checkout(self.c, body(self.dep, from_stop="RV-BUS", to_stop="NG-BUS"))
        self.assertEqual(r.json()["code"], "invalid_leg")
        self.assertEqual(checkout(self.c, body(self.dep, passengers=2, names=["Only one"])).status_code, 400)
        self.assertEqual(self.c.post("/api/bookings/", body(self.dep), content_type="application/json").status_code, 400)  # no key

    def test_requires_login(self):
        self.assertIn(Client().get("/api/bookings/").status_code, (401, 403))
        self.assertIn(checkout(Client(), body(self.dep)).status_code, (401, 403))

    def test_failed_checkout_leaves_no_partial_state(self):
        # Force a failure after capacity was incremented: the whole transaction must roll back.
        from unittest import mock
        with mock.patch.object(services.Traveller.objects, "bulk_create", side_effect=RuntimeError("secret-internal-detail")):
            res = checkout(self.c, body(self.dep))
        self.assertEqual(res.status_code, 500)                       # sanitised: no stack trace, no internal message
        self.assertEqual(res.json()["code"], "server_error")
        self.assertNotIn("secret-internal-detail", res.content.decode())
        self.assertTrue(res.json()["request_id"])
        self.assertEqual(self.fresh().places_taken, 0)
        self.assertEqual(Booking.objects.count(), 0)
        self.assertEqual(Reservation.objects.count(), 0)


class PaymentTests(BookingTestBase, TestCase):
    def new_booking(self, passengers=1):
        return checkout(self.c, body(self.dep, passengers=passengers)).json()["reference"]

    def test_successful_payment_confirms_and_consumes(self):
        ref = self.new_booking()
        res = pay(self.c, ref)
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.json()["booking"]["status"], "confirmed")
        self.assertEqual(Reservation.objects.get().status, "consumed")
        self.assertEqual(self.fresh().places_taken, 1)
        self.assertTrue(self.c.get(f"/api/bookings/{ref}/").json()["simulated_notice"])

    def test_failed_payment_keeps_hold_and_allows_retry(self):
        ref = self.new_booking()
        r = pay(self.c, ref, "failure").json()
        self.assertEqual(r["payment"]["status"], "failed")
        self.assertEqual(r["booking"]["status"], "pending_payment")
        self.assertEqual(self.fresh().places_taken, 1)
        self.assertEqual(pay(self.c, ref, "success").json()["booking"]["status"], "confirmed")
        self.assertEqual(PaymentAttempt.objects.count(), 2)

    def test_same_key_repeat_is_replayed_not_recharged(self):
        ref = self.new_booking()
        key = uuid.uuid4().hex
        a, b = pay(self.c, ref, key=key).json(), pay(self.c, ref, key=key).json()
        self.assertFalse(a["replayed"])
        self.assertTrue(b["replayed"])
        self.assertEqual(PaymentAttempt.objects.filter(status="succeeded").count(), 1)
        self.assertEqual(PaymentAttempt.objects.count(), 1)

    def test_second_payment_with_new_key_rejected(self):
        ref = self.new_booking()
        pay(self.c, ref)
        r = pay(self.c, ref)
        self.assertEqual((r.status_code, r.json()["code"]), (409, "already_paid"))
        self.assertEqual(PaymentAttempt.objects.count(), 1)

    def test_db_forbids_two_successful_payments(self):
        from django.db import IntegrityError, transaction
        ref = self.new_booking()
        pay(self.c, ref)
        b = Booking.objects.get(reference=ref)
        with self.assertRaises(IntegrityError), transaction.atomic():
            PaymentAttempt.objects.create(booking=b, idempotency_key="other-key-1", amount=b.total_amount, currency="EUR", status="succeeded")

    def test_payment_after_expiry_rejected_and_places_released(self):
        ref = self.new_booking()
        Booking.objects.filter(reference=ref).update(expires_at=timezone.now() - timedelta(seconds=1))
        r = pay(self.c, ref)
        self.assertEqual((r.status_code, r.json()["code"]), (409, "expired"))
        self.assertEqual(self.fresh().places_taken, 0)
        self.assertEqual(Booking.objects.get(reference=ref).status, "expired")
        self.assertEqual(PaymentAttempt.objects.count(), 0)

    def test_abandon_releases_places_and_is_idempotent(self):
        ref = self.new_booking(passengers=3)
        self.assertEqual(self.fresh().places_taken, 3)
        for _ in range(2):
            r = self.c.post(f"/api/bookings/{ref}/abandon/")
            self.assertEqual(r.status_code, 200)
        self.assertEqual(self.fresh().places_taken, 0)
        self.assertEqual(r.json()["status"], "cancelled")

    def test_cannot_abandon_confirmed(self):
        ref = self.new_booking()
        pay(self.c, ref)
        self.assertEqual(self.c.post(f"/api/bookings/{ref}/abandon/").status_code, 409)


class OwnershipTests(BookingTestBase, TestCase):
    def test_other_passengers_cannot_see_or_touch_my_booking(self):
        ref = checkout(self.c, body(self.dep)).json()["reference"]
        other = client_for(make_user("p2@example.com"))
        self.assertEqual(other.get(f"/api/bookings/{ref}/").status_code, 404)
        self.assertEqual(pay(other, ref).status_code, 404)
        self.assertEqual(other.post(f"/api/bookings/{ref}/abandon/").status_code, 404)
        self.assertEqual(other.get("/api/bookings/").json()["results"], [])
        self.assertEqual(Booking.objects.get(reference=ref).status, "pending_payment")
        self.assertEqual(len(self.c.get("/api/bookings/").json()["results"]), 1)


class ExpiryWorkerTests(BookingTestBase, TestCase):
    def test_worker_expires_overdue_booking_via_durable_job(self):
        ref = checkout(self.c, body(self.dep)).json()["reference"]
        past = timezone.now() - timedelta(minutes=1)
        Booking.objects.filter(reference=ref).update(expires_at=past)
        Job.objects.update(run_at=past)
        self.assertEqual(jobs.run_pending(), 1)
        self.assertEqual(Booking.objects.get(reference=ref).status, "expired")
        self.assertEqual(self.fresh().places_taken, 0)
        self.assertEqual(Job.objects.get().status, "done")
        self.assertEqual(jobs.run_pending(), 0)  # nothing left; rerun is harmless

    def test_job_not_run_before_due(self):
        checkout(self.c, body(self.dep))
        self.assertEqual(jobs.run_pending(), 0)

    def test_restart_recovers_job_abandoned_mid_run(self):
        ref = checkout(self.c, body(self.dep)).json()["reference"]
        past = timezone.now() - timedelta(minutes=5)
        Booking.objects.filter(reference=ref).update(expires_at=past)
        # Simulate a worker that claimed the job and then died: status running, stale lock.
        Job.objects.update(run_at=past, status="running", locked_at=past, attempts=1)
        self.assertEqual(jobs.run_pending(), 1)
        self.assertEqual(Booking.objects.get(reference=ref).status, "expired")

    def test_expiry_is_idempotent_and_ignores_paid_bookings(self):
        ref = checkout(self.c, body(self.dep)).json()["reference"]
        pay(self.c, ref)
        b = Booking.objects.get(reference=ref)
        self.assertFalse(services.expire_booking(b.pk, now=timezone.now() + timedelta(days=1)))
        self.assertEqual(self.fresh().places_taken, 1)

    def test_sweep_expires_overdue_without_job_row(self):
        ref = checkout(self.c, body(self.dep)).json()["reference"]
        Job.objects.all().delete()
        Booking.objects.filter(reference=ref).update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(services.expire_due_bookings(), 1)
        self.assertEqual(self.fresh().places_taken, 0)


class ConcurrencyTests(TransactionTestCase):
    """Real threads, real PostgreSQL connections, real row locks."""

    def setUp(self):
        demo_data.reset_transport_data(demo_data.reference_date())

    def run_threads(self, fns):
        from django.db import connection
        results = [None] * len(fns)

        def wrap(i, fn):
            try:
                results[i] = fn()
            finally:
                connection.close()

        barrier = threading.Barrier(len(fns))
        ts = [threading.Thread(target=lambda i=i, f=f: (barrier.wait(), wrap(i, f))) for i, f in enumerate(fns)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        return results

    def test_two_passengers_competing_for_last_place(self):
        last = dep_at("GL1", "07:30")  # exactly one place left
        users = [make_user(f"u{i}@example.com") for i in range(4)]
        fns = [lambda u=u: checkout(client_for(u), body(last, from_stop="NG-BUS", to_stop="RV-BUS")).status_code for u in users]
        codes = sorted(self.run_threads(fns))
        self.assertEqual(codes, [201, 409, 409, 409])
        last.refresh_from_db()
        self.assertEqual(last.places_taken, last.capacity)
        self.assertEqual(Booking.objects.count(), 1)

    def test_same_idempotency_key_concurrently_creates_one_booking(self):
        dep = dep_at("VC1", "12:00")
        u = make_user()
        key = uuid.uuid4().hex
        fns = [lambda: checkout(client_for(u), body(dep), key).status_code for _ in range(5)]
        codes = self.run_threads(fns)
        self.assertEqual(sorted(set(codes)) , [200, 201])
        self.assertEqual(codes.count(201), 1)
        self.assertEqual(Booking.objects.count(), 1)
        dep.refresh_from_db()
        self.assertEqual(dep.places_taken, 1)

    def test_concurrent_payments_charge_once(self):
        dep = dep_at("VC1", "12:00")
        u = make_user()
        ref = checkout(client_for(u), body(dep)).json()["reference"]
        fns = [lambda: pay(client_for(u), ref).status_code for _ in range(5)]  # five different keys
        codes = sorted(self.run_threads(fns))
        self.assertEqual(codes, [200, 409, 409, 409, 409])
        self.assertEqual(PaymentAttempt.objects.filter(status="succeeded").count(), 1)
        self.assertEqual(PaymentAttempt.objects.count(), 1)

    def test_pay_races_with_expiry_never_leaves_inconsistent_state(self):
        dep = dep_at("VC1", "12:00")
        u = make_user()
        ref = checkout(client_for(u), body(dep)).json()["reference"]
        b = Booking.objects.get(reference=ref)
        Booking.objects.filter(pk=b.pk).update(expires_at=timezone.now() + timedelta(milliseconds=50))
        fns = [lambda: pay(client_for(u), ref).status_code, lambda: services.expire_booking(b.pk, now=timezone.now() + timedelta(seconds=1))]
        self.run_threads(fns)
        b.refresh_from_db()
        dep.refresh_from_db()
        if b.status == "confirmed":
            self.assertEqual(dep.places_taken, 1)
        else:
            self.assertEqual(b.status, "expired")
            self.assertEqual(dep.places_taken, 0)
            self.assertEqual(PaymentAttempt.objects.filter(status="succeeded").count(), 0)


class ResetTests(BookingTestBase, TestCase):
    def test_demo_reset_succeeds_when_bookings_exist(self):
        ref = checkout(self.c, body(self.dep)).json()["reference"]
        pay(self.c, ref)
        demo_data.reset_transport_data(demo_data.reference_date())
        self.assertEqual(Booking.objects.count(), 0)
        self.assertEqual(PaymentAttempt.objects.count(), 0)
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())  # accounts are kept
        self.assertEqual(Departure.objects.filter(places_taken__gt=0).count(), 2)  # only the seeded scenarios


def pick_chain(client, origin, destination, modes, hhmm="11:00", passengers=1):
    """Find an itinerary with the given mode sequence via the real search API; return (itinerary, checkout body)."""
    ref = demo_data.reference_date()
    day = (ref + timedelta(days=1)).isoformat()
    res = client.get("/api/search/", {"origin": origin, "destination": destination, "depart_after": f"{day}T{hhmm}", "passengers": passengers})
    it = next(r for r in res.json()["results"] if [l["mode"] for l in r["legs"]] == modes)
    payload = {
        "passengers": passengers, "legs": it["selection"], "expected_total": it["total_price"],
        "contact_email": "pat@example.com", "travellers": [f"T{i}" for i in range(passengers)],
    }
    return it, payload


class MultimodalBookingTests(BookingTestBase, TestCase):
    def test_bookable_bus_train_taxi_itinerary(self):
        it, payload = pick_chain(self.c, "NG-BUS", "PM-MARINA", ["bus", "train", "taxi"], passengers=2)
        bus, train = [Departure.objects.get(pk=l["departure_id"]) for l in it["legs"][:2]]
        res = checkout(self.c, payload)
        self.assertEqual(res.status_code, 201, res.content)
        b = res.json()
        self.assertEqual([l["mode"] for l in b["legs"]], ["bus", "train", "taxi"])
        self.assertEqual(b["total_amount"], it["total_price"])
        self.assertEqual(b["legs"][2]["price_basis"], "vehicle")
        self.assertEqual((self.fresh(bus).places_taken, self.fresh(train).places_taken), (2, 2))
        self.assertEqual(Reservation.objects.count(), 2)  # taxi has no capacity pool => no reservation
        paid = pay(self.c, b["reference"]).json()["booking"]
        self.assertEqual(paid["status"], "confirmed")
        self.assertEqual(set(Reservation.objects.values_list("status", flat=True)), {"consumed"})
        # Expiring/abandoning an unpaid multimodal booking returns places on every leg.

    def test_abandon_releases_every_leg(self):
        it, payload = pick_chain(self.c, "NG-BUS", "PM-MARINA", ["bus", "train", "taxi"])
        ref = checkout(self.c, payload).json()["reference"]
        self.c.post(f"/api/bookings/{ref}/abandon/")
        for l in it["legs"][:2]:
            self.assertEqual(Departure.objects.get(pk=l["departure_id"]).places_taken, 0)

    def test_second_leg_full_means_nothing_is_reserved_on_first_leg(self):
        it, payload = pick_chain(self.c, "NG-BUS", "PM-MARINA", ["bus", "train", "taxi"])
        bus, train = [Departure.objects.get(pk=l["departure_id"]) for l in it["legs"][:2]]
        Departure.objects.filter(pk=train.pk).update(places_taken=train.capacity)
        res = checkout(self.c, payload)
        self.assertEqual((res.status_code, res.json()["code"]), (409, "no_capacity"))
        self.assertEqual(self.fresh(bus).places_taken, 0)
        self.assertEqual((Booking.objects.count(), Reservation.objects.count()), (0, 0))

    def test_delay_after_search_breaks_connection_at_checkout(self):
        it, payload = pick_chain(self.c, "NG-BUS", "PM-MARINA", ["bus", "train", "taxi"])
        bus = Departure.objects.get(pk=it["legs"][0]["departure_id"])
        Departure.objects.filter(pk=bus.pk).update(status="delayed", delay_minutes=90)
        res = checkout(self.c, payload)
        self.assertEqual((res.status_code, res.json()["code"]), (409, "connection_missed"))
        self.assertEqual(self.fresh(bus).places_taken, 0)

    def test_taxi_leg_snapshot_survives_offer_edit(self):
        from apps.transport.models import TaxiOffer
        it, payload = pick_chain(self.c, "NG-BUS", "PM-MARINA", ["bus", "train", "taxi"])
        ref = checkout(self.c, payload).json()["reference"]
        TaxiOffer.objects.all().update(price=99)
        self.assertEqual(self.c.get(f"/api/bookings/{ref}/").json()["legs"][2]["unit_price"], "14.00")

    def test_checkout_input_must_pick_exactly_one_kind(self):
        bad = body(self.dep)
        bad["legs"][0]["taxi_offer_id"] = 1
        self.assertEqual(checkout(self.c, bad).status_code, 400)


class MultimodalConcurrencyTests(TransactionTestCase):
    def setUp(self):
        demo_data.reset_transport_data(demo_data.reference_date())

    def run_threads(self, fns):
        return ConcurrencyTests.run_threads(self, fns)

    def test_concurrent_multi_leg_checkouts_do_not_deadlock_or_oversell(self):
        users = [make_user(f"m{i}@example.com") for i in range(8)]
        it, payload = pick_chain(client_for(users[0]), "NG-BUS", "PM-MARINA", ["bus", "train", "taxi"])
        bus, train = [Departure.objects.get(pk=l["departure_id"]) for l in it["legs"][:2]]
        Departure.objects.filter(pk=bus.pk).update(places_taken=bus.capacity - 3)  # only 3 places left on leg 1
        codes = sorted(self.run_threads([lambda u=u: checkout(client_for(u), payload).status_code for u in users]))
        self.assertEqual(codes, [201] * 3 + [409] * 5)
        bus.refresh_from_db(); train.refresh_from_db()
        self.assertEqual(bus.places_taken, bus.capacity)
        self.assertEqual(train.places_taken, 3)  # losers left nothing behind on the train


# ------------------------------------------------------------------------------------ Stage 5: cancellation

from decimal import Decimal  # noqa: E402

from apps.payments.models import Refund  # noqa: E402

from .models import BookingLeg  # noqa: E402


def confirmed_booking(c, dep, passengers=1, from_stop="NG-BUS", to_stop="RV-BUS"):
    ref = checkout(c, body(dep, passengers=passengers, from_stop=from_stop, to_stop=to_stop)).json()["reference"]
    assert pay(c, ref).status_code == 200
    return ref


def depart_in(ref, hours):
    """Move the purchase *snapshot* so cancellation rules can be tested at any distance from departure."""
    BookingLeg.objects.filter(booking__reference=ref).update(departs_at=timezone.now() + timedelta(hours=hours))


class CancellationTests(BookingTestBase, TestCase):
    def cancel(self, ref, c=None, **body):
        return (c or self.c).post(f"/api/bookings/{ref}/cancel/", body, content_type="application/json")

    def refund_for(self, hours, passengers=1):
        ref = confirmed_booking(self.c, self.dep, passengers)
        depart_in(ref, hours)
        return ref, Decimal(self.c.get(f"/api/bookings/{ref}/cancellation/").json()["total_refund"])

    def test_refund_tiers_follow_the_snapshotted_policy(self):
        # Standard policy: >=24h full, >=2h 50%, otherwise nothing. Fare 7.00 per passenger.
        self.assertEqual(self.refund_for(48)[1], Decimal("7.00"))
        self.assertEqual(self.refund_for(5)[1], Decimal("3.50"))
        self.assertEqual(self.refund_for(2.01)[1], Decimal("3.50"))
        self.assertEqual(self.refund_for(1.5)[1], Decimal("0.00"))
        self.assertEqual(self.refund_for(-1)[1], Decimal("0.00"))      # already departed

    def test_tier_boundaries_are_inclusive(self):
        ref = confirmed_booking(self.c, self.dep)
        b, leg = Booking.objects.get(reference=ref), BookingLeg.objects.get(booking__reference=ref)
        total = lambda hours_before: services.refund_quote(b, now=leg.departs_at - timedelta(hours=hours_before))["total"]
        self.assertEqual(total(24), Decimal("7.00"))
        self.assertEqual(total(23.99), Decimal("3.50"))
        self.assertEqual(total(2), Decimal("3.50"))
        self.assertEqual(total(1.99), Decimal("0.00"))

    def test_refund_rounds_half_up_to_cents(self):
        ref = confirmed_booking(self.c, self.dep, passengers=1)
        depart_in(ref, 5)
        BookingLeg.objects.filter(booking__reference=ref).update(unit_price=Decimal("7.05"))  # 50% = 3.525
        self.assertEqual(self.c.get(f"/api/bookings/{ref}/cancellation/").json()["total_refund"], "3.53")

    def test_cancel_refunds_frees_places_and_records_everything(self):
        ref = confirmed_booking(self.c, self.dep, passengers=2)
        depart_in(ref, 48)
        res = self.cancel(ref)
        self.assertEqual(res.status_code, 200, res.content)
        b = res.json()
        self.assertEqual((b["status"], b["refunds"][0]["amount"], b["refunds"][0]["status"]), ("cancelled", "14.00", "completed"))
        self.assertEqual(self.fresh().places_taken, 0)
        self.assertEqual(Reservation.objects.get().status, "released")
        from apps.core.models import AuditRecord
        from apps.notifications.models import Notification
        self.assertTrue(AuditRecord.objects.filter(action="booking.cancelled", object_id=ref).exists())
        self.assertEqual(Notification.objects.filter(user=self.user, kind="booking_cancelled").count(), 1)

    def test_repeated_cancellation_never_refunds_twice(self):
        ref = confirmed_booking(self.c, self.dep)
        depart_in(ref, 48)
        for _ in range(3):
            self.assertEqual(self.cancel(ref).status_code, 200)
        self.assertEqual(Refund.objects.filter(booking__reference=ref).count(), 1)
        self.assertEqual(self.fresh().places_taken, 0)

    def test_db_forbids_a_second_cancel_refund(self):
        from django.db import IntegrityError, transaction
        ref = confirmed_booking(self.c, self.dep)
        self.cancel(ref)
        b = Booking.objects.get(reference=ref)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Refund.objects.create(booking=b, key="cancel", reason="passenger_cancel", amount=1, currency="EUR")

    def test_refund_changed_between_quote_and_cancel_is_rejected(self):
        ref = confirmed_booking(self.c, self.dep)
        depart_in(ref, 48)
        quote = self.c.get(f"/api/bookings/{ref}/cancellation/").json()["total_refund"]
        depart_in(ref, 5)  # time passes: the tier drops
        res = self.cancel(ref, expected_refund=quote)
        self.assertEqual((res.status_code, res.json()["code"]), (409, "refund_changed"))
        self.assertEqual(Booking.objects.get(reference=ref).status, "confirmed")
        self.assertEqual(Refund.objects.count(), 0)

    def test_multileg_refund_uses_each_legs_own_policy(self):
        it, payload = pick_chain(self.c, "NG-BUS", "PM-MARINA", ["bus", "train", "taxi"])
        ref = checkout(self.c, payload).json()["reference"]
        pay(self.c, ref)
        # 5h before: bus/train (standard) 50%, taxi (free until 1h before) 100%.
        BookingLeg.objects.filter(booking__reference=ref).update(departs_at=timezone.now() + timedelta(hours=5))
        q = self.c.get(f"/api/bookings/{ref}/cancellation/").json()
        self.assertEqual([l["percent"] for l in q["lines"]], [50, 50, 100])
        expected = Decimal(it["legs"][0]["unit_price"]) / 2 + Decimal(it["legs"][1]["unit_price"]) / 2 + Decimal("14.00")
        self.assertEqual(Decimal(q["total_refund"]), expected.quantize(Decimal("0.01")))

    def test_cancelling_an_unpaid_reservation_releases_places_without_refund(self):
        ref = checkout(self.c, body(self.dep)).json()["reference"]
        self.assertEqual(self.cancel(ref).json()["status"], "cancelled")
        self.assertEqual(self.fresh().places_taken, 0)
        self.assertEqual(Refund.objects.count(), 0)

    def test_nobody_else_can_cancel_my_booking(self):
        ref = confirmed_booking(self.c, self.dep)
        other = client_for(make_user("p2@example.com"))
        self.assertEqual(self.cancel(ref, other).status_code, 404)
        self.assertEqual(other.get(f"/api/bookings/{ref}/cancellation/").status_code, 404)
        self.assertEqual(Booking.objects.get(reference=ref).status, "confirmed")

    def test_expired_booking_cannot_be_cancelled(self):
        ref = checkout(self.c, body(self.dep)).json()["reference"]
        Booking.objects.filter(reference=ref).update(expires_at=timezone.now() - timedelta(seconds=1))
        services.expire_due_bookings()
        self.assertEqual(self.cancel(ref).status_code, 409)

    def test_cancelled_places_become_searchable_again(self):
        last = dep_at("GL1", "07:30")  # one place left
        ref = confirmed_booking(self.c, last)
        search = lambda: [r for r in client_for(self.user).get("/api/search/", {"origin": "NG-BUS", "destination": "RV-BUS", "depart_after": f"{demo_data.reference_date() + timedelta(days=1)}T07:00"}).json()["results"] if r["legs"][0]["route_code"] == "GL1" and r["transfers"] == 0]
        self.assertFalse([r for r in search() if r["legs"][0]["departure_id"] == last.pk])
        self.cancel(ref)
        self.assertTrue([r for r in search() if r["legs"][0]["departure_id"] == last.pk])


class CancellationConcurrencyTests(TransactionTestCase):
    def setUp(self):
        demo_data.reset_transport_data(demo_data.reference_date())

    def test_concurrent_cancellations_refund_once(self):
        dep = dep_at("VC1", "12:00")
        u = make_user()
        ref = confirmed_booking(client_for(u), dep)
        fns = [lambda: client_for(u).post(f"/api/bookings/{ref}/cancel/", {}, content_type="application/json").status_code for _ in range(6)]
        codes = ConcurrencyTests.run_threads(self, fns)
        self.assertEqual(set(codes), {200})
        self.assertEqual(Refund.objects.filter(booking__reference=ref).count(), 1)
        dep.refresh_from_db()
        self.assertEqual(dep.places_taken, 0)
