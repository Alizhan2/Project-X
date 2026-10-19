"""Simulated payment processing. No real money, no card data."""

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.bookings.models import Booking
from apps.bookings.services import BookingError, confirm_booking, expire_booking
from apps.core.models import AuditRecord

from .models import PaymentAttempt

OUTCOMES = ("success", "failure")
FAILURE_REASON = "Simulated card decline (demonstration)."


def pay_booking(*, user, reference, idempotency_key, outcome):
    """Run one simulated payment attempt for a booking owned by `user`.

    Returns (attempt, replayed). Guarantees:
      * same idempotency key => same attempt returned, nothing re-processed (no double charge);
      * a different key after success => rejected (409 `already_paid`);
      * paying after the reservation expired => rejected (409 `expired`) and the places are released;
      * the booking row lock serialises concurrent attempts; a partial unique index backs it up in the DB.
    """
    booking = Booking.objects.filter(reference=reference, user=user).first()
    if booking is None:
        return None, False  # caller maps to 404 (also for other users' bookings)
    expire_booking(booking.pk)  # own transaction; commits the release before we may reject below
    try:
        with transaction.atomic():
            booking = Booking.objects.select_for_update().get(pk=booking.pk)
            prior = PaymentAttempt.objects.filter(booking=booking, idempotency_key=idempotency_key).first()
            if prior:
                return prior, True
            if booking.status == Booking.Status.CONFIRMED:
                raise BookingError("already_paid", "This booking is already paid.")
            if booking.status == Booking.Status.EXPIRED:
                raise BookingError("expired", "The reservation expired. Please search again.")
            if booking.status != Booking.Status.PENDING_PAYMENT:
                raise BookingError("not_payable", "This booking can no longer be paid.")
            now = timezone.now()
            if booking.expires_at <= now:
                raise BookingError("expired", "The reservation expired. Please search again.")
            attempt = PaymentAttempt(
                booking=booking, idempotency_key=idempotency_key, amount=booking.total_amount, currency=booking.currency
            )
            if outcome == "success":
                attempt.status = PaymentAttempt.Status.SUCCEEDED
                attempt.save()
                confirm_booking(booking, now)
            else:
                attempt.status = PaymentAttempt.Status.FAILED
                attempt.failure_reason = FAILURE_REASON
                attempt.save()
            AuditRecord.objects.create(
                actor=user, action=f"payment.{attempt.status}", object_type="booking", object_id=booking.reference,
                detail={"amount": str(attempt.amount), "simulated": True},
            )
            return attempt, False
    except IntegrityError:
        prior = PaymentAttempt.objects.filter(booking=booking, idempotency_key=idempotency_key).first()
        if prior:
            return prior, True
        raise BookingError("already_paid", "This booking is already paid.")
