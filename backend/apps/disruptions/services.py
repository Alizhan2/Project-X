"""Disruptions: what an operator change does to existing bookings.

`live_legs` re-times a booking from the *current* state of its services (purchase snapshots are never touched).
Bus/train legs follow their departure (+ delay). A taxi leg is dispatched on demand, so it moves with the leg
before it, and is only impossible if its pickup falls outside the taxi's service window.
"""

from dataclasses import dataclass, field
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.bookings.models import Booking, BookingLeg, Reservation
from apps.core import jobs
from apps.core.models import AuditRecord
from apps.notifications.services import notify
from apps.notifications.follows import notify_followers
from apps.notifications.watches import schedule_evaluation
from apps.transport.models import Departure, RouteStop, TransferLink

from .models import DisruptionEvent

MAX_DELAY_MINUTES = 720


class ChangeError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code, self.message = code, message


@dataclass
class LiveLeg:
    leg: BookingLeg
    departs_at: object
    arrives_at: object
    cancelled: bool = False
    taxi_unavailable: bool = False


@dataclass
class Assessment:
    """Outcome for one booking. status: ok | delayed | broken. `problem_sequence` = first leg that cannot be used."""

    booking: Booking
    status: str
    reason: str = ""
    problem_sequence: int | None = None
    legs: list[LiveLeg] = field(default_factory=list)
    arrival_delay_minutes: int = 0


def _transfer_map():
    return {(t.from_stop_id, t.to_stop_id): t.minutes for t in TransferLink.objects.all()}


def live_legs(booking, overrides=None, transfers=None) -> list[LiveLeg]:
    """`overrides`: {departure_id: (status, delay_minutes)} to evaluate a hypothetical change."""
    overrides = overrides or {}
    transfers = transfers if transfers is not None else _transfer_map()
    out: list[LiveLeg] = []
    for leg in booking.legs.select_related("departure", "taxi_offer").order_by("sequence"):
        if leg.status != BookingLeg.Status.BOOKED:
            continue
        if leg.departure_id:
            dep = leg.departure
            status, delay = overrides.get(dep.pk, (dep.status, dep.delay_minutes))
            rs = {r.stop_id: r for r in RouteStop.objects.filter(route_id=dep.route_id, stop_id__in=[leg.from_stop_id, leg.to_stop_id])}
            o, d = rs[leg.from_stop_id], rs[leg.to_stop_id]
            shift = timedelta(minutes=delay)
            out.append(LiveLeg(
                leg, dep.departs_at + timedelta(minutes=o.departure_offset_min) + shift,
                dep.departs_at + timedelta(minutes=d.arrival_offset_min) + shift, cancelled=status == Departure.Status.CANCELLED,
            ))
        else:
            offer = leg.taxi_offer
            if out:
                prev = out[-1]
                need = settings.MIN_SAME_STOP_TRANSFER_MIN if prev.leg.to_stop_id == leg.from_stop_id else transfers.get((prev.leg.to_stop_id, leg.from_stop_id), 0)
                pickup = prev.arrives_at + timedelta(minutes=need + offer.pickup_wait_min)
            else:
                pickup = leg.departs_at
            local = timezone.localtime(pickup).time()
            out.append(LiveLeg(leg, pickup, pickup + timedelta(minutes=offer.ride_min),
                               taxi_unavailable=not (offer.service_start <= local <= offer.service_end)))
    return out


def assess(booking, overrides=None, transfers=None) -> Assessment:
    transfers = transfers if transfers is not None else _transfer_map()
    legs = live_legs(booking, overrides, transfers)
    a = Assessment(booking=booking, status="ok", legs=legs)
    for i, ll in enumerate(legs):
        if ll.cancelled:
            a.status, a.reason, a.problem_sequence = "broken", "service_cancelled", ll.leg.sequence
            break
        if ll.taxi_unavailable:
            a.status, a.reason, a.problem_sequence = "broken", "taxi_unavailable", ll.leg.sequence
            break
        if i > 0 and ll.leg.departure_id:
            prev = legs[i - 1]
            need = settings.MIN_SAME_STOP_TRANSFER_MIN if prev.leg.to_stop_id == ll.leg.from_stop_id else transfers.get((prev.leg.to_stop_id, ll.leg.from_stop_id), 0)
            if ll.departs_at < prev.arrives_at + timedelta(minutes=need):
                a.status, a.reason, a.problem_sequence = "broken", "connection_missed", ll.leg.sequence
                break
    if a.status == "ok" and legs:
        a.arrival_delay_minutes = max(0, int((legs[-1].arrives_at - legs[-1].leg.arrives_at).total_seconds() // 60))
        # "delayed" = any leg moved from what was sold, even if every connection still holds.
        if any(ll.departs_at != ll.leg.departs_at or ll.arrives_at != ll.leg.arrives_at for ll in legs):
            a.status = "delayed"
    return a


def is_disrupted(booking) -> bool:
    return assess(booking).status == "broken"


def _bookings_on(departure):
    ids = BookingLeg.objects.filter(
        departure=departure, status=BookingLeg.Status.BOOKED,
        booking__status__in=[Booking.Status.CONFIRMED, Booking.Status.PENDING_PAYMENT],
    ).values_list("booking_id", flat=True)
    return Booking.objects.filter(pk__in=ids).select_related("user").order_by("pk")


def preview_impact(departure, action, minutes=0):
    """Consequences of a hypothetical change, without applying it. Returns a list of dicts."""
    overrides = _override(departure, action, minutes)
    transfers = _transfer_map()
    impacts = []
    for b in _bookings_on(departure):
        after = assess(b, {departure.pk: overrides}, transfers)
        before = assess(b, None, transfers)
        impacts.append({"booking": b, "before": before.status, "after": after.status, "reason": after.reason,
                        "arrival_delay_minutes": after.arrival_delay_minutes})
    return impacts


def _override(departure, action, minutes):
    if action == "cancel":
        return (Departure.Status.CANCELLED, departure.delay_minutes)
    if action == "delay":
        return (Departure.Status.DELAYED if minutes > 0 else Departure.Status.SCHEDULED, minutes)
    raise ChangeError("bad_action", "Unknown action.")


def _describe(reason, dep_label):
    return {
        "service_cancelled": f"Your service {dep_label} was cancelled by the operator.",
        "connection_missed": f"A delay to {dep_label} means you can no longer make a connection.",
        "taxi_unavailable": f"After a change to {dep_label}, your taxi pickup falls outside its service hours.",
    }[reason]


def apply_change(*, actor, departure_id, action, minutes=0):
    """Apply an operator delay/cancellation. Idempotent: repeating the same change creates no event/notifications.

    Returns (event_or_None, noop). The caller has already authorised `actor` for this departure's operator.
    """
    from apps.bookings.services import free_pending_booking  # local import: avoids a cycle

    if action == "delay" and not 0 <= minutes <= MAX_DELAY_MINUTES:
        raise ChangeError("bad_minutes", f"Delay must be between 0 and {MAX_DELAY_MINUTES} minutes.")
    with transaction.atomic():
        dep = Departure.objects.select_for_update().select_related("route").get(pk=departure_id)
        if dep.status == Departure.Status.CANCELLED:
            if action == "cancel":
                return None, True
            raise ChangeError("already_cancelled", "A cancelled service cannot be changed.")
        last = RouteStop.objects.filter(route=dep.route).order_by("-sequence").first()
        if dep.departs_at + timedelta(minutes=last.arrival_offset_min + dep.delay_minutes) < timezone.now():
            raise ChangeError("finished", "This service has already finished.")
        if action == "delay" and minutes == dep.delay_minutes:
            return None, True
        status, delay = _override(dep, action, minutes)
        label = f"{dep.route.code} {timezone.localtime(dep.departs_at):%d.%m %H:%M}"
        # Assess *after* applying so connection checks see the new times.
        dep.status, dep.delay_minutes = status, delay
        dep.save(update_fields=["status", "delay_minutes"])
        kind = DisruptionEvent.Kind.CANCEL if action == "cancel" else (DisruptionEvent.Kind.DELAY if minutes > 0 else DisruptionEvent.Kind.CLEAR)
        event = DisruptionEvent.objects.create(departure=dep, kind=kind, delay_minutes=delay if kind == "delay" else 0, created_by=actor)
        affected = 0
        booked_user_ids = set()
        transfers = _transfer_map()
        for b in _bookings_on(dep):
            booked_user_ids.add(b.user_id)
            a = assess(b, None, transfers)
            if b.status == Booking.Status.PENDING_PAYMENT:
                if action == "cancel":
                    free_pending_booking(b.pk, reason="service_cancelled")
                    notify(b.user, "reservation_released", "Reservation released",
                           f"{_describe('service_cancelled', label)} Your unpaid reservation {b.reference} was released; nothing was charged.",
                           b, f"event:{event.pk}:booking:{b.pk}")
                    affected += 1
                continue
            if a.status == "broken":
                jobs.enqueue("recover_booking", {"booking_id": b.pk, "event_id": event.pk}, dedupe_key=f"recover:{event.pk}:{b.pk}")
                notify(b.user, "journey_disrupted", f"Your journey {b.reference} needs attention",
                       f"{_describe(a.reason, label)} Open the booking to review replacement options or cancel for a full refund.",
                       b, f"event:{event.pk}:booking:{b.pk}")
                affected += 1
            elif a.status == "delayed" and kind == DisruptionEvent.Kind.DELAY:
                notify(b.user, "journey_delayed", f"Delay on journey {b.reference}",
                       f"{label} is delayed by {delay} minutes. Your connections still work"
                       + (f"; you arrive about {a.arrival_delay_minutes} minutes later." if a.arrival_delay_minutes else " and your arrival time is unchanged."),
                       b, f"event:{event.pk}:booking:{b.pk}")
                affected += 1
        notify_followers(dep, kind, delay, event.pk, exclude_user_ids=booked_user_ids)
        # Open offers that include this service are re-evaluated (e.g. the replacement itself got cancelled/delayed).
        from django.db.models import Q
        from .models import ReplacementOffer
        stale = ReplacementOffer.objects.filter(status=ReplacementOffer.Status.PROPOSED).filter(
            Q(legs_param__startswith=f"d{dep.pk}:") | Q(legs_param__contains=f",d{dep.pk}:")).values_list("booking_id", flat=True)
        for booking_id in set(stale):
            jobs.enqueue("recover_booking", {"booking_id": booking_id, "event_id": event.pk}, dedupe_key=f"recover:{event.pk}:{booking_id}")
        event.affected_bookings = affected
        event.save(update_fields=["affected_bookings"])
        AuditRecord.objects.create(
            actor=actor, action=f"service.{kind}", object_type="departure", object_id=str(dep.pk),
            detail={"delay_minutes": delay, "affected_bookings": affected, "route": dep.route.code},
        )
        schedule_evaluation()      # cancellations/delays change what searches return
        return event, False
