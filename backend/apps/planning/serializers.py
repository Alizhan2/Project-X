from django.utils import timezone
from rest_framework import serializers

from apps.transport.models import Stop


class StopSerializer(serializers.ModelSerializer):
    hub = serializers.CharField(source="hub.name", default=None, read_only=True)

    class Meta:
        model = Stop
        fields = ["code", "name", "kind", "hub", "step_free"]


def _tri(value):
    return "unknown" if value is None else ("yes" if value else "no")


def serialize_leg(leg, passengers):
    dep = leg.departure
    wheelchair = leg.wheelchair_accessible
    return {
        "kind": "taxi" if leg.taxi else "service",
        "departure_id": dep.pk if dep else None,
        "taxi_offer_id": leg.taxi.pk if leg.taxi else None,
        "mode": leg.mode,
        "operator": leg.operator_name,
        "route_code": leg.route_code,
        "route_name": leg.route_name,
        "from": {"code": leg.from_stop.code, "name": leg.from_stop.name},
        "to": {"code": leg.to_stop.code, "name": leg.to_stop.name},
        "departs_at": timezone.localtime(leg.departs_at),
        "arrives_at": timezone.localtime(leg.arrives_at),
        "status": dep.status if dep else "scheduled",
        "delay_minutes": dep.delay_minutes if dep else 0,
        "unit_price": f"{leg.unit_price:.2f}",
        "price_basis": leg.price_basis,
        "leg_total": f"{leg.total(passengers):.2f}",
        "places_left": dep.places_left if dep else None,
        "accessibility": {
            "wheelchair_vehicle": _tri(wheelchair),
            "origin_step_free": _tri(leg.from_stop.step_free),
            "destination_step_free": _tri(leg.to_stop.step_free),
        },
        "cancellation_policy": leg.policy.name,
    }


def serialize_itinerary(it):
    return {
        "departs_at": timezone.localtime(it.departs_at),
        "arrives_at": timezone.localtime(it.arrives_at),
        "duration_minutes": it.duration_minutes,
        "transfers": it.transfers,
        "min_transfer_buffer_minutes": it.min_transfer_buffer_minutes,
        "transfer_buffers": it.buffers or [],
        "passengers": it.passengers,
        "total_price": f"{it.total_price:.2f}",
        "currency": it.currency,
        "legs_param": it.legs_param,
        "selection": [l.selection for l in it.legs],
        "legs": [serialize_leg(l, it.passengers) for l in it.legs],
    }
