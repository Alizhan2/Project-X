from datetime import datetime

from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from apps.core.throttling import throttle
from apps.transport.models import Stop

from . import services
from .serializers import StopSerializer, serialize_itinerary


@extend_schema(responses=StopSerializer(many=True))
@api_view(["GET"])
@permission_classes([AllowAny])
def stops(request):
    """Controlled list of stops usable as origin/destination."""
    return Response(StopSerializer(Stop.objects.select_related("hub"), many=True).data)


@extend_schema(
    responses=inline_serializer("SearchResponse", {
        "simulated": serializers.BooleanField(),
        "window_hours": serializers.IntegerField(),
        "count": serializers.IntegerField(),
        "results": serializers.ListField(child=serializers.DictField()),
    }),
    parameters=[
        OpenApiParameter("origin", str, required=True, description="Stop code"),
        OpenApiParameter("destination", str, required=True, description="Stop code"),
        OpenApiParameter("depart_after", str, required=True, description="ISO 8601 datetime; naive values are read in the demo timezone"),
        OpenApiParameter("passengers", int, description="1-9, default 1"),
        OpenApiParameter("sort", str, enum=list(services.SORTS), description="departure (default), price, duration, buffer (largest minimum transfer buffer)"),
    ]
)
@throttle("search")
@api_view(["GET"])
@permission_classes([AllowAny])
def search(request):
    """Search direct and multi-leg (up to 3) journeys. Results are offers, not bookings; nothing is reserved."""
    q = request.query_params
    errors = {}
    try:
        passengers = int(q.get("passengers", 1))
        if not 1 <= passengers <= services.MAX_PASSENGERS:
            raise ValueError
    except ValueError:
        errors["passengers"] = f"Must be a whole number from 1 to {services.MAX_PASSENGERS}."
    try:
        depart_after = datetime.fromisoformat(q.get("depart_after", ""))
        if timezone.is_naive(depart_after):
            depart_after = timezone.make_aware(depart_after)
    except ValueError:
        errors["depart_after"] = "Required ISO 8601 date and time."
    sort = q.get("sort", "departure")
    if sort not in services.SORTS:
        errors["sort"] = f"Must be one of: {', '.join(services.SORTS)}."
    found = {}
    for field in ("origin", "destination"):
        stop = Stop.objects.filter(code=q.get(field, "")).first()
        if stop is None:
            errors[field] = "Unknown stop code."
        found[field] = stop
    if not errors and found["origin"].pk == found["destination"].pk:
        errors["destination"] = "Destination must differ from origin."
    if errors:
        raise ValidationError(errors)
    results = services.search(found["origin"], found["destination"], depart_after, passengers, sort)
    return Response({
        "simulated": True,
        "window_hours": int(services.SEARCH_WINDOW.total_seconds() // 3600),
        "count": len(results),
        "results": [serialize_itinerary(i) for i in results],
    })


def parse_legs(raw):
    """`d12:NG-BUS:RV-BUS,t3:PM-RAIL:PM-MARINA:1760000000` -> selection list.

    `d<departure_id>` = bus/train service (a bare number is accepted too); `t<taxi_offer_id>` carries the
    passenger-ready time as epoch seconds (used only when the taxi is the first leg).
    """
    out = []
    for part in raw.split(","):
        bits = part.split(":")
        head = bits[0]
        try:
            if len(bits) == 3 and head.lstrip("d").isdigit():
                out.append({"departure_id": int(head.lstrip("d")), "from_stop": bits[1], "to_stop": bits[2]})
            elif len(bits) == 4 and head.startswith("t") and head[1:].isdigit() and bits[3].isdigit():
                ready = datetime.fromtimestamp(int(bits[3]), tz=timezone.get_current_timezone())
                out.append({"taxi_offer_id": int(head[1:]), "from_stop": bits[1], "to_stop": bits[2], "ready_at": ready.isoformat()})
            else:
                raise ValueError
        except (ValueError, OverflowError, OSError):
            raise ValidationError({"legs": "Use d<id>:from:to or t<id>:from:to:epoch, comma separated."})
    if not 1 <= len(out) <= services.MAX_LEGS:
        raise ValidationError({"legs": f"A journey has 1 to {services.MAX_LEGS} legs."})
    return out


@extend_schema(
    parameters=[
        OpenApiParameter("legs", str, required=True, description="departure_id:from_stop:to_stop, comma separated"),
        OpenApiParameter("passengers", int),
    ],
    responses={200: dict, 409: dict},
)
@throttle("search")
@api_view(["GET"])
@permission_classes([AllowAny])
def itinerary(request):
    """Current, freshly computed details for a selected journey (what checkout would use)."""
    try:
        passengers = int(request.query_params.get("passengers", 1))
        assert 1 <= passengers <= services.MAX_PASSENGERS
    except (ValueError, AssertionError):
        raise ValidationError({"passengers": f"Must be a whole number from 1 to {services.MAX_PASSENGERS}."})
    selection = parse_legs(request.query_params.get("legs", ""))
    try:
        it = services.build_itinerary(selection, passengers, timezone.now())
    except services.OfferError as e:
        return Response({"code": e.code, "message": e.message}, status=409)
    if it.min_places_left is not None and it.min_places_left < passengers:
        return Response({"code": "no_capacity", "message": "Not enough places are left on this service."}, status=409)
    return Response({"simulated": True, **serialize_itinerary(it)})
