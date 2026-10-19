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

from . import recovery
from .services import assess


def _leg_row(l):
    return {"sequence": l.sequence, "mode": l.mode, "route_code": l.route_code, "from": l.from_name, "to": l.to_name,
            "departs_at": timezone.localtime(l.departs_at), "arrives_at": timezone.localtime(l.arrives_at)}


def offer_payload(o):
    diff = o.difference
    return {
        "id": o.pk, "status": o.status, "expires_at": timezone.localtime(o.expires_at),
        "arrives_at": timezone.localtime(o.arrives_at), "legs": o.legs_snapshot, "legs_param": o.legs_param,
        "replacement_price": f"{o.total_new:.2f}", "replaced_value": f"{o.replaced_value:.2f}", "currency": o.currency,
        "difference": f"{diff:.2f}", "settlement": "pay" if diff > 0 else "refund" if diff < 0 else "none",
        "reserves_capacity": False,
        "availability_warning": "Places are not held until you accept. Availability and price are checked again at that moment.",
    }


@extend_schema(responses={200: dict})
@api_view(["GET"])
def replacements(request, reference):
    """Replacement options for a disrupted booking (refreshes them first). Offers do not reserve places."""
    b = _own_booking(request, reference)
    state, offers = recovery.ensure_offers(b.pk)
    b = _own_booking(request, reference)
    live = assess(b) if b.status == Booking.Status.CONFIRMED else None
    out = {"state": state, "offers": [offer_payload(o) for o in offers], "retained_legs": [], "affected_legs": [], "original_arrival": None}
    if live and live.status == "broken":
        by_seq = {l.sequence: l for l in b.legs.filter(status=BookingLeg.Status.BOOKED)}
        out["retained_legs"] = [_leg_row(by_seq[s]) for s in sorted(by_seq) if s < live.problem_sequence]
        out["affected_legs"] = [_leg_row(by_seq[s]) for s in sorted(by_seq) if s >= live.problem_sequence]
        out["original_arrival"] = timezone.localtime(by_seq[max(by_seq)].arrives_at)
        out["reason"] = live.reason
        if state == "none":
            out["cancellation"] = _quote_payload(refund_quote(b))
    return Response(out)


class AcceptIn(serializers.Serializer):
    outcome = serializers.ChoiceField(choices=["success", "failure"], default="success", help_text="Simulator only (top-up payment).")


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
                                    outcome=data.validated_data["outcome"])
    except recovery.RecoveryError as e:
        raise Conflict(e.code, e.message, **e.extra) from e
    if res is None:
        raise Http404
    offer, replayed = res
    return Response({"replayed": replayed, "offer": offer_payload(offer), "booking": booking_payload(_own_booking(request, reference))})


@extend_schema(request=None, responses={200: dict})
@api_view(["POST"])
def decline(request, reference, offer_id):
    offer = recovery.decline_offer(user=request.user, reference=reference, offer_id=offer_id)
    if offer is None:
        raise Http404
    return Response(offer_payload(offer))
