"""Disruption recovery: propose and apply replacements for the unusable remainder of a booking.

Offers are NON-reserving (nothing is held until acceptance) and are fully re-validated on acceptance.
Everything reuses existing services: planning.search / build_itinerary for routing, bookings.make_leg for legs,
the same departure lock order as checkout, and the existing simulated payment/refund tables.
"""

import hashlib
import json
import logging
from datetime import datetime, timedelta
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
    i = next(i for i, ll in enumerate(a.legs) if ll.leg.sequence == a.problem_sequence)
    return a.legs[:i], a.legs[i:]


def _previous_leg(kept):
    if not kept:
        return None
    last = kept[-1]
    return planner.Leg(last.leg.from_stop, last.leg.to_stop, last.departs_at, last.arrives_at, Decimal("0"), last.leg.booking.currency)


def recovery_context(booking, a, now, constraints=None):
    """Current reachable location, never an arbitrary stop supplied by the client."""
    from apps.planning.transfers import load_transfer_rules, connection_accessible, transfer_minutes
    from apps.transport.models import Stop
    constraints = constraints or booking.recovery_preferences or {}
    kept = []
    for ll in a.legs:
        if ll.leg.boarded_at or ll.leg.completed_at or (ll.departs_at <= now and not ll.cancelled):
            kept.append(ll)
        else:
            break
    if len(kept) == len(a.legs):
        return kept, [], None, {}, []
    replaced = a.legs[len(kept):]
    base = kept[-1].leg.to_stop if kept else replaced[0].leg.from_stop
    ready = max(now, kept[-1].arrives_at + timedelta(minutes=settings.MIN_SAME_STOP_TRANSFER_MIN)) if kept else now
    rules = load_transfer_rules()
    wheelchair = booking.wheelchair_required or constraints.get("wheelchair_required", False)
    allowed = {base.code: (base, ready)}
    for (start, end), minutes in rules.items():
        if start == base.pk:
            stop = Stop.objects.get(pk=end)
            if not wheelchair or connection_accessible(rules, base, stop):
                allowed[stop.code] = (stop, ready + timedelta(minutes=minutes))
    requested = constraints.get("origin", base.code)
    if requested not in allowed:
        raise RecoveryError("location_unreachable", "Choose your current reachable location from the available stops.")
    origin, reached = allowed[requested]
    earliest = constraints.get("earliest_departure", reached)
    latest = constraints.get("latest_arrival", a.legs[-1].leg.arrives_at + timedelta(hours=settings.REPLACEMENT_MAX_LATER_ARRIVAL_HOURS))
    if isinstance(earliest, str):
        earliest = datetime.fromisoformat(earliest)
    if isinstance(latest, str):
        latest = datetime.fromisoformat(latest)
    if latest < earliest:
        raise RecoveryError("invalid_deadline", "Arrival deadline must not be before earliest departure.")
    normalized = {"origin": origin.code, "earliest_departure": earliest.isoformat(), "reachable_after": reached.isoformat(),
                  "latest_arrival": latest.isoformat(), "max_payment_now": constraints.get("max_payment_now"),
                  "wheelchair_required": bool(wheelchair)}
    locations = [{"code": stop.code, "name": stop.name} for stop, _ in allowed.values()]
    return kept, replaced, origin, normalized, locations


def _retime_suffix(suffix, previous, rules, passengers):
    from dataclasses import replace
    from apps.planning.transfers import transfer_minutes
    retimed = []
    last_stop, arrival = previous.to_stop, previous.arrives_at
    for ll in suffix:
        if ll.leg.taxi_offer_id:
            need = transfer_minutes(rules, last_stop, ll.leg.from_stop)
            if need is None:
                return None
            ready = arrival + timedelta(minutes=need)
            leg = planner._taxi_leg(ll.leg.taxi_offer, ll.leg.from_stop, ll.leg.to_stop,
                                   ready, passengers, ready + timedelta(minutes=settings.MAX_TRANSFER_WAIT_MIN))
            if leg is None:
                return None
            ll = replace(ll, departs_at=leg.departs_at, arrives_at=leg.arrives_at, taxi_unavailable=False)
        retimed.append(ll)
        last_stop, arrival = ll.leg.to_stop, ll.arrives_at
    return retimed


def _suffix_valid(suffix, rules, wheelchair):
    from apps.planning.transfers import transfer_minutes, connection_accessible
    for ll in suffix:
        vehicle = ll.leg.departure if ll.leg.departure_id else ll.leg.taxi_offer
        if ll.cancelled or ll.taxi_unavailable:
            return False
        if wheelchair and (vehicle.wheelchair_accessible is not True or ll.leg.from_stop.step_free is not True or ll.leg.to_stop.step_free is not True):
            return False
    for left, right in zip(suffix, suffix[1:]):
        need = transfer_minutes(rules, left.leg.to_stop, right.leg.from_stop)
        if need is None or (right.leg.departure_id and left.arrives_at + timedelta(minutes=need) > right.departs_at):
            return False
        if wheelchair and not connection_accessible(rules, left.leg.to_stop, right.leg.from_stop):
            return False
    return True


def _alternatives(booking, a, kept, replaced, now, constraints=None):
    from datetime import datetime
    from apps.planning.transfers import load_transfer_rules, transfer_minutes, leg_accessible, connection_accessible
    from apps.bookings.services import leg_refund_line
    kept, replaced, origin, options, _ = recovery_context(booking, a, now, constraints)
    if not replaced or origin is None:
        return []
    start = max(datetime.fromisoformat(options["earliest_departure"]), datetime.fromisoformat(options["reachable_after"]))
    deadline = datetime.fromisoformat(options["latest_arrival"])
    rules = load_transfer_rules()
    found = []
    # Try reconnecting to still usable booked legs before replacing the entire remainder.
    for count in range(1, len(replaced) + 1):
        removed, suffix = replaced[:count], replaced[count:]
        target = suffix[0].leg.from_stop if suffix else removed[-1].leg.to_stop
        if origin.pk == target.pk:
            continue
        if suffix and (any(ll.cancelled or ll.taxi_unavailable for ll in suffix) or not _suffix_valid(suffix, rules, options["wheelchair_required"])):
            continue
        suffix_deadline = min(deadline, suffix[0].departs_at) if suffix else deadline
        targets = [target]
        if suffix:
            from apps.transport.models import Stop
            targets += list(Stop.objects.filter(pk__in=[a for (a, b) in rules if b == target.pk]))
        alts = []
        for destination in targets:
            if destination.pk == origin.pk:
                continue
            alts.extend(planner.search(origin, destination, start, booking.passengers, now=now,
                              max_legs=max(1, planner.MAX_LEGS - len(kept) - len(suffix)),
                              window=timedelta(hours=settings.REPLACEMENT_WINDOW_HOURS), walk_from_start=True,
                              latest_arrival=suffix_deadline, wheelchair_required=options["wheelchair_required"]))
        for it in alts:
            if len(kept) + len(it.legs) + len(suffix) > planner.MAX_LEGS or it.currency != booking.currency:
                continue
            if options["max_payment_now"] is not None and it.total_price > Decimal(options["max_payment_now"]):
                continue
            actual_suffix = _retime_suffix(suffix, it.legs[-1], rules, booking.passengers)
            if actual_suffix is None:
                continue
            if actual_suffix:
                suffix = actual_suffix
                need = transfer_minutes(rules, it.legs[-1].to_stop, suffix[0].leg.from_stop)
                if need is None or it.arrives_at + timedelta(minutes=need) > suffix[0].departs_at:
                    continue
                if suffix[-1].arrives_at > deadline:
                    continue
                if options["wheelchair_required"]:
                    valid = connection_accessible(rules, it.legs[-1].to_stop, suffix[0].leg.from_stop)
                    for ll in suffix:
                        leg = ll.leg
                        vehicle = leg.departure if leg.departure_id else leg.taxi_offer
                        valid = valid and vehicle.wheelchair_accessible is True and leg.from_stop.step_free is True and leg.to_stop.step_free is True
                    for left, right in zip(suffix, suffix[1:]):
                        valid = valid and connection_accessible(rules, left.leg.to_stop, right.leg.from_stop)
                    if not valid:
                        continue
            it.replaced_sequences = [ll.leg.sequence for ll in removed]
            it.retained_suffix = [ll.leg.sequence for ll in suffix]
            it.final_arrival = suffix[-1].arrives_at if suffix else it.arrives_at
            it.eligible_refund = sum((leg_refund_line(ll.leg, now, ll)["refund"] for ll in removed), Decimal("0"))
            it.recovery_constraints = {k: v for k, v in options.items() if k != "reachable_after"}
            found.append(it)
    def order(it):
        return (it.final_arrival, it.total_price, tuple(leg.route_code for leg in it.legs), it.legs_param)
    unique = {}
    for it in sorted(found, key=order):
        unique.setdefault((it.legs_param, tuple(it.replaced_sequences)), it)
    return list(unique.values())[:MAX_OFFERS]


def _fingerprint(it):
    value = [it.legs_param, str(it.total_price), it.final_arrival.isoformat(), it.replaced_sequences, it.recovery_constraints, str(it.eligible_refund)]
    return hashlib.sha1(json.dumps(value, sort_keys=True).encode()).hexdigest()


def ensure_offers(booking_id, *, now=None, event_id=None, constraints=None):
    now = now or timezone.now()
    with transaction.atomic():
        booking = Booking.objects.select_for_update().select_related("user").get(pk=booking_id)
        live = ReplacementOffer.objects.filter(booking=booking, status=ReplacementOffer.Status.PROPOSED)
        # A pending payment must be reconciled, not replaced by a fresh offer.
        pending_ids = PaymentAttempt.objects.filter(booking=booking, status__in=["created", "pending"], offer__isnull=False).values_list("offer_id", flat=True)
        live.exclude(pk__in=pending_ids).filter(expires_at__lte=now).update(status="expired", resolved_at=now)
        a = assess(booking) if booking.status == Booking.Status.CONFIRMED else None
        if a is None or a.status != "broken":
            live.exclude(pk__in=pending_ids).update(status="invalidated", resolved_at=now, note="The disruption no longer applies.")
            return "not_disrupted", []
        _, _, _, normalized, _ = recovery_context(booking, a, now, constraints)
        preferences = {key: value for key, value in normalized.items() if key != "reachable_after"}
        if preferences and preferences != booking.recovery_preferences:
            booking.recovery_preferences = preferences
            booking.save(update_fields=["recovery_preferences"])
        alts = _alternatives(booking, a, None, None, now, preferences)
        wanted = {_fingerprint(it): it for it in alts}
        live.exclude(fingerprint__in=wanted).exclude(pk__in=pending_ids).update(status="invalidated", resolved_at=now, note="Replaced by updated options.")
        have = set(live.filter(status="proposed").values_list("fingerprint", flat=True))
        for fp, it in wanted.items():
            if fp in have:
                continue
            snapshot = json.loads(json.dumps([serialize_leg(l, it.passengers) for l in it.legs], cls=DjangoJSONEncoder))
            removed = [ll for ll in a.legs if ll.leg.sequence in it.replaced_sequences]
            replaced_value = sum((leg_gross(ll.leg) for ll in removed), Decimal("0"))
            prefs = {**it.recovery_constraints, "replaced_sequences": it.replaced_sequences, "retained_suffix": it.retained_suffix}
            ReplacementOffer.objects.create(booking=booking, problem_sequence=a.problem_sequence,
                legs_selection=[l.selection for l in it.legs], legs_snapshot=snapshot, legs_param=it.legs_param,
                total_new=it.total_price, replaced_value=replaced_value, eligible_refund=it.eligible_refund,
                difference=it.total_price - it.eligible_refund, currency=booking.currency, arrives_at=it.final_arrival,
                fingerprint=fp, constraints_snapshot=prefs, expires_at=now + timedelta(minutes=settings.REPLACEMENT_OFFER_MINUTES))
        offers = list(ReplacementOffer.objects.filter(booking=booking, status="proposed"))
        offers.sort(key=lambda o: (o.arrives_at, o.total_new, tuple(l["route_code"] for l in o.legs_snapshot), o.legs_param))
        if event_id is not None:
            kind = "replacement_options" if offers else "no_replacement"
            notify(booking.user, kind, f"Replacement options for {booking.reference}",
                   "Review replacement options and the full payment now; old-leg refunds are separate." if offers else
                   "No alternative fits your constraints. Cancellation refunds follow each unused leg's policy.",
                   booking, f"recovery:{booking.pk}:{event_id}")
        return ("options" if offers else "none"), offers


@jobs.handler("recover_booking")
def _recover_job(booking_id, event_id=None):
    ensure_offers(booking_id, event_id=event_id)


def expire_due_offers(now=None):
    now = now or timezone.now()
    pending = PaymentAttempt.objects.filter(status__in=["created", "pending"], offer__isnull=False).values_list("offer_id", flat=True)
    return ReplacementOffer.objects.filter(status="proposed", expires_at__lte=now).exclude(pk__in=pending).update(status="expired", resolved_at=now)


# ------------------------------------------------------------------------------------------- acceptance

def _close(offer_id, status, note):
    ReplacementOffer.objects.filter(pk=offer_id, status="proposed").update(status=status, resolved_at=timezone.now(), note=note[:200])


def _validate(booking, offer, now):
    from datetime import datetime
    from apps.planning.transfers import load_transfer_rules, transfer_minutes, connection_accessible
    a = assess(booking)
    if booking.status != Booking.Status.CONFIRMED:
        raise RecoveryError("booking_not_active", "This booking is no longer active.", invalidate="invalidated")
    if offer.status != "proposed":
        raise RecoveryError("offer_unavailable", "This offer is no longer available.")
    if offer.expires_at <= now:
        raise RecoveryError("offer_expired", "This offer has expired. Please review new options.", invalidate="expired")
    if a.status != "broken" or a.problem_sequence != offer.problem_sequence:
        raise RecoveryError("offer_outdated", "Your journey changed since this offer was made.", invalidate="invalidated")
    prefs = dict(offer.constraints_snapshot)
    sequences = prefs.pop("replaced_sequences", [ll.leg.sequence for ll in _split(a)[1]])
    suffix_seq = prefs.pop("retained_suffix", [])
    for key in ("earliest_departure", "latest_arrival"):
        if prefs.get(key):
            prefs[key] = datetime.fromisoformat(prefs[key])
    try:
        kept, _, origin, normalized, _ = recovery_context(booking, a, now, prefs)
    except RecoveryError as exc:
        raise RecoveryError("offer_outdated", exc.message, invalidate="invalidated") from exc
    removed = [ll for ll in a.legs if ll.leg.sequence in sequences]
    suffix = [ll for ll in a.legs if ll.leg.sequence in suffix_seq]
    if not removed or any(ll.leg.boarded_at or ll.leg.completed_at or (ll.departs_at <= now and not ll.cancelled) for ll in removed):
        raise RecoveryError("offer_outdated", "A leg has already started. Your booking was preserved.", invalidate="invalidated")
    old_ids = {ll.leg.departure_id for ll in removed if ll.leg.departure_id}
    new_ids = {item["departure_id"] for item in offer.legs_selection if item.get("departure_id")}
    locked = _lock_departures(old_ids | new_ids | {ll.leg.departure_id for ll in suffix if ll.leg.departure_id})
    try:
        it = planner.build_itinerary(offer.legs_selection, booking.passengers, now, _previous_leg(kept),
                                     wheelchair_required=booking.wheelchair_required or normalized.get("wheelchair_required", False))
    except planner.OfferError as exc:
        raise RecoveryError("offer_outdated", exc.message, invalidate="invalidated") from exc
    from apps.planning.transfers import load_transfer_rules, transfer_minutes, connection_accessible
    rules = load_transfer_rules()
    need = transfer_minutes(rules, origin, it.legs[0].from_stop)
    reached = max(datetime.fromisoformat(normalized["earliest_departure"]), datetime.fromisoformat(normalized["reachable_after"]))
    if need is None or it.departs_at < reached + (timedelta(minutes=need) if origin.pk != it.legs[0].from_stop.pk else timedelta()):
        raise RecoveryError("offer_outdated", "The replacement cannot be reached from your location.", invalidate="invalidated")
    if normalized["wheelchair_required"] and origin.pk != it.legs[0].from_stop.pk and not connection_accessible(rules, origin, it.legs[0].from_stop):
        raise RecoveryError("offer_outdated", "The transfer path is not confirmed accessible.", invalidate="invalidated")
    suffix = _retime_suffix(suffix, it.legs[-1], rules, booking.passengers)
    if suffix is None:
        raise RecoveryError("offer_outdated", "The retained taxi is no longer available.", invalidate="invalidated")
    if suffix:
        if normalized["wheelchair_required"] and not connection_accessible(rules, it.legs[-1].to_stop, suffix[0].leg.from_stop):
            raise RecoveryError("offer_outdated", "The retained transfer path is not confirmed accessible.", invalidate="invalidated")
        if not _suffix_valid(suffix, rules, normalized["wheelchair_required"]):
            raise RecoveryError("offer_outdated", "The retained journey is no longer usable.", invalidate="invalidated")
        need = transfer_minutes(rules, it.legs[-1].to_stop, suffix[0].leg.from_stop)
        if any(ll.cancelled or ll.taxi_unavailable for ll in suffix) or need is None or it.arrives_at + timedelta(minutes=need) > suffix[0].departs_at:
            raise RecoveryError("offer_outdated", "The retained connection is no longer possible.", invalidate="invalidated")
    final_arrival = suffix[-1].arrives_at if suffix else it.arrives_at
    from apps.bookings.services import leg_refund_line
    refund = sum((leg_refund_line(ll.leg, now, ll)["refund"] for ll in removed), Decimal("0"))
    if (it.total_price != offer.total_new or final_arrival != offer.arrives_at or refund != offer.eligible_refund
            or final_arrival > datetime.fromisoformat(normalized["latest_arrival"])
            or (normalized["max_payment_now"] is not None and it.total_price > Decimal(normalized["max_payment_now"]))):
        raise RecoveryError("offer_outdated", "The price, refund or times changed. Review updated options.", invalidate="invalidated")
    for leg in it.legs:
        if leg.departure and locked[leg.departure.pk].places_left < booking.passengers:
            raise RecoveryError("no_capacity", "The replacement no longer has enough free places.", invalidate="invalidated")
    return it, kept, removed, suffix


def accept_offer(*, user, reference, offer_id, idempotency_key, outcome="success", reconcile=False):
    from apps.payments.services import begin_attempt, record_outcome, compensate, request_refund
    from apps.bookings.services import BookingError
    booking = Booking.objects.filter(reference=reference, user=user).first()
    offer = ReplacementOffer.objects.filter(pk=offer_id, booking=booking).first() if booking else None
    if offer is None:
        return None
    # Validate before creating a new charge. For an existing pending charge we must first resolve its result.
    try:
        with transaction.atomic():
            booking = Booking.objects.select_for_update().get(pk=booking.pk)
            offer = ReplacementOffer.objects.select_for_update().get(pk=offer.pk)
            if offer.status == "accepted":
                return offer, True
            prior = PaymentAttempt.objects.filter(booking=booking, idempotency_key=idempotency_key).first()
            if prior is None:
                if reconcile:
                    raise RecoveryError("payment_not_found", "The original payment attempt was not found.")
                _validate(booking, offer, timezone.now())
            attempt, replayed = begin_attempt(booking, idempotency_key, offer.total_new, PaymentAttempt.Purpose.REPLACEMENT, offer)
    except BookingError as exc:
        raise RecoveryError(exc.code, exc.message) from exc
    except RecoveryError as exc:
        if exc.invalidate:
            _close(offer.pk, exc.invalidate, exc.message)
        raise
    with transaction.atomic():
        booking = Booking.objects.select_for_update().get(pk=booking.pk)
        offer = ReplacementOffer.objects.select_for_update().get(pk=offer.pk)
        attempt = PaymentAttempt.objects.select_for_update().get(pk=attempt.pk)
        if offer.status == "accepted":
            return offer, True
        record_outcome(attempt, outcome, reconcile=reconcile)
        if attempt.status == "failed":
            # The transaction must commit the failed attempt before returning an error.
            failure = RecoveryError("payment_failed", "The simulated payment failed. Your original booking is intact.")
        elif attempt.status != "succeeded":
            return offer, replayed
        elif attempt.compensated:
            return offer, True
        else:
            failure = None
            try:
                with transaction.atomic():
                    it, kept, removed, suffix = _validate(booking, offer, timezone.now())
                    now = timezone.now()
                    for leg in it.legs:
                        if leg.departure:
                            Departure.objects.filter(pk=leg.departure.pk).update(places_taken=F("places_taken") + booking.passengers)
                    previous = list(booking.legs.all())
                    base = max((leg.sequence for leg in previous), default=-1) + 1
                    new = [make_leg(booking, base + i, leg, booking.passengers, Reservation.Status.CONSUMED) for i, leg in enumerate(it.legs)]
                    for ll in removed:
                        for res in Reservation.objects.filter(leg=ll.leg, status__in=["held", "consumed"]):
                            Departure.objects.filter(pk=res.departure_id).update(places_taken=F("places_taken") - res.places)
                            res.status = Reservation.Status.RELEASED
                            res.save(update_fields=["status"])
                        ll.leg.status = BookingLeg.Status.REPLACED
                        ll.leg.save(update_fields=["status"])
                    active = [ll.leg for ll in kept] + new + [ll.leg for ll in suffix]
                    active_ids = {leg.pk for leg in active}
                    history = [leg for leg in previous if leg.pk not in active_ids]
                    ordered = active + history
                    # Temporarily move unique sequence numbers, then order active travel before history.
                    for i, leg in enumerate(ordered):
                        BookingLeg.objects.filter(pk=leg.pk).update(sequence=32767 - i)
                    for i, leg in enumerate(ordered):
                        BookingLeg.objects.filter(pk=leg.pk).update(sequence=i)
                    request_refund(booking, key=f"replacement:{offer.pk}", amount=offer.eligible_refund,
                                   reason=Refund.Reason.REPLACED_LEGS,
                                   detail={"offer": offer.pk, "leg_ids": [ll.leg.pk for ll in removed]})
                    booking.total_amount = sum((leg_gross(leg) for leg in active), Decimal("0"))
                    booking.save(update_fields=["total_amount"])
                    offer.status, offer.resolved_at = "accepted", now
                    offer.save(update_fields=["status", "resolved_at"])
                    ReplacementOffer.objects.filter(booking=booking, status="proposed").update(status="invalidated", resolved_at=now, note="Another replacement was accepted.")
                    AuditRecord.objects.create(actor=user, action="booking.replacement_accepted", object_type="booking", object_id=booking.reference,
                                               detail={"offer": offer.pk, "payment_now": str(it.total_price), "refund_requested": str(offer.eligible_refund)})
                    notify(booking.user, "replacement_confirmed", f"Replacement confirmed for {booking.reference}",
                           "Replacement booked (simulated). Its full price was charged; any old-leg refund is processed separately.", booking, f"replacement:{offer.pk}")
            except (RecoveryError, BookingError, IntegrityError) as exc:
                # The capture remains durable while all booking mutations are rolled back.
                compensate(attempt)
                _close(offer.pk, getattr(exc, "invalidate", None) or "invalidated", getattr(exc, "message", "Replacement confirmation failed; the payment is being refunded."))
                offer.refresh_from_db()
                return offer, replayed
        if failure is None:
            return offer, replayed
    raise failure


def decline_offer(*, user, reference, offer_id):
    booking = Booking.objects.filter(reference=reference, user=user).first()
    offer = ReplacementOffer.objects.filter(pk=offer_id, booking=booking).first() if booking else None
    if offer is None:
        return None
    if PaymentAttempt.objects.filter(offer=offer, status__in=["created", "pending"]).exists():
        raise RecoveryError("payment_pending", "Check the pending payment result before declining this offer.")
    _close(offer.pk, "declined", "Declined by passenger.")
    offer.refresh_from_db()
    return offer
