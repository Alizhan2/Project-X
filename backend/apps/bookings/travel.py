"""Read-only, current timetable view. Never rewrites the purchase snapshots."""
from datetime import timedelta

from django.utils import timezone

from apps.disruptions.services import assess
from apps.transport.markets import booking_timezone, city_id_for_stop, local_datetime, local_iso
from .models import Booking


def travel_plan(booking, assessment=None, now=None):
    now = now or timezone.now()
    assessment = assessment or assess(booking)
    zone = booking_timezone(booking)
    legs = []
    for item in assessment.legs:
        leg = item.leg
        state = ("completed" if item.arrives_at <= now else
                 "travelling" if item.departs_at <= now else "upcoming")
        if item.cancelled or item.taxi_unavailable:
            state = "unavailable"
        legs.append({
            "sequence": leg.sequence, "from": leg.from_name, "to": leg.to_name,
            "from_code": leg.from_stop.code, "to_code": leg.to_stop.code,
            "mode": leg.mode, "route_code": leg.route_code, "operator": leg.operator_name,
            "departs_at": local_datetime(item.departs_at, zone), "arrives_at": local_datetime(item.arrives_at, zone),
            "scheduled_departs_at": local_datetime(leg.departs_at, zone), "scheduled_arrives_at": local_datetime(leg.arrives_at, zone),
            "state": state,
        })
    remaining = [leg for leg in legs if leg["arrives_at"] > now]
    return {
        "reference": booking.reference, "generated_at": local_datetime(now, zone), "timezone": zone,
        "origin_city": city_id_for_stop(assessment.legs[0].leg.from_stop) if assessment.legs else None,
        "destination_city": city_id_for_stop(assessment.legs[-1].leg.to_stop) if assessment.legs else None,
        "status": assessment.status, "reason": assessment.reason,
        "progress": "finished" if not remaining else (
            "needs_attention" if assessment.status == "broken" else
            "in_progress" if legs[0]["departs_at"] <= now else "upcoming"),
        "next_sequence": remaining[0]["sequence"] if remaining else None,
        "legs": legs,
        "notice": "Timetable estimate, not GPS tracking. All transport and tickets are simulated.",
    }


def travel_plan_payload(plan):
    """Keep datetimes for exports/calculation; preserve market offsets at the JSON boundary."""
    if plan is None:
        return None
    zone = plan["timezone"]
    fields = ("departs_at", "arrives_at", "scheduled_departs_at", "scheduled_arrives_at")
    return {**plan, "generated_at": local_iso(plan["generated_at"], zone),
            "legs": [{**leg, **{field: local_iso(leg[field], zone) for field in fields}} for leg in plan["legs"]]}


def upcoming_plan(user):
    now = timezone.now()
    # Operator delays are capped at 12 hours. Include yesterday's snapshots so a
    # delayed arrival does not disappear when its originally booked time passes.
    candidates = Booking.objects.filter(
        user=user, status=Booking.Status.CONFIRMED,
        legs__status="booked", legs__arrives_at__gt=now - timedelta(days=1),
    ).distinct()
    plans = [travel_plan(b, now=now) for b in candidates]
    plans = [p for p in plans if p["legs"] and p["progress"] != "finished"]
    return min(plans, key=lambda p: (p["legs"][0]["departs_at"], p["reference"]), default=None)
