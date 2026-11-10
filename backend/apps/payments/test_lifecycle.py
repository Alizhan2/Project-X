"""Money remains durable through unknown outcomes and failed booking commits."""
import uuid
from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.test import TestCase
from django.utils import timezone
from apps.bookings import tests as helpers
from apps.bookings.models import Booking
from apps.payments.models import PaymentAttempt, Refund
from apps.payments.services import process_refund, request_refund
from apps.bookings.services import BookingError
from django.db import transaction


class PaymentLifecycleTests(helpers.BookingTestBase, TestCase):
    def reserve(self):
        return helpers.checkout(self.c, helpers.body(self.dep)).json()["reference"]

    def resolve(self, ref, key, outcome="success"):
        return self.c.post(f"/api/bookings/{ref}/pay/reconcile/", {"outcome": outcome},
                           content_type="application/json", HTTP_IDEMPOTENCY_KEY=key)

    def test_unknown_blocks_another_charge_and_reconciles_same_attempt_once(self):
        ref, key = self.reserve(), uuid.uuid4().hex
        pending = helpers.pay(self.c, ref, "pending", key)
        self.assertEqual(pending.json()["payment"]["status"], "pending")
        self.assertEqual(helpers.pay(self.c, ref).json()["code"], "payment_pending")
        self.assertEqual(helpers.pay(self.c, ref, "success", key).json()["payment"]["status"], "pending")
        result = self.resolve(ref, key)
        self.assertEqual(result.json()["booking"]["status"], "confirmed")
        self.resolve(ref, key)
        self.assertEqual(PaymentAttempt.objects.filter(booking__reference=ref).count(), 1)
        self.assertEqual(Refund.objects.count(), 0)

    def test_late_success_after_expiry_is_refunded_without_reviving_booking(self):
        ref, key = self.reserve(), uuid.uuid4().hex
        helpers.pay(self.c, ref, "pending", key)
        Booking.objects.filter(reference=ref).update(expires_at=timezone.now() - timedelta(seconds=1))
        result = self.resolve(ref, key)
        self.assertEqual(result.json()["booking"]["status"], "expired")
        self.assertTrue(result.json()["payment"]["compensated"])
        self.assertEqual(Refund.objects.get().amount, Decimal("7.00"))
        self.assertEqual(Refund.objects.get().status, "requested")
        self.resolve(ref, key)
        self.assertEqual(Refund.objects.count(), 1)

    def test_capture_survives_confirmation_failure_and_gets_full_compensation(self):
        ref = self.reserve()
        with mock.patch("apps.payments.services.confirm_booking", side_effect=BookingError("commit_failed", "Commit failed")):
            response = helpers.pay(self.c, ref)
        self.assertEqual(response.json()["booking"]["status"], "expired")
        self.assertEqual(PaymentAttempt.objects.get().status, "succeeded")
        self.assertEqual(Refund.objects.get().amount, PaymentAttempt.objects.get().amount)

    def test_failed_refund_can_be_retried_without_creating_another_refund(self):
        ref = helpers.confirmed_booking(self.c, self.dep)
        self.c.post(f"/api/bookings/{ref}/cancel/", {}, content_type="application/json")
        refund = Refund.objects.get()
        process_refund(refund.pk, "failure")
        response = self.c.post(f"/api/bookings/{ref}/refunds/{refund.pk}/retry/", {"outcome":"success"}, content_type="application/json")
        self.assertEqual(response.json()["refunds"][0]["status"], "completed")
        process_refund(refund.pk, "success")
        self.assertEqual(Refund.objects.count(), 1)

    def test_reserved_refunds_count_against_global_and_per_charge_caps(self):
        ref = helpers.confirmed_booking(self.c, self.dep)
        booking = Booking.objects.get(reference=ref)
        attempt = PaymentAttempt.objects.get(booking=booking)
        with transaction.atomic():
            Booking.objects.select_for_update().get(pk=booking.pk)
            request_refund(booking, key="first", amount=Decimal("5"), reason=Refund.Reason.PASSENGER_CANCEL)
            with self.assertRaises(BookingError):
                request_refund(booking, key="second", amount=Decimal("3"), reason=Refund.Reason.COMMIT_FAILED, payment_attempt=attempt)

    def test_unrelated_old_refund_does_not_reduce_full_compensation_of_a_new_charge(self):
        ref = helpers.confirmed_booking(self.c, self.dep)
        booking = Booking.objects.get(reference=ref)
        old = Refund.objects.create(booking=booking, key="earlier", reason="replaced_legs", amount=Decimal("4"), currency="EUR", status="completed")
        fresh = PaymentAttempt.objects.create(booking=booking, purpose="replacement", idempotency_key=uuid.uuid4().hex,
                                               amount=Decimal("18"), currency="EUR", status="succeeded")
        from apps.payments.services import compensate
        with transaction.atomic():
            Booking.objects.select_for_update().get(pk=booking.pk)
            refund = compensate(fresh)
        self.assertEqual(refund.amount,Decimal("18"))
        process_refund(refund.pk,"failure")
        process_refund(refund.pk,"success")
        refund.refresh_from_db()
        self.assertEqual(refund.status,"completed")
        self.assertEqual(Refund.objects.count(),2)

    def test_other_passenger_cannot_reconcile_or_retry(self):
        ref, key = self.reserve(), uuid.uuid4().hex
        helpers.pay(self.c, ref, "pending", key)
        other = helpers.client_for(helpers.make_user("other@example.com"))
        self.assertEqual(other.post(f"/api/bookings/{ref}/pay/reconcile/", {"outcome":"success"}, content_type="application/json", HTTP_IDEMPOTENCY_KEY=key).status_code, 404)
