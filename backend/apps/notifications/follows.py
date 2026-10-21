"""Follow a line: delay/cancellation notices for upcoming services without owning a booking."""

from datetime import timedelta

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.models import User
from apps.core.throttling import throttle
from apps.transport.models import Route

from .models import LineFollow
from .services import notify

MAX_FOLLOWS = 10
NOTIFY_HORIZON = timedelta(hours=48)     # only services leaving soon are worth an alert


class FollowIn(serializers.Serializer):
    route_code = serializers.CharField(max_length=16)


def payload(f):
    r = f.route
    stops = list(r.route_stops.select_related("stop").order_by("sequence"))
    return {"id": f.pk, "route_code": r.code, "route_name": r.name, "mode": r.mode, "operator": r.operator.name,
            "from": stops[0].stop.name if stops else "", "to": stops[-1].stop.name if stops else ""}


@extend_schema(methods=["GET"], responses={200: dict})
@extend_schema(methods=["POST"], request=FollowIn, responses={200: dict, 201: dict})
@throttle("booking")
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def collection(request):
    qs = LineFollow.objects.filter(user=request.user).select_related("route__operator")
    if request.method == "GET":
        return Response({"max_follows": MAX_FOLLOWS, "results": [payload(f) for f in qs]})
    data = FollowIn(data=request.data)
    data.is_valid(raise_exception=True)
    route = Route.objects.filter(code=data.validated_data["route_code"]).select_related("operator").first()
    if route is None:
        raise ValidationError({"route_code": "Unknown line."})
    with transaction.atomic():
        User.objects.select_for_update().get(pk=request.user.pk)        # per-account: limit and de-duplication stay exact
        existing = LineFollow.objects.filter(user=request.user, route=route).first()
        if existing:
            return Response(payload(existing))
        if LineFollow.objects.filter(user=request.user).count() >= MAX_FOLLOWS:
            raise ValidationError({"detail": f"You can follow up to {MAX_FOLLOWS} lines. Unfollow one before adding another."})
        follow = LineFollow.objects.create(user=request.user, route=route)
    return Response(payload(follow), status=201)


@extend_schema(responses={204: None})
@throttle("booking")
@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def remove(request, pk):
    get_object_or_404(LineFollow, pk=pk, user=request.user).delete()    # someone else's id behaves like a missing one
    return Response(status=204)


def notify_followers(departure, kind, delay_minutes, event_pk, exclude_user_ids=(), now=None):
    """Tell followers of `departure.route` about a change to this service. Followers who hold a booking on it get the
    booking-specific notice instead (passed in `exclude_user_ids`). Idempotent per (event, user)."""
    now = now or timezone.now()
    if departure.departs_at > now + NOTIFY_HORIZON:
        return 0
    route = departure.route
    when = timezone.localtime(departure.departs_at)
    first = route.route_stops.select_related("stop").order_by("sequence").first()
    origin = first.stop.name if first else route.name
    if kind == "cancel":
        title, body = f"Line {route.code}: cancelled", f"The {when:%a %d %b %H:%M} departure from {origin} is cancelled."
    elif kind == "delay":
        title, body = f"Line {route.code}: delayed by {delay_minutes} min", f"The {when:%a %d %b %H:%M} departure from {origin} is delayed by {delay_minutes} minutes."
    else:
        title, body = f"Line {route.code}: back on time", f"The {when:%a %d %b %H:%M} departure from {origin} is running to its timetable again."
    sent = 0
    for follow in LineFollow.objects.filter(route=route).exclude(user_id__in=exclude_user_ids).select_related("user"):
        if notify(follow.user, f"line_{kind}", title, body + " You are following this line. Simulated demonstration data.",
                  dedupe_key=f"follow:{event_pk}:{follow.pk}", link="/alerts"):
            sent += 1
    return sent
