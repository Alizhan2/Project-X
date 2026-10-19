"""Operator workspace API. Every query is scoped to the caller's own operator; other operators' objects are 404."""

from datetime import timedelta
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import APIException, PermissionDenied
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response

from apps.core.models import AuditRecord
from apps.disruptions import services as disruptions
from apps.disruptions.models import DisruptionEvent

from .models import Departure, Fare, Route


class IsOperator(BasePermission):
    message = "Operator access only."

    def has_permission(self, request, view):
        u = request.user
        return bool(u and u.is_authenticated and u.role == "operator" and hasattr(u, "membership"))


class Conflict(APIException):
    status_code = 409

    def __init__(self, code, message):
        super().__init__({"code": code, "message": message})


def operator_of(request):
    return request.user.membership.operator


def own_departures(request):
    return Departure.objects.filter(route__operator=operator_of(request)).select_related("route")


def dep_payload(d):
    local = timezone.localtime
    last = d.route.route_stops.order_by("-sequence").first()
    first = d.route.route_stops.order_by("sequence").first()
    return {
        "id": d.pk, "route_code": d.route.code, "route_name": d.route.name, "mode": d.route.mode,
        "departs_at": local(d.departs_at), "status": d.status, "delay_minutes": d.delay_minutes,
        "capacity": d.capacity, "places_taken": d.places_taken,
        "wheelchair_accessible": d.wheelchair_accessible,
        "first_stop": first.stop.name, "last_stop": last.stop.name,
        "ends_at": local(d.departs_at + timedelta(minutes=last.arrival_offset_min + d.delay_minutes)),
    }


def impact_payload(impacts):
    """Operator-appropriate detail: reference, passenger count and effect. No contact data, no prices."""
    return [{
        "reference": i["booking"].reference, "passengers": i["booking"].passengers, "booking_status": i["booking"].status,
        "before": i["before"], "after": i["after"], "reason": i["reason"], "arrival_delay_minutes": i["arrival_delay_minutes"],
    } for i in impacts]


class ServiceIn(serializers.Serializer):
    route_id = serializers.IntegerField(required=False)
    departs_at = serializers.DateTimeField(required=False)
    capacity = serializers.IntegerField(min_value=1, max_value=500, required=False)
    wheelchair_accessible = serializers.BooleanField(required=False, allow_null=True)


@extend_schema(responses={200: dict})
@api_view(["GET"])
@permission_classes([IsOperator])
def routes(request):
    op = operator_of(request)
    out = []
    for r in Route.objects.filter(operator=op).prefetch_related("fares__from_stop", "fares__to_stop"):
        out.append({
            "id": r.pk, "code": r.code, "name": r.name, "mode": r.mode,
            "fares": [{"id": f.pk, "from": f.from_stop.name, "to": f.to_stop.name, "price": f"{f.price:.2f}", "currency": f.currency}
                      for f in r.fares.all()],
        })
    return Response({"operator": op.name, "results": out})


@extend_schema(methods=["GET"], responses={200: dict}, operation_id="operator_services_list")
@extend_schema(methods=["POST"], request=ServiceIn, responses={201: dict}, operation_id="operator_services_create")
@api_view(["GET", "POST"])
@permission_classes([IsOperator])
def services(request):
    if request.method == "GET":
        qs = own_departures(request)
        start = request.query_params.get("from")
        qs = qs.filter(departs_at__gte=start) if start else qs.filter(departs_at__gte=timezone.now() - timedelta(hours=6))
        if request.query_params.get("route"):
            qs = qs.filter(route__code=request.query_params["route"])
        return Response({"results": [dep_payload(d) for d in qs.order_by("departs_at")[:200]]})
    data = ServiceIn(data=request.data)
    data.is_valid(raise_exception=True)
    v = data.validated_data
    if not {"route_id", "departs_at", "capacity"} <= v.keys():
        raise serializers.ValidationError({"detail": "route_id, departs_at and capacity are required."})
    route = get_object_or_404(Route, pk=v["route_id"], operator=operator_of(request))  # not yours => 404
    try:
        with transaction.atomic():
            d = Departure.objects.create(route=route, departs_at=v["departs_at"], capacity=v["capacity"],
                                         wheelchair_accessible=v.get("wheelchair_accessible"))
    except IntegrityError:
        raise serializers.ValidationError({"departs_at": "This route already has a service at that time."})
    AuditRecord.objects.create(actor=request.user, action="service.created", object_type="departure", object_id=str(d.pk), detail={"route": route.code})
    return Response(dep_payload(d), status=201)


@extend_schema(methods=["GET"], responses={200: dict}, operation_id="operator_service_detail")
@extend_schema(methods=["PATCH"], request=ServiceIn, responses={200: dict}, operation_id="operator_service_update")
@api_view(["GET", "PATCH"])
@permission_classes([IsOperator])
def service_detail(request, pk):
    if request.method == "GET":
        d = get_object_or_404(own_departures(request), pk=pk)
        events = [{"kind": e.kind, "delay_minutes": e.delay_minutes, "affected_bookings": e.affected_bookings,
                   "created_at": timezone.localtime(e.created_at)} for e in d.disruption_events.all()[:20]]
        return Response({**dep_payload(d), "events": events})
    data = ServiceIn(data=request.data, partial=True)
    data.is_valid(raise_exception=True)
    v = data.validated_data
    with transaction.atomic():
        d = get_object_or_404(own_departures(request).select_for_update(of=("self",)), pk=pk)
        if "capacity" in v:
            if v["capacity"] < d.places_taken:
                raise serializers.ValidationError({"capacity": f"{d.places_taken} places are already booked; capacity cannot go below that."})
            d.capacity = v["capacity"]
        if "wheelchair_accessible" in v:
            d.wheelchair_accessible = v["wheelchair_accessible"]
        if "departs_at" in v and v["departs_at"] != d.departs_at:
            if d.places_taken or d.booking_legs.exists():
                raise Conflict("has_bookings", "This service has bookings. Use a delay or cancellation instead of moving it.")
            d.departs_at = v["departs_at"]
        try:
            d.save()
        except IntegrityError:
            raise serializers.ValidationError({"departs_at": "This route already has a service at that time."})
        AuditRecord.objects.create(actor=request.user, action="service.edited", object_type="departure", object_id=str(d.pk),
                                   detail={k: str(x) for k, x in v.items()})
    return Response(dep_payload(d))


class FareIn(serializers.Serializer):
    price = serializers.DecimalField(max_digits=8, decimal_places=2, min_value=Decimal("0.01"))


@extend_schema(request=FareIn, responses={200: dict})
@api_view(["PATCH"])
@permission_classes([IsOperator])
def fare_detail(request, pk):
    """Changes the *current* fare only. Existing bookings keep the price they paid (snapshots)."""
    fare = get_object_or_404(Fare, pk=pk, route__operator=operator_of(request))
    data = FareIn(data=request.data)
    data.is_valid(raise_exception=True)
    old, fare.price = fare.price, data.validated_data["price"]
    fare.save(update_fields=["price"])
    AuditRecord.objects.create(actor=request.user, action="fare.changed", object_type="fare", object_id=str(fare.pk),
                               detail={"from": str(old), "to": str(fare.price)})
    return Response({"id": fare.pk, "price": f"{fare.price:.2f}"})


class ChangeIn(serializers.Serializer):
    action = serializers.ChoiceField(choices=["delay", "cancel"])
    minutes = serializers.IntegerField(min_value=0, max_value=disruptions.MAX_DELAY_MINUTES, required=False, default=0)


@extend_schema(request=ChangeIn, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsOperator])
def service_impact(request, pk):
    """Preview the consequences of a delay/cancellation. Changes nothing."""
    d = get_object_or_404(own_departures(request), pk=pk)
    data = ChangeIn(data=request.data)
    data.is_valid(raise_exception=True)
    impacts = disruptions.preview_impact(d, data.validated_data["action"], data.validated_data["minutes"])
    rows = impact_payload(impacts)
    return Response({
        "affected": rows, "passengers": sum(r["passengers"] for r in rows),
        "broken": sum(1 for r in rows if r["after"] == "broken"),
    })


@extend_schema(request=ChangeIn, responses={200: dict})
@api_view(["POST"])
@permission_classes([IsOperator])
def service_change(request, pk):
    """Apply a delay (minutes = new total delay, 0 clears it) or a cancellation. Idempotent."""
    d = get_object_or_404(own_departures(request), pk=pk)
    data = ChangeIn(data=request.data)
    data.is_valid(raise_exception=True)
    try:
        event, noop = disruptions.apply_change(
            actor=request.user, departure_id=d.pk, action=data.validated_data["action"], minutes=data.validated_data["minutes"])
    except disruptions.ChangeError as e:
        raise Conflict(e.code, e.message) from e
    d.refresh_from_db()
    return Response({"noop": noop, "affected_bookings": event.affected_bookings if event else 0, "service": dep_payload(d)})
