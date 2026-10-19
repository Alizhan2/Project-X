"""Disruption recovery: propose and apply replacements for the unusable remainder of a booking.

Offers are NON-reserving (nothing is held until acceptance) and are fully re-validated on acceptance.
Everything reuses existing services: planning.search / build_itinerary for routing, bookings.make_leg for legs,
the same departure lock order as checkout, and the existing simulated payment/refund tables.
"""

import hashlib
import json
import logging
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import IntegrityError, transaction
from django.db.models import F, Max
from django.utils import timezone

from apps.bookings.models import Booking, BookingLeg, Reservation
from apps.bookings.services import _lock_departures, leg_gross, make_leg
from apps.core import jobs
from apps.core.models import AuditRecord
from apps.notifications.services import notify
from apps.payments.models import PaymentAttempt, Refund
from apps.planning import services as planner
from apps.planning.serializers import serialize_leg
from apps.transport.models import Departure

from .models import ReplacementOffer
from .services import assess

log = logging.getLogger(__name__)
CENT = Decimal("0.01")
MAX_OFFERS = 3


class RecoveryError(Exception):
    """`code` is machine-readable. `invalidate` closes the offer (in its own transaction) after the failed attempt."""

    def __init__(self, code, message, *, invalidate=None, failed_payment=None, **extra):
        super().__init__(message)
        self.code, self.message, self.invalidate, self.failed_payment, self.extra = code, message, invalidate, failed_payment, extra


# ----------------------------------------------------------------------------------------------- generation

def _split(a):
    """(kept LiveLegs, replaced LiveLegs) from an Assessment whose status is broken."""
    i = next(i for i, ll in enumerate(a.legs) if ll.leg.sequence == a.problem_sequence)
    return a.legs[:i], a.legs[i:]


def _previous_leg(kept):
    if not kept:
        return None
    last = kept[-1]
    return planner.Leg(last.leg.from_stop, last.leg.to_stop, last.departs_at, last.arrives_at, Decimal("0"), last.leg.booking.currency)


def _alternatives(booking, a, kept, replaced, now):
    destination = replaced[-1].leg.to_stop
    if kept:
        origin = kept[-1].leg.to_stop
        start = kept[-1].arrives_at + timedelta(minutes=settings.MIN_SAME_STOP_TRANSFER_MIN)
    else:
        origin = replaced[0].leg.from_stop
        start = replaced[0].leg.departs_at
    if origin.pk == destination.pk:
        return []
    last_planned = booking.legs.filter(status=BookingLeg.Status.BOOKED).order_by("-sequence").first().arrives_at
    found = planner.search(
        origin, destination, max(start, now), booking.passengers, now=now,
        max_legs=max(1, planner.MAX_LEGS - len(kept)), window=timedelta(hours=settings.REPLACEMENT_WINDOW_HOURS),
        walk_from_start=True, latest_arrival=last_planned + timedelta(hours=settings.REPLACEMENT_MAX_LATER_ARRIVAL_HOURS),
    )
    # Variety: earliest arrival, cheapest, largest buffer; then fill by arrival time.
    picks = []
    for ordering in (lambda i: (i.arrives_at, i.total_price), lambda i: (i.total_price, i.arrives_at), planner.SORTS["buffer"]):
        for it in sorted(found, key=ordering):
            if it.legs_param not in [p.legs_param for p in picks]:
                picks.append(it)
                break
    for it in sorted(found, key=lambda i: (i.arrives_at, i.total_price)):
        if len(picks) >= MAX_OFFERS:
            break
        if it.legs_param not in [p.legs_param for p in picks]:
            picks.append(it)
    return sorted(picks[:MAX_OFFERS], key=lambda i: (i.arrives_at, i.total_price))


def _fingerprint(it):
    return hashlib.sha1(f"{it.legs_param}|{it.total_price}|{it.arrives_at.isoformat()}".encode()).hexdigest()


def ensure_offers(booking_id, *, now=None, event_id=None):
    """Make the stored offers match reality. Idempotent and safe to run concurrently or repeatedly.

    Returns (state, offers) with state in: "not_disrupted" | "options" | "none".
    """
    now = now or timezone.now()
    with transaction.atomic():
        booking = Booking.objects.select_for_update().select_related("user").get(pk=booking_id)
        live = ReplacementOffer.objects.filter(booking=booking, status=ReplacementOffer.Status.PROPOSED)
        live.filter(expires_at__lte=now).update(status=ReplacementOffer.Status.EXPIRED, resolved_at=now)
        a = assess(booking) if booking.status == Booking.Status.CONFIRMED else None
        if a is None or a.status != "broken":
            live.update(status=ReplacementOffer.Status.INVALIDATED, resolved_at=now, note="The disruption no longer applies.")
            return "not_disrupted", []
        kept, replaced = _split(a)
        alts = _alternatives(booking, a, kept, replaced, now)
        wanted = {_fingerprint(it): it for it in alts}
        for offer in live:
            if offer.fingerprint not in wanted:
                offer.status, offer.resolved_at, offer.note = ReplacementOffer.Status.INVALIDATED, now, "Replaced by updated options."
                offer.save(update_fields=["status", "resolved_at", "note"])
        have = set(live.filter(status=ReplacementOffer.Status.PROPOSED).values_list("fingerprint", flat=True))
        replaced_value = sum((leg_gross(ll.leg) for ll in replaced), Decimal("0"))
        for fp, it in wanted.items():
            if fp in have:
                continue
            snapshot = json.loads(json.dumps([serialize_leg(l, it.passengers) for l in it.legs], cls=DjangoJSONEncoder))
            ReplacementOffer.objects.create(
                booking=booking, problem_sequence=a.problem_sequence, legs_selection=[l.selection for l in it.legs],
                legs_snapshot=snapshot, legs_param=it.legs_param, total_new=it.total_price, replaced_value=replaced_value,
                difference=it.total_price - replaced_value, currency=booking.currency, arrives_at=it.arrives_at, fingerprint=fp,
                expires_at=now + timedelta(minutes=settings.REPLACEMENT_OFFER_MINUTES),
            )
        offers = list(ReplacementOffer.objects.filter(booking=booking, status=ReplacementOffer.Status.PROPOSED))
        if event_id is not None:
            if offers:
                notify(booking.user, "replacement_options", f"Replacement options for {booking.reference}",
                       f"{len(offers)} replacement option(s) are ready. They expire in {settings.REPLACEMENT_OFFER_MINUTES} minutes.",
                       booking, f"recovery:{booking.pk}:{event_id}")
            else:
                notify(booking.user, "no_replacement", f"No replacement found for {booking.reference}",
                       "We found no suitable alternative for the rest of your journey. You can cancel for a full refund of the unused legs.",
                       booking, f"recovery:{booking.pk}:{event_id}")
        return ("options" if offers else "none"), offers


@jobs.handler("recover_booking")
def _recover_job(booking_id, event_id=None):
    ensure_offers(booking_id, event_id=event_id)


def expire_due_offers(now=None):
    now = now or timezone.now()
    return ReplacementOffer.objects.filter(status=ReplacementOffer.Status.PROPOSED, expires_at__lte=now).update(
        status=ReplacementOffer.Status.EXPIRED, resolved_at=now)


# ------------------------------------------------------------------------------------------- acceptance

def _close(offer_id, status, note):
    """Close an offer in its own short transaction (the failed acceptance transaction was rolled back)."""
    ReplacementOffer.objects.filter(pk=offer_id, status=ReplacementOffer.Status.PROPOSED).update(
        status=status, resolved_at=timezone.now(), note=note[:200])


def accept_offer(*, user, reference, offer_id, idempotency_key, outcome="success"):
    """Apply a replacement. Returns (offer, replayed), or None if the booking/offer is not the user's (-> 404).

    Idempotent: repeating it after success returns the same result; a repeated payment key never charges twice.
    """
    booking = Booking.objects.filter(reference=reference, user=user).first()
    offer = ReplacementOffer.objects.filter(pk=offer_id, booking=booking).first() if booking else None
    if offer is None:
        return None
    try:
        return _accept(booking.pk, offer.pk, user, idempotency_key, outcome)
    except RecoveryError as e:
        if e.invalidate:
            _close(offer.pk, e.invalidate, e.message)
        if e.failed_payment is not None:
            PaymentAttempt.objects.get_or_create(
                booking=booking, idempotency_key=idempotency_key,
                defaults={"purpose": PaymentAttempt.Purpose.REPLACEMENT, "amount": e.failed_payment, "currency": booking.currency,
                          "status": PaymentAttempt.Status.FAILED, "failure_reason": "Simulated card decline (demonstration)."})
        raise


def _accept(booking_id, offer_id, user, key, outcome):
    S = ReplacementOffer.Status
    with transaction.atomic():
        booking = Booking.objects.select_for_update().get(pk=booking_id)                      # 1. booking
        offer = ReplacementOffer.objects.select_for_update().get(pk=offer_id)                 # 2. offer
        if offer.status == S.ACCEPTED:
            return offer, True
        if offer.status != S.PROPOSED:
            raise RecoveryError("offer_unavailable", f"This offer is no longer available ({offer.get_status_display().lower()}).")
        if booking.status != Booking.Status.CONFIRMED:
            raise RecoveryError("booking_not_active", "This booking is no longer active.", invalidate=S.INVALIDATED)
        now = timezone.now()
        if offer.expires_at <= now:
            raise RecoveryError("offer_expired", "This offer has expired. Please review the new options.", invalidate=S.EXPIRED)
        prior = PaymentAttempt.objects.filter(booking=booking, idempotency_key=key).first()
        if prior and prior.status == PaymentAttempt.Status.FAILED:
            raise RecoveryError("payment_failed", "The simulated payment failed. Nothing was changed.", failed_payment=None)
        a = assess(booking)
        if a.status != "broken" or a.problem_sequence != offer.problem_sequence:
            raise RecoveryError("offer_outdated", "Your journey changed since this offer was made.", invalidate=S.INVALIDATED)
        kept, replaced = _split(a)
        replaced_value = sum((leg_gross(ll.leg) for ll in replaced), Decimal("0"))
        new_ids = {s["departure_id"] for s in offer.legs_selection if s.get("departure_id") is not None}
        old_ids = {ll.leg.departure_id for ll in replaced if ll.leg.departure_id}
        locked = _lock_departures(new_ids | old_ids)                                          # 3. departures, ascending id
        try:
            it = planner.build_itinerary(offer.legs_selection, booking.passengers, now, _previous_leg(kept))
        except planner.OfferError as e:
            raise RecoveryError("offer_outdated", f"This replacement is no longer possible: {e.message}", invalidate=S.INVALIDATED) from e
        if it.total_price != offer.total_new or it.arrives_at != offer.arrives_at or replaced_value != offer.replaced_value:
            raise RecoveryError("offer_outdated", "The price or times changed since this offer was made.", invalidate=S.INVALIDATED,
                                new_difference=f"{it.total_price - replaced_value:.2f}")
        for leg in it.legs:
            if leg.departure and locked[leg.departure.pk].places_left < booking.passengers:
                raise RecoveryError("no_capacity", "The replacement no longer has enough free places.", invalidate=S.INVALIDATED)
        diff = it.total_price - replaced_value
        if diff > 0 and outcome == "failure":
            raise RecoveryError("payment_failed", "The simulated payment failed. Nothing was changed.", failed_payment=diff)
        # ---- apply: acquire new places first, then release the old ones
        for leg in it.legs:
            if leg.departure:
                Departure.objects.filter(pk=leg.departure.pk).update(places_taken=F("places_taken") + booking.passengers)
        next_seq = booking.legs.aggregate(m=Max("sequence"))["m"] + 1
        for i, leg in enumerate(it.legs):
            make_leg(booking, next_seq + i, leg, booking.passengers, Reservation.Status.CONSUMED)
        for ll in replaced:
            for res in Reservation.objects.filter(leg=ll.leg, status__in=["held", "consumed"]):
                Departure.objects.filter(pk=res.departure_id).update(places_taken=F("places_taken") - res.places)
                res.status = Reservation.Status.RELEASED
                res.save(update_fields=["status"])
            ll.leg.status = BookingLeg.Status.REPLACED
            ll.leg.save(update_fields=["status"])
        if diff > 0:
            PaymentAttempt.objects.create(booking=booking, purpose=PaymentAttempt.Purpose.REPLACEMENT, idempotency_key=key,
                                          amount=diff, currency=booking.currency, status=PaymentAttempt.Status.SUCCEEDED)
        elif diff < 0:
            Refund.objects.create(booking=booking, key=f"replacement:{offer.pk}", reason=Refund.Reason.REPLACEMENT_DIFFERENCE, amount=-diff,
                                  currency=booking.currency, status=Refund.Status.COMPLETED, completed_at=now,
                                  detail={"offer": offer.pk, "replaced_value": str(replaced_value), "new_total": str(it.total_price)})
        booking.total_amount = booking.total_amount + diff
        booking.save(update_fields=["total_amount"])
        offer.status, offer.resolved_at = S.ACCEPTED, now
        offer.save(update_fields=["status", "resolved_at"])
        ReplacementOffer.objects.filter(booking=booking, status=S.PROPOSED).update(
            status=S.INVALIDATED, resolved_at=now, note="Another replacement was accepted.")
        AuditRecord.objects.create(actor=user, action="booking.replacement_accepted", object_type="booking", object_id=booking.reference,
                                   detail={"offer": offer.pk, "difference": str(diff), "replaced_sequences": [ll.leg.sequence for ll in replaced]})
        notify(booking.user, "replacement_confirmed", f"Replacement confirmed for {booking.reference}",
               "Your new journey is booked (simulated)." + (f" Extra simulated payment: {booking.currency} {diff:.2f}." if diff > 0 else
                f" Simulated refund: {booking.currency} {-diff:.2f}." if diff < 0 else ""), booking, f"replacement:{offer.pk}")
        return offer, False


def decline_offer(*, user, reference, offer_id):
    booking = Booking.objects.filter(reference=reference, user=user).first()
    offer = ReplacementOffer.objects.filter(pk=offer_id, booking=booking).first() if booking else None
    if offer is None:
        return None
    _close(offer.pk, ReplacementOffer.Status.DECLINED, "Declined by passenger.")
    offer.refresh_from_db()
    return offer
