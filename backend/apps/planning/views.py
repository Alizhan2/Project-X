from datetime import datetime, timezone as datetime_timezone

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
        OpenApiParameter("depart_after", str, description="ISO datetime. Provide exactly one of depart_after or arrive_by; naive values use Europe/Berlin."),
        OpenApiParameter("arrive_by", str, description="Arrival deadline (inclusive); searches departures in the preceding 24 hours. Defaults to latest_departure sorting."),
        OpenApiParameter("passengers", int, description="1-9, default 1"),
        OpenApiParameter("modes", str, description="Comma-separated allowed modes: bus,train,taxi. Default all; every leg must match."),
        OpenApiParameter("max_transfers", str, enum=["any", "0", "1", "2"], description="Maximum changes; any defaults to 2."),
        OpenApiParameter("max_connection_minutes", int, description="Optional 5-180 minute cap from arrival to the next departure, including walking."),
        OpenApiParameter("sort", str, enum=list(services.SORTS), description="Default departure for depart_after, latest_departure for arrive_by. Also price, duration and buffer."),
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
    time_field = "arrive_by" if "arrive_by" in q else "depart_after"
    if "arrive_by" in q and "depart_after" in q:
        errors["arrive_by"] = "Choose either depart_after or arrive_by, not both."
    try:
        search_time = datetime.fromisoformat(q.get(time_field, ""))
        if timezone.is_naive(search_time):
            search_time = timezone.make_aware(search_time)
            if time_field == "arrive_by" and search_time.astimezone(datetime_timezone.utc).astimezone(timezone.get_current_timezone()).replace(tzinfo=None) != search_time.replace(tzinfo=None):
                errors[time_field] = "This local time does not exist because the clocks change. Choose another time."
            elif time_field == "arrive_by" and search_time.utcoffset() != search_time.replace(fold=1).utcoffset():
                errors[time_field] = "This local time occurs twice because the clocks change. Choose another time or supply an explicit UTC offset."
        if time_field == "arrive_by" and search_time <= timezone.now():
            errors[time_field] = "Choose an arrival deadline in the future."
    except ValueError:
        errors[time_field] = "Required ISO 8601 date and time."
    sort = q.get("sort", "latest_departure" if time_field == "arrive_by" else "departure")
    if sort not in services.SORTS:
        errors["sort"] = f"Must be one of: {', '.join(services.SORTS)}."
    modes = frozenset(q.get("modes", "bus,train,taxi").split(","))
    if not modes or not modes <= {"bus", "train", "taxi"}:
        errors["modes"] = "Choose at least one of: bus, train, taxi."
    transfers = q.get("max_transfers", "any")
    if transfers not in {"any", "0", "1", "2"}:
        errors["max_transfers"] = "Must be any, 0, 1 or 2."
    connection = None
    if q.get("max_connection_minutes"):
        try:
            connection = int(q["max_connection_minutes"])
            if not 5 <= connection <= 180:
                raise ValueError
        except ValueError:
            errors["max_connection_minutes"] = "Must be a whole number from 5 to 180."
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
    planner = services.search_arrive_by if time_field == "arrive_by" else services.search
    results = planner(found["origin"], found["destination"], search_time, passengers, sort,
                              max_legs=3 if transfers == "any" else int(transfers) + 1,
                              modes=modes, max_connection_minutes=connection)
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
        OpenApiParameter("arrive_by", str, description="Optional arrival deadline to revalidate against current times."),
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
    if "arrive_by" in request.query_params:
        field = serializers.DateTimeField()
        try:
            deadline = field.run_validation(request.query_params["arrive_by"])
        except serializers.ValidationError as e:
            raise ValidationError({"arrive_by": e.detail}) from e
        if it.arrives_at > deadline:
            return Response({"code": "arrival_deadline_missed", "message": "This journey no longer arrives by your chosen time. Search again."}, status=409)
    return Response({"simulated": True, **serialize_itinerary(it)})


@extend_schema(
    parameters=[
        OpenApiParameter("origin", str, required=True, description="Stop code"),
        OpenApiParameter("destination", str, required=True, description="Stop code"),
        OpenApiParameter("date", str, required=True, description="Centre day, YYYY-MM-DD (demo timezone)"),
        OpenApiParameter("time", str, description="Earliest departure each day, HH:MM (default 00:00)"),
        OpenApiParameter("passengers", int, description="1-9, default 1"),
        OpenApiParameter("modes", str, description="Comma-separated allowed modes: bus,train,taxi"),
        OpenApiParameter("span", int, description="Days either side of `date`, 0-3 (default 3)"),
    ],
    responses={200: dict},
)
@throttle("search")
@api_view(["GET"])
@permission_classes([AllowAny])
def search_days(request):
    """Cheapest and fastest journey per day around a date (a price calendar). Uses the same planner as /search/,
    so every number matches what the passenger will see after choosing that day. Past days have no journeys."""
    from datetime import date as date_type, time as time_type, timedelta

    q = request.query_params
    errors = {}
    try:
        passengers = int(q.get("passengers", 1))
        if not 1 <= passengers <= services.MAX_PASSENGERS:
            raise ValueError
    except ValueError:
        errors["passengers"] = f"Must be a whole number from 1 to {services.MAX_PASSENGERS}."
    try:
        centre = date_type.fromisoformat(q.get("date", ""))
    except ValueError:
        errors["date"] = "Required date, YYYY-MM-DD."
    try:
        start_time = time_type.fromisoformat(q.get("time", "00:00"))
    except ValueError:
        errors["time"] = "Must be HH:MM."
    try:
        span = int(q.get("span", 3))
        if not 0 <= span <= 3:
            raise ValueError
    except ValueError:
        errors["span"] = "Must be a whole number from 0 to 3."
    modes = frozenset(q.get("modes", "bus,train,taxi").split(","))
    if not modes <= {"bus", "train", "taxi"}:
        errors["modes"] = "Choose from: bus, train, taxi."
    found = {}
    for field in ("origin", "destination"):
        found[field] = Stop.objects.filter(code=q.get(field, "")).first()
        if found[field] is None:
            errors[field] = "Unknown stop code."
    if not errors and found["origin"].pk == found["destination"].pk:
        errors["destination"] = "Destination must differ from origin."
    if errors:
        raise ValidationError(errors)
    days = []
    now = timezone.now()
    for offset in range(-span, span + 1):
        day = centre + timedelta(days=offset)
        start = timezone.make_aware(datetime.combine(day, start_time))
        results = services.search(found["origin"], found["destination"], start, passengers, "price", now=now, modes=modes)
        days.append({
            "date": day.isoformat(),
            "count": len(results),
            "cheapest_price": f"{min(r.total_price for r in results):.2f}" if results else None,
            "fastest_minutes": min(r.duration_minutes for r in results) if results else None,
            "currency": results[0].currency if results else None,
        })
    return Response({"simulated": True, "days": days})
