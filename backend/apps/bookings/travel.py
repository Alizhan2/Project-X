"""Read-only, current timetable view. Never rewrites the purchase snapshots."""
from datetime import timedelta

from django.utils import timezone

from apps.disruptions.services import assess
from .models import Booking


def travel_plan(booking, assessment=None, now=None):
    now = now or timezone.now()
    assessment = assessment or assess(booking)
    legs = []
    for item in assessment.legs:
        leg = item.leg
        state = ("completed" if item.arrives_at <= now else
                 "travelling" if item.departs_at <= now else "upcoming")
        if item.cancelled or item.taxi_unavailable:
            state = "unavailable"
        legs.append({
            "sequence": leg.sequence, "from": leg.from_name, "to": leg.to_name,
            "mode": leg.mode, "route_code": leg.route_code, "operator": leg.operator_name,
            "departs_at": timezone.localtime(item.departs_at), "arrives_at": timezone.localtime(item.arrives_at),
            "scheduled_departs_at": timezone.localtime(leg.departs_at), "scheduled_arrives_at": timezone.localtime(leg.arrives_at),
            "state": state,
        })
    remaining = [leg for leg in legs if leg["arrives_at"] > now]
    return {
        "reference": booking.reference, "generated_at": timezone.localtime(now),
        "status": assessment.status, "reason": assessment.reason,
        "progress": "finished" if not remaining else (
            "needs_attention" if assessment.status == "broken" else
            "in_progress" if legs[0]["departs_at"] <= now else "upcoming"),
        "next_sequence": remaining[0]["sequence"] if remaining else None,
        "legs": legs,
        "notice": "Timetable estimate, not GPS tracking. All transport and tickets are simulated.",
    }


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
