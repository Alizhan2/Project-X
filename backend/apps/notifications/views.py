from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view
from rest_framework.response import Response

from apps.transport.markets import booking_timezone, local_iso, timezone_for_stops
from .models import Notification


def _payload(n):
    zone = booking_timezone(n.booking) if n.booking_id else timezone_for_stops()
    return {
        "id": n.pk, "kind": n.kind, "title": n.title, "body": n.body,
        "booking": n.booking.reference if n.booking_id else None, "link": n.link or None,
        "created_at": local_iso(n.created_at, zone), "timezone": zone, "read": n.read_at is not None,
    }


@extend_schema(responses={200: dict})
@api_view(["GET"])
def notifications(request):
    """Own notifications, newest first. The SPA polls this endpoint (no websockets in the MVP)."""
    qs = Notification.objects.filter(user=request.user).select_related("booking").prefetch_related("booking__legs__from_stop", "booking__legs__to_stop")
    return Response({"unread": qs.filter(read_at__isnull=True).count(), "results": [_payload(n) for n in qs[:100]]})


@extend_schema(request=None, responses={200: dict})
@api_view(["POST"])
def mark_read(request, pk):
    # Filtering by user means another user's id behaves like a missing one (no information leak).
    Notification.objects.filter(pk=pk, user=request.user, read_at__isnull=True).update(read_at=timezone.now())
    return Response({"ok": True})


@extend_schema(request=None, responses={200: dict})
@api_view(["POST"])
def mark_all_read(request):
    Notification.objects.filter(user=request.user, read_at__isnull=True).update(read_at=timezone.now())
    return Response({"ok": True})
