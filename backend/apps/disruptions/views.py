from datetime import datetime
from zoneinfo import ZoneInfo

from django.conf import settings
from django.http import Http404
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.decorators import api_view
from rest_framework.response import Response

from apps.bookings.models import Booking, BookingLeg
from apps.bookings.services import refund_quote
from apps.bookings.views import Conflict, _own_booking, _quote_payload, booking_payload, idempotency_key

from apps.core.throttling import throttle
from apps.transport.markets import booking_timezone, local_iso, timezone_for_stops

from . import recovery
from .services import assess


def _leg_row(l):
    zone = timezone_for_stops(l.from_stop, l.to_stop)
    return {"sequence": l.sequence, "mode": l.mode, "route_code": l.route_code, "from": l.from_name, "to": l.to_name, "from_code": l.from_stop.code, "to_code": l.to_stop.code,
            "timezone": zone, "departs_at": local_iso(l.departs_at, zone), "arrives_at": local_iso(l.arrives_at, zone)}


def offer_payload(o):
    from apps.planning.transfers import load_transfer_rules, assess_connection
    from apps.transport.models import Stop
    stops = {stop.code: stop for stop in Stop.objects.all()}
    rules = load_transfer_rules()
    connections = [assess_connection(stops[a["to"]["code"]], stops[b["from"]["code"]],
                     datetime.fromisoformat(a["arrives_at"]), datetime.fromisoformat(b["departs_at"]),
                     rules, on_demand=b["mode"] == "taxi") for a,b in zip(o.legs_snapshot, o.legs_snapshot[1:])]
    diff = o.difference
    zone = booking_timezone(o.booking)
    return {
        "id": o.pk, "status": o.status, "expires_at": local_iso(o.expires_at, zone), "timezone": zone,
        "arrives_at": local_iso(o.arrives_at, zone), "legs": o.legs_snapshot, "legs_param": o.legs_param,
        "replacement_price": f"{o.total_new:.2f}", "replaced_value": f"{o.replaced_value:.2f}", "currency": o.currency,
        "difference": f"{diff:.2f}", "settlement": "pay",
        "payment_now": f"{o.total_new:.2f}", "eligible_refund": f"{o.eligible_refund:.2f}", "net_extra_cost": f"{diff:.2f}",
        "refund_status": o.booking.refunds.filter(key=f"replacement:{o.pk}").values_list("status", flat=True).first(),
        "retained_legs": [_leg_row(l) for l in o.booking.legs.filter(status="booked").exclude(sequence__in=o.constraints_snapshot.get("replaced_sequences", []))],
        "affected_legs": [_leg_row(l) for l in o.booking.legs.filter(sequence__in=o.constraints_snapshot.get("replaced_sequences", []))],
        "reserves_capacity": False, "connections": connections,
        "availability_warning": "Places are not held until you accept. Availability and price are checked again at that moment.",
    }


class RecoveryPreferences(serializers.Serializer):
    origin = serializers.CharField(required=False, max_length=16)
    earliest_departure = serializers.DateTimeField(required=False)
    latest_arrival = serializers.DateTimeField(required=False)
    max_payment_now = serializers.IntegerField(required=False, min_value=0)
    wheelchair_required = serializers.BooleanField(required=False)

    def validate(self, attrs):
        earliest = attrs.get("earliest_departure", timezone.now())
        if "latest_arrival" in attrs and attrs["latest_arrival"] < earliest:
            raise serializers.ValidationError({"latest_arrival": "Arrival deadline must not be before earliest departure."})
        return attrs


@extend_schema(parameters=[RecoveryPreferences], responses={200: dict})
@api_view(["GET"])
def replacements(request, reference):
    b = _own_booking(request, reference)
    zone = booking_timezone(b)
    data = RecoveryPreferences(data=request.query_params.dict())
    for field in ("earliest_departure", "latest_arrival"):
        data.fields[field].timezone = ZoneInfo(zone)
    data.is_valid(raise_exception=True)
    prefs = data.validated_data
    try:
        state, offers = recovery.ensure_offers(b.pk, constraints=prefs)
        b = _own_booking(request, reference)
        live = assess(b) if b.status == Booking.Status.CONFIRMED else None
        kept, affected, _, constraints, locations = recovery.recovery_context(b, live, timezone.now(), prefs) if live and live.status == "broken" else ([], [], None, {}, [])
    except recovery.RecoveryError as exc:
        raise Conflict(exc.code, exc.message) from exc
    constraints = {**constraints, **{key: local_iso(datetime.fromisoformat(constraints[key]), zone)
                                   for key in ("earliest_departure", "reachable_after", "latest_arrival") if key in constraints}}
    out = {"state": state, "timezone": zone, "offers": [offer_payload(o) for o in offers],
           "retained_legs": [_leg_row(ll.leg) for ll in kept], "affected_legs": [_leg_row(ll.leg) for ll in affected],
           "original_arrival": None, "constraints": constraints, "locations": locations}
    if live and live.status == "broken":
        out["original_arrival"] = local_iso(live.legs[-1].leg.arrives_at, zone)
        out["reason"] = live.reason
        if state == "none":
            out["cancellation"] = _quote_payload(refund_quote(b))
    return Response(out)


class AcceptIn(serializers.Serializer):
    reconcile = serializers.BooleanField(default=False)
    outcome = serializers.ChoiceField(choices=["success", "failure", "pending"], default="success", help_text="Simulator only (full replacement payment).")


@extend_schema(
    request=AcceptIn, responses={200: dict, 409: dict},
    parameters=[OpenApiParameter("Idempotency-Key", str, OpenApiParameter.HEADER, required=True)],
)
@throttle("booking")
@api_view(["POST"])
def accept(request, reference, offer_id):
    if not settings.SIMULATION_ENABLED:   # replacement settlement uses the payment/refund simulator
        return Response({"code": "payments_not_configured", "message": "Payments are not available in this deployment."}, status=503)
    key = idempotency_key(request)
    data = AcceptIn(data=request.data)
    data.is_valid(raise_exception=True)
    try:
        res = recovery.accept_offer(user=request.user, reference=reference, offer_id=offer_id, idempotency_key=key,
                                    outcome=data.validated_data["outcome"], reconcile=data.validated_data["reconcile"])
    except recovery.RecoveryError as e:
        raise Conflict(e.code, e.message, **e.extra) from e
    if res is None:
        raise Http404
    offer, replayed = res
    return Response({"replayed": replayed, "offer": offer_payload(offer), "booking": booking_payload(_own_booking(request, reference))})


@extend_schema(request=None, responses={200: dict})
@api_view(["POST"])
def decline(request, reference, offer_id):
    try:
        offer = recovery.decline_offer(user=request.user, reference=reference, offer_id=offer_id)
    except recovery.RecoveryError as exc:
        raise Conflict(exc.code, exc.message) from exc
    if offer is None:
        raise Http404
    return Response(offer_payload(offer))
