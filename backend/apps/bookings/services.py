"""Booking lifecycle: reserve → (pay, see payments.services) → confirm | expire | abandon.

Locking protocol (prevents oversell and deadlocks):
  1. Lock the *departure* rows involved, always ordered by primary key.
  2. Only then read capacity and change `places_taken`.
  3. Booking-row locks are taken before departure locks when both are needed.
Short transactions only: nothing here waits for a user.
"""

import logging
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from apps.core import jobs
from apps.core.models import AuditRecord
from apps.planning.services import OfferError, build_itinerary
from apps.transport.models import Departure

from .models import Booking, BookingLeg, Reservation, Traveller

log = logging.getLogger(__name__)


class BookingError(Exception):
    """Business-rule failure surfaced to the API as HTTP 409 with a machine-readable code."""

    def __init__(self, code, message, **extra):
        super().__init__(message)
        self.code, self.message, self.extra = code, message, extra


def _lock_departures(ids):
    # Deterministic order => two checkouts touching the same departures can never deadlock each other.
    return {d.pk: d for d in Departure.objects.select_for_update().filter(pk__in=ids).order_by("pk")}


def create_booking(*, user, selection, passengers, traveller_names, contact_email, idempotency_key, expected_total):
    """Revalidate every leg, hold capacity for all legs atomically, create a pending booking.

    Idempotent per (user, idempotency_key): a replay returns the original booking with created=False.
    """
    existing = Booking.objects.filter(user=user, idempotency_key=idempotency_key).first()
    if existing:
        return existing, False
    try:
        with transaction.atomic():
            now = timezone.now()
            locked = _lock_departures({s["departure_id"] for s in selection if s.get("departure_id") is not None})
            try:
                it = build_itinerary(selection, passengers, now)
            except OfferError as e:
                raise BookingError(e.code, e.message) from e
            if expected_total is not None and Decimal(expected_total) != it.total_price:
                raise BookingError(
                    "offer_changed", "The price changed since you searched.",
                    new_total=f"{it.total_price:.2f}", currency=it.currency,
                )
            needed = {}  # taxis have no capacity pool; only bus/train departures are reserved
            for leg in it.legs:
                if leg.departure:
                    needed[leg.departure.pk] = needed.get(leg.departure.pk, 0) + passengers
            for pk, places in needed.items():
                dep = locked[pk]  # locked + freshly read inside this transaction
                if dep.capacity - dep.places_taken < places:
                    raise BookingError("no_capacity", "Not enough places are left on one of the services.")
            for pk, places in needed.items():
                Departure.objects.filter(pk=pk).update(places_taken=F("places_taken") + places)
            booking = Booking.objects.create(
                user=user, passengers=passengers, total_amount=it.total_price, currency=it.currency,
                contact_email=contact_email, idempotency_key=idempotency_key,
                expires_at=now + timedelta(minutes=settings.RESERVATION_MINUTES),
            )
            Traveller.objects.bulk_create([Traveller(booking=booking, full_name=n) for n in traveller_names])
            for seq, leg in enumerate(it.legs):
                make_leg(booking, seq, leg, passengers, Reservation.Status.HELD)
            jobs.enqueue(
                "expire_booking", {"booking_id": booking.pk}, run_at=booking.expires_at,
                dedupe_key=f"expire_booking:{booking.pk}",
            )
            AuditRecord.objects.create(
                actor=user, action="booking.created", object_type="booking", object_id=booking.reference,
                detail={"total": str(booking.total_amount), "passengers": passengers},
            )
            return booking, True
    except IntegrityError:
        # Two concurrent requests with the same idempotency key: the loser sees the winner's booking.
        existing = Booking.objects.filter(user=user, idempotency_key=idempotency_key).first()
        if existing:
            return existing, False
        raise


def make_leg(booking, sequence, leg, passengers, reservation_status):
    """Create a BookingLeg with its purchase snapshot (and a reservation for bus/train legs). Caller holds the locks
    and has already incremented `places_taken`. Shared by checkout and replacement acceptance."""
    policy = leg.policy
    bl = BookingLeg.objects.create(
        booking=booking, sequence=sequence, departure=leg.departure, taxi_offer=leg.taxi,
        from_stop=leg.from_stop, to_stop=leg.to_stop,
        mode=leg.mode, operator_name=leg.operator_name, route_code=leg.route_code, route_name=leg.route_name,
        from_name=leg.from_stop.name, to_name=leg.to_stop.name,
        departs_at=leg.departs_at, arrives_at=leg.arrives_at, unit_price=leg.unit_price,
        price_basis=leg.price_basis, policy_name=policy.name,
        policy_full_refund_hours=policy.full_refund_hours_before,
        policy_partial_refund_hours=policy.partial_refund_hours_before,
        policy_partial_percent=policy.partial_refund_percent,
    )
    if leg.departure:
        Reservation.objects.create(leg=bl, departure=leg.departure, places=passengers, status=reservation_status)
    return bl


def _free_places(booking, reservation_status, booking_status, *, now, actor=None, action):
    """Return held places to their departures. Caller holds the booking row lock."""
    res = list(
        Reservation.objects.filter(leg__booking=booking, status__in=[Reservation.Status.HELD, Reservation.Status.CONSUMED])
        .order_by("departure_id", "pk")
    )
    locked = _lock_departures({r.departure_id for r in res})
    for r in res:
        Departure.objects.filter(pk=locked[r.departure_id].pk).update(places_taken=F("places_taken") - r.places)
        r.status = reservation_status
        r.save(update_fields=["status"])
    booking.status = booking_status
    if booking_status == Booking.Status.CANCELLED:
        booking.cancelled_at = now
    booking.save(update_fields=["status", "cancelled_at"])
    AuditRecord.objects.create(
        actor=actor, action=action, object_type="booking", object_id=booking.reference, detail={}
    )


def expire_booking(booking_id, now=None):
    """Expire a pending booking whose reservation window has passed. Idempotent. Returns True if it expired."""
    now = now or timezone.now()
    with transaction.atomic():
        booking = Booking.objects.select_for_update().get(pk=booking_id)
        if booking.status != Booking.Status.PENDING_PAYMENT or booking.expires_at > now:
            return False
        _free_places(booking, Reservation.Status.EXPIRED, Booking.Status.EXPIRED, now=now, action="booking.expired")
        return True


def expire_due_bookings(now=None):
    now = now or timezone.now()
    ids = list(
        Booking.objects.filter(status=Booking.Status.PENDING_PAYMENT, expires_at__lte=now).values_list("pk", flat=True)
    )
    return sum(1 for i in ids if expire_booking(i, now))


def abandon_booking(booking_id, actor):
    """Passenger gives up before paying: release the held places."""
    with transaction.atomic():
        booking = Booking.objects.select_for_update().get(pk=booking_id)
        if booking.status == Booking.Status.CANCELLED:
            return booking  # idempotent
        if booking.status != Booking.Status.PENDING_PAYMENT:
            raise BookingError("not_pending", "Only an unpaid reservation can be abandoned here.")
        _free_places(booking, Reservation.Status.RELEASED, Booking.Status.CANCELLED, now=timezone.now(), actor=actor, action="booking.abandoned")
        return booking


def confirm_booking(booking, now):
    """Mark paid reservations consumed. Caller holds the booking row lock and has verified payment succeeded."""
    Reservation.objects.filter(leg__booking=booking, status=Reservation.Status.HELD).update(status=Reservation.Status.CONSUMED)
    booking.status = Booking.Status.CONFIRMED
    booking.confirmed_at = now
    booking.save(update_fields=["status", "confirmed_at"])


@jobs.handler("expire_booking")
def _expire_job(booking_id):
    expire_booking(booking_id)


def free_pending_booking(booking_id, reason):
    """Release an unpaid booking because of something outside the passenger's control (e.g. cancelled service)."""
    with transaction.atomic():
        booking = Booking.objects.select_for_update().get(pk=booking_id)
        if booking.status != Booking.Status.PENDING_PAYMENT:
            return False
        _free_places(booking, Reservation.Status.RELEASED, Booking.Status.CANCELLED, now=timezone.now(), action=f"booking.{reason}")
        return True


# ---------------------------------------------------------------------------------- cancellation & refunds

CENT = Decimal("0.01")


def leg_gross(leg):
    return leg.unit_price if leg.price_basis == "vehicle" else leg.unit_price * leg.booking.passengers


def refund_quote(booking, now=None):
    """Explicit, deterministic refund rules (docs/business-rules.md):

    per not-yet-departed leg, using the policy *snapshotted at purchase*:
      hours before departure >= full window  -> 100%;  >= partial window -> partial %;  otherwise 0%.
    Legs that already departed refund 0. If the journey is disrupted (a leg cancelled by the operator or a
    connection no longer possible), every not-yet-departed leg is refunded 100%.
    """
    from apps.disruptions.services import assess  # local import: disruptions depends on bookings

    now = now or timezone.now()
    disrupted = assess(booking).status == "broken"
    lines = []
    for leg in booking.legs.order_by("sequence"):
        if leg.status != leg.Status.BOOKED:
            continue
        gross = leg_gross(leg)
        hours = (leg.departs_at - now).total_seconds() / 3600
        if leg.departs_at <= now:
            pct, why = 0, "already departed"
        elif disrupted:
            pct, why = 100, "journey disrupted: full refund of unused legs"
        elif hours >= leg.policy_full_refund_hours:
            pct, why = 100, f"cancelled at least {leg.policy_full_refund_hours}h before departure"
        elif hours >= leg.policy_partial_refund_hours:
            pct, why = leg.policy_partial_percent, f"cancelled at least {leg.policy_partial_refund_hours}h before departure"
        else:
            pct, why = 0, "too close to departure for a refund"
        lines.append({
            "sequence": leg.sequence, "route_code": leg.route_code, "paid": gross, "percent": pct, "reason": why,
            "refund": (gross * pct / 100).quantize(CENT, rounding=ROUND_HALF_UP),
        })
    return {"disrupted": disrupted, "lines": lines, "total": sum((l["refund"] for l in lines), Decimal("0.00"))}


def cancel_booking(booking_id, actor, expected_refund=None):
    """Cancel a whole booking. Idempotent: repeating it never creates a second refund or frees places twice.

    Returns (booking, refund_or_None).
    """
    from apps.payments.models import Refund

    with transaction.atomic():
        booking = Booking.objects.select_for_update().get(pk=booking_id)
        if booking.status == Booking.Status.CANCELLED:
            return booking, Refund.objects.filter(booking=booking, key="cancel").first()
        if booking.status == Booking.Status.PENDING_PAYMENT:
            _free_places(booking, Reservation.Status.RELEASED, Booking.Status.CANCELLED, now=timezone.now(), actor=actor, action="booking.abandoned")
            return booking, None
        if booking.status != Booking.Status.CONFIRMED:
            raise BookingError("not_cancellable", "This booking can no longer be cancelled.")
        now = timezone.now()
        quote = refund_quote(booking, now)
        if expected_refund is not None and Decimal(expected_refund) != quote["total"]:
            raise BookingError("refund_changed", "The refund amount changed since you looked.", new_refund=f"{quote['total']:.2f}")
        reason = Refund.Reason.DISRUPTION_CANCEL if quote["disrupted"] else Refund.Reason.PASSENGER_CANCEL
        refund = Refund.objects.create(
            booking=booking, key="cancel", reason=reason, amount=quote["total"], currency=booking.currency,
            detail={"lines": [{**l, "paid": str(l["paid"]), "refund": str(l["refund"])} for l in quote["lines"]]},
        )
        refund.status, refund.completed_at = Refund.Status.COMPLETED, now  # simulated instant refund
        refund.save(update_fields=["status", "completed_at"])
        _free_places(booking, Reservation.Status.RELEASED, Booking.Status.CANCELLED, now=now, actor=actor, action="booking.cancelled")
        from apps.notifications.services import notify
        notify(booking.user, "booking_cancelled", f"Booking {booking.reference} cancelled",
               f"Simulated refund of {booking.currency} {refund.amount:.2f} issued.", booking, f"cancel:{booking.pk}")
        return booking, refund
