from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.decorators import api_view
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.response import Response

from apps.core.throttling import throttle

from . import services
from .models import Booking


class Conflict(APIException):
    status_code = 409
    default_code = "conflict"

    def __init__(self, code, message, **extra):
        super().__init__({"code": code, "message": message, **extra})


def idempotency_key(request):
    key = request.headers.get("Idempotency-Key", "").strip()
    if not (8 <= len(key) <= 64):
        raise ValidationError({"idempotency_key": "Send an Idempotency-Key header (8-64 characters)."})
    return key


class LegIn(serializers.Serializer):
    """A bus/train leg (`departure_id`) or a simulated taxi leg (`taxi_offer_id` + `ready_at`)."""

    departure_id = serializers.IntegerField(required=False)
    taxi_offer_id = serializers.IntegerField(required=False)
    ready_at = serializers.DateTimeField(required=False, help_text="Taxi as first leg: when the passenger is ready")
    from_stop = serializers.CharField(help_text="Stop code")
    to_stop = serializers.CharField(help_text="Stop code")

    def validate(self, attrs):
        if ("departure_id" in attrs) == ("taxi_offer_id" in attrs):
            raise serializers.ValidationError("Give exactly one of departure_id or taxi_offer_id.")
        return attrs


class CheckoutIn(serializers.Serializer):
    passengers = serializers.IntegerField(min_value=1, max_value=9)
    legs = LegIn(many=True, allow_empty=False, max_length=3)
    expected_total = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    contact_email = serializers.EmailField()
    travellers = serializers.ListField(child=serializers.CharField(max_length=150, allow_blank=False))

    def validate(self, attrs):
        names = [n.strip() for n in attrs["travellers"]]
        if len(names) != attrs["passengers"] or not all(names):
            raise serializers.ValidationError({"travellers": "Enter a name for each passenger."})
        attrs["travellers"] = names
        return attrs


def _selection(leg):
    item = dict(leg)
    if "ready_at" in item:
        item["ready_at"] = item["ready_at"].isoformat()
    return item


def booking_payload(b):
    from apps.disruptions.services import assess  # local import: disruptions depends on bookings

    live = assess(b) if b.status == Booking.Status.CONFIRMED else None
    return {
        "disruption": None if live is None else {
            "status": live.status, "reason": live.reason, "problem_sequence": live.problem_sequence,
            "arrival_delay_minutes": live.arrival_delay_minutes,
        },
        "cancellable": b.status in (Booking.Status.CONFIRMED, Booking.Status.PENDING_PAYMENT),
        "refunds": [
            {"status": r.status, "amount": f"{r.amount:.2f}", "reason": r.get_reason_display(), "created_at": timezone.localtime(r.created_at)}
            for r in b.refunds.all()
        ],
        "reference": b.reference,
        "status": b.status,
        "status_label": b.get_status_display(),
        "passengers": b.passengers,
        "total_amount": f"{b.total_amount:.2f}",
        "currency": b.currency,
        "contact_email": b.contact_email,
        "expires_at": timezone.localtime(b.expires_at),
        "created_at": timezone.localtime(b.created_at),
        "confirmed_at": timezone.localtime(b.confirmed_at) if b.confirmed_at else None,
        "simulated_notice": "Simulated booking for demonstration. Not a valid travel ticket.",
        "travellers": [t.full_name for t in b.travellers.all()],
        "legs": [
            {
                "sequence": l.sequence, "status": l.status, "mode": l.mode, "operator": l.operator_name,
                "route_code": l.route_code, "route_name": l.route_name,
                "from": l.from_name, "to": l.to_name,
                "from_code": l.from_stop.code, "to_code": l.to_stop.code,
                "departs_at": timezone.localtime(l.departs_at), "arrives_at": timezone.localtime(l.arrives_at),
                "unit_price": f"{l.unit_price:.2f}", "price_basis": l.price_basis, "cancellation_policy": l.policy_name,
            }
            for l in b.legs.all()
        ],
        "payments": [
            {"status": p.status, "purpose": p.purpose, "amount": f"{p.amount:.2f}", "failure_reason": p.failure_reason,
             "created_at": timezone.localtime(p.created_at)}
            for p in b.payment_attempts.all()
        ],
    }


def _own_booking(request, reference):
    """Object-level ownership: other users' bookings behave exactly like nonexistent ones (404)."""
    qs = Booking.objects.filter(user=request.user).prefetch_related("legs__from_stop", "legs__to_stop", "travellers", "payment_attempts", "refunds")
    return get_object_or_404(qs, reference=reference)


@extend_schema(
    methods=["POST"], request=CheckoutIn,
    parameters=[OpenApiParameter("Idempotency-Key", str, OpenApiParameter.HEADER, required=True)],
    responses={201: dict, 200: dict, 409: dict},
)
@extend_schema(methods=["GET"], operation_id="bookings_list", responses=inline_serializer("BookingList", {"results": serializers.ListField(child=serializers.DictField())}))
@throttle("booking")
@api_view(["GET", "POST"])
def bookings(request):
    """POST: revalidate the selected legs, hold capacity, create a pending booking (idempotent). GET: my bookings."""
    if request.method == "GET":
        services.expire_due_bookings()
        qs = Booking.objects.filter(user=request.user).prefetch_related("legs__from_stop", "legs__to_stop", "travellers", "payment_attempts", "refunds")
        return Response({"results": [booking_payload(b) for b in qs]})
    key = idempotency_key(request)
    data = CheckoutIn(data=request.data)
    data.is_valid(raise_exception=True)
    v = data.validated_data
    try:
        booking, created = services.create_booking(
            user=request.user, selection=[_selection(l) for l in v["legs"]], passengers=v["passengers"],
            traveller_names=v["travellers"], contact_email=v["contact_email"], idempotency_key=key,
            expected_total=v.get("expected_total"),
        )
    except services.BookingError as e:
        raise Conflict(e.code, e.message, **e.extra) from e
    return Response(booking_payload(_own_booking(request, booking.reference)), status=201 if created else 200)


@extend_schema(operation_id="bookings_detail", responses={200: dict})
@api_view(["GET"])
def booking_detail(request, reference):
    b = _own_booking(request, reference)
    if services.expire_booking(b.pk):
        b = _own_booking(request, reference)
    return Response(booking_payload(b))


@extend_schema(request=None, responses={200: dict, 409: dict})
@api_view(["POST"])
def booking_abandon(request, reference):
    b = _own_booking(request, reference)
    try:
        services.abandon_booking(b.pk, request.user)
    except services.BookingError as e:
        raise Conflict(e.code, e.message) from e
    return Response(booking_payload(_own_booking(request, reference)))


def _quote_payload(q):
    return {
        "disrupted": q["disrupted"],
        "total_refund": f"{q['total']:.2f}",
        "lines": [{"sequence": l["sequence"], "route_code": l["route_code"], "paid": f"{l['paid']:.2f}",
                   "percent": l["percent"], "refund": f"{l['refund']:.2f}", "reason": l["reason"]} for l in q["lines"]],
    }


@extend_schema(responses={200: dict})
@api_view(["GET"])
def booking_cancellation_quote(request, reference):
    """What cancelling now would refund, per leg, under the policy snapshotted at purchase."""
    b = _own_booking(request, reference)
    if b.status != Booking.Status.CONFIRMED:
        raise Conflict("not_cancellable", "Only a confirmed booking has a refund quote.")
    return Response(_quote_payload(services.refund_quote(b)))


class CancelIn(serializers.Serializer):
    expected_refund = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)


@extend_schema(request=CancelIn, responses={200: dict, 409: dict})
@throttle("booking")
@api_view(["POST"])
def booking_cancel(request, reference):
    """Cancel the whole journey and receive the simulated refund. Safe to repeat: never refunds twice."""
    b = _own_booking(request, reference)
    data = CancelIn(data=request.data)
    data.is_valid(raise_exception=True)
    try:
        services.cancel_booking(b.pk, request.user, data.validated_data.get("expected_refund"))
    except services.BookingError as e:
        raise Conflict(e.code, e.message, **e.extra) from e
    return Response(booking_payload(_own_booking(request, reference)))
