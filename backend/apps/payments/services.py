"""Durable simulated charges and refunds. No real provider or card data."""
from decimal import Decimal

from django.db import transaction, IntegrityError
from django.db.models import Sum
from django.utils import timezone

from apps.bookings.models import Booking
from apps.bookings.services import BookingError, confirm_booking, expire_booking
from apps.core import jobs
from apps.core.models import AuditRecord
from .models import PaymentAttempt, Refund

OUTCOMES = ("success", "failure", "pending")
FAILURE_REASON = "Simulated card decline (demonstration)."


def begin_attempt(booking, key, amount, purpose, offer=None):
    """Caller locks the booking. Commit this record before executing a simulated charge."""
    prior = PaymentAttempt.objects.filter(booking=booking, idempotency_key=key).first()
    if prior:
        if prior.purpose != purpose or prior.offer_id != (offer.pk if offer else None):
            raise BookingError("payment_key_conflict", "This payment key belongs to another operation.")
        return prior, True
    if PaymentAttempt.objects.filter(booking=booking, status__in=["created", "pending"]).exists():
        raise BookingError("payment_pending", "A payment outcome is pending. Check that attempt before paying again.")
    return PaymentAttempt.objects.create(booking=booking, idempotency_key=key, amount=amount,
                                         currency=booking.currency, purpose=purpose, offer=offer), False


def record_outcome(attempt, outcome, *, reconcile=False):
    """Caller locks booking then attempt. Terminal outcomes are immutable."""
    if attempt.status in ("succeeded", "failed") or (attempt.status == "pending" and not reconcile):
        return attempt
    attempt.status = {"success": "succeeded", "failure": "failed", "pending": "pending"}[outcome]
    attempt.failure_reason = FAILURE_REASON if outcome == "failure" else ""
    attempt.save(update_fields=["status", "failure_reason"])
    AuditRecord.objects.create(actor=attempt.booking.user, action=f"payment.{attempt.status}", object_type="booking",
                               object_id=attempt.booking.reference, detail={"amount": str(attempt.amount), "simulated": True})
    return attempt


def request_refund(booking, *, key, amount, reason, detail=None, payment_attempt=None):
    """Reserve refundable money once. Caller locks booking; pending requests count against the cap."""
    prior = Refund.objects.filter(booking=booking, key=key).first()
    if prior:
        return prior
    amount = Decimal(amount)
    captured = PaymentAttempt.objects.filter(booking=booking, status="succeeded")
    reserved = Refund.objects.filter(booking=booking).exclude(status="failed")
    available = (captured.aggregate(s=Sum("amount"))["s"] or Decimal("0")) - (reserved.aggregate(s=Sum("amount"))["s"] or Decimal("0"))
    if payment_attempt is not None:
        own_reserved = reserved.filter(payment_attempt=payment_attempt).aggregate(s=Sum("amount"))["s"] or Decimal("0")
        own_captured = payment_attempt.amount if payment_attempt.status == "succeeded" else Decimal("0")
        available = min(available, own_captured - own_reserved)
    if amount < 0 or amount > available:
        raise BookingError("refund_limit", "The refund exceeds the remaining captured payment.")
    refund = Refund.objects.create(booking=booking, key=key, amount=amount, currency=booking.currency,
                                   reason=reason, detail=detail or {}, payment_attempt=payment_attempt)
    jobs.enqueue("process_refund", {"refund_id": refund.pk}, dedupe_key=f"refund:{refund.pk}")
    return refund


def process_refund(refund_id, outcome="success"):
    booking_id = Refund.objects.values_list("booking_id", flat=True).get(pk=refund_id)
    with transaction.atomic():
        booking = Booking.objects.select_for_update().get(pk=booking_id)
        refund = Refund.objects.select_for_update().get(pk=refund_id)
        if refund.status == Refund.Status.COMPLETED:
            return refund
        # Failed requests release their reservation; recheck the capture cap on retry.
        if refund.status == Refund.Status.FAILED:
            total = PaymentAttempt.objects.filter(booking=booking, status="succeeded").aggregate(s=Sum("amount"))["s"] or Decimal("0")
            reserved = Refund.objects.filter(booking=booking).exclude(status="failed").exclude(pk=refund.pk).aggregate(s=Sum("amount"))["s"] or Decimal("0")
            available = total - reserved
            if refund.payment_attempt_id:
                own = Refund.objects.filter(booking=booking, payment_attempt_id=refund.payment_attempt_id).exclude(status="failed").exclude(pk=refund.pk).aggregate(s=Sum("amount"))["s"] or Decimal("0")
                available = min(available, refund.payment_attempt.amount - own)
            if refund.amount > available:
                raise BookingError("refund_limit", "The refund exceeds the remaining captured payment.")
        refund.status = {"success": "completed", "failure": "failed", "pending": "pending"}[outcome]
        refund.failure_reason = "Simulated refund failure. Retry this refund operation." if outcome == "failure" else ""
        refund.completed_at = timezone.now() if outcome == "success" else None
        refund.save(update_fields=["status", "failure_reason", "completed_at"])
        AuditRecord.objects.create(actor=booking.user, action=f"refund.{refund.status}", object_type="booking",
                                   object_id=booking.reference, detail={"refund": refund.pk, "amount": str(refund.amount)})
        return refund


@jobs.handler("process_refund")
def _refund_job(refund_id):
    # An explicitly failed simulator outcome needs a visible passenger retry.
    if Refund.objects.get(pk=refund_id).status != Refund.Status.FAILED:
        process_refund(refund_id)


def compensate(attempt):
    """A successful charge whose booking commit failed is refunded independently of fare policy."""
    refund = request_refund(attempt.booking, key=f"compensate:{attempt.pk}", amount=attempt.amount,
                            reason=Refund.Reason.COMMIT_FAILED, payment_attempt=attempt,
                            detail={"payment": attempt.pk})
    attempt.compensated = True
    attempt.save(update_fields=["compensated"])
    return refund


def pay_booking(*, user, reference, idempotency_key, outcome, reconcile=False):
    booking = Booking.objects.filter(reference=reference, user=user).first()
    if booking is None:
        return None, False
    expire_booking(booking.pk)
    with transaction.atomic():
        booking = Booking.objects.select_for_update().get(pk=booking.pk)
        prior = PaymentAttempt.objects.filter(booking=booking, idempotency_key=idempotency_key).first()
        if prior is None:
            if reconcile:
                raise BookingError("payment_not_found", "The original payment attempt was not found.")
            if booking.status == Booking.Status.CONFIRMED:
                raise BookingError("already_paid", "This booking is already paid.")
            if booking.status == Booking.Status.EXPIRED:
                raise BookingError("expired", "The reservation expired. Please search again.")
            if booking.status != Booking.Status.PENDING_PAYMENT:
                raise BookingError("not_payable", "This booking can no longer be paid.")
        attempt, replayed = begin_attempt(booking, idempotency_key, booking.total_amount, PaymentAttempt.Purpose.INITIAL)
    # The attempt exists durably before any outcome is recorded.
    with transaction.atomic():
        booking = Booking.objects.select_for_update().get(pk=booking.pk)
        attempt = PaymentAttempt.objects.select_for_update().get(pk=attempt.pk)
        record_outcome(attempt, outcome, reconcile=reconcile)
        if attempt.status != "succeeded" or attempt.compensated or booking.status == Booking.Status.CONFIRMED:
            return attempt, replayed
        try:
            with transaction.atomic():
                if booking.status != Booking.Status.PENDING_PAYMENT or booking.expires_at <= timezone.now():
                    raise BookingError("expired", "The reservation expired before confirmation.")
                from apps.planning.services import build_itinerary, OfferError
                from apps.bookings.services import _lock_departures
                from apps.bookings.models import Reservation
                selection = []
                for leg in booking.legs.filter(status="booked"):
                    item = {"from_stop": leg.from_stop.code, "to_stop": leg.to_stop.code}
                    if leg.departure_id:
                        item["departure_id"] = leg.departure_id
                    else:
                        from datetime import timedelta
                        item.update(taxi_offer_id=leg.taxi_offer_id, ready_at=(leg.departs_at - timedelta(minutes=leg.taxi_offer.pickup_wait_min)).isoformat())
                    selection.append(item)
                _lock_departures({s["departure_id"] for s in selection if "departure_id" in s})
                try:
                    build_itinerary(selection, booking.passengers, timezone.now(), wheelchair_required=booking.wheelchair_required)
                except OfferError as exc:
                    raise BookingError(exc.code, exc.message) from exc
                confirm_booking(booking, timezone.now())
        except (BookingError, IntegrityError):
            from apps.bookings.services import _free_places
            from apps.bookings.models import Reservation
            if booking.status == Booking.Status.PENDING_PAYMENT:
                _free_places(booking, Reservation.Status.RELEASED, Booking.Status.EXPIRED, now=timezone.now(), action="booking.commit_failed")
            compensate(attempt)
        return attempt, replayed
