from datetime import date as date_type, time as time_type, timedelta

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
from apps.planning.services import MAX_PASSENGERS
from apps.transport.models import Stop

from . import watches
from .models import Watch


class WatchIn(serializers.Serializer):
    kind = serializers.ChoiceField(choices=Watch.Kind.values)
    origin = serializers.SlugRelatedField(slug_field="code", queryset=Stop.objects.all())
    destination = serializers.SlugRelatedField(slug_field="code", queryset=Stop.objects.all())
    date = serializers.DateField()
    time = serializers.TimeField(format="%H:%M", input_formats=["%H:%M"])
    passengers = serializers.IntegerField(min_value=1, max_value=MAX_PASSENGERS)
    modes = serializers.CharField(default="bus,train,taxi")

    def validate_modes(self, value):
        parts = value.split(",")
        if not parts or not set(parts) <= {"bus", "train", "taxi"} or len(set(parts)) != len(parts):
            raise serializers.ValidationError("Choose from: bus, train, taxi.")
        return ",".join(sorted(parts, key=["bus", "train", "taxi"].index))      # canonical order => reliable de-duplication

    def validate(self, attrs):
        if attrs["origin"] == attrs["destination"]:
            raise serializers.ValidationError({"destination": "Destination must differ from origin."})
        today = timezone.localdate()
        if not today <= attrs["date"] <= today + timedelta(days=watches.MAX_DAYS_AHEAD):
            raise serializers.ValidationError({"date": f"Choose a date from today to {watches.MAX_DAYS_AHEAD} days ahead."})
        return attrs


def payload(w):
    return {
        "id": w.pk, "kind": w.kind, "status": w.status,
        "origin": {"code": w.origin.code, "name": w.origin.name}, "destination": {"code": w.destination.code, "name": w.destination.name},
        "date": w.date.isoformat(), "time": w.time.strftime("%H:%M"), "passengers": w.passengers, "modes": w.modes,
        "baseline_price": f"{w.baseline_price:.2f}" if w.baseline_price is not None else None, "currency": w.currency or None,
        "last_checked_at": timezone.localtime(w.last_checked_at) if w.last_checked_at else None,
        "last_notified_at": timezone.localtime(w.last_notified_at) if w.last_notified_at else None,
        "link": watches.search_link(w),
    }


@extend_schema(methods=["GET"], responses={200: dict})
@extend_schema(methods=["POST"], request=WatchIn, responses={200: dict, 201: dict})
@throttle("booking")
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def collection(request):
    if request.method == "GET":
        watches.evaluate_user(request.user)       # lazy evaluation: correct even if the worker is not running
        qs = Watch.objects.filter(user=request.user).select_related("origin", "destination")
        return Response({"max_active": watches.MAX_ACTIVE_PER_USER, "results": [payload(w) for w in qs]})
    data = WatchIn(data=request.data)
    data.is_valid(raise_exception=True)
    v = data.validated_data
    key = {k: v[k] for k in ("kind", "origin", "destination", "date", "time", "passengers", "modes")}
    with transaction.atomic():
        User.objects.select_for_update().get(pk=request.user.pk)      # per-account: the limit and de-duplication stay exact
        existing = Watch.objects.filter(user=request.user, **key).select_related("origin", "destination").first()
        if existing and existing.status == Watch.Status.ACTIVE:
            return Response(payload(existing))
        if Watch.objects.filter(user=request.user, status=Watch.Status.ACTIVE).count() >= watches.MAX_ACTIVE_PER_USER:
            raise ValidationError({"detail": f"You can have up to {watches.MAX_ACTIVE_PER_USER} active alerts. Remove one before adding another."})
        count, price, currency = watches.search_snapshot(v["origin"], v["destination"], v["date"], v["time"], v["passengers"], v["modes"])
        if v["kind"] == Watch.Kind.PRICE and price is None:
            raise ValidationError({"kind": "No journey matches yet, so there is no price to track. Ask to be notified when one becomes available instead."})
        if v["kind"] == Watch.Kind.AVAILABILITY and count > 0:
            raise ValidationError({"kind": "Journeys are already available for this search."})
        fields = {"baseline_price": price, "currency": currency, "status": Watch.Status.ACTIVE, "last_checked_at": timezone.now()}
        if existing:                                   # an ended watch for the same search is restarted
            for name, value in fields.items():
                setattr(existing, name, value)
            existing.save()
            return Response(payload(existing), status=201)
        w = Watch.objects.create(user=request.user, **key, **fields)
    return Response(payload(Watch.objects.select_related("origin", "destination").get(pk=w.pk)), status=201)


@extend_schema(responses={204: None})
@throttle("booking")
@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def remove(request, pk):
    get_object_or_404(Watch, pk=pk, user=request.user).delete()      # someone else's id behaves like a missing one
    return Response(status=204)
