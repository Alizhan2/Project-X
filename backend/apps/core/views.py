import hmac

from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import render  # noqa: F401
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response

from . import ops


@extend_schema(responses={200: OpenApiTypes.OBJECT})
@api_view(["GET"])
@authentication_classes([])
@permission_classes([])
def live(request):
    """Liveness: the process answers. Touches nothing else, so a database outage never restarts healthy app servers."""
    return Response({"status": "ok"})


@extend_schema(responses={200: OpenApiTypes.OBJECT, 503: OpenApiTypes.OBJECT})
@api_view(["GET"])
@authentication_classes([])
@permission_classes([])
def ready(request):
    """Readiness: can this instance serve traffic? Database reachable and no pending migrations.
    The worker state is informational (a stale worker must not take the web tier out of rotation).
    The body contains no versions, hostnames or credentials."""
    if not ops.database_ok():
        return Response({"status": "unavailable", "database": "unreachable"}, status=503)
    if ops.migrations_pending():
        return Response({"status": "unavailable", "database": "ok", "migrations": "pending"}, status=503)
    state, _ = ops.worker_state()
    return Response({"status": "ok", "database": "ok", "migrations": "ok", "worker": state, "release": settings.RELEASE})


health = ready  # /api/health/ kept for existing clients/tests


@extend_schema(responses={200: OpenApiTypes.OBJECT})
@api_view(["GET"])
@authentication_classes([])
@permission_classes([])
def config(request):
    """Public runtime configuration for the SPA: what this deployment is allowed to claim."""
    return Response({
        "launch_mode": settings.LAUNCH_MODE, "simulated": settings.SIMULATION_ENABLED,
        "registration_enabled": settings.REGISTRATION_ENABLED, "release": settings.RELEASE,
    })


@extend_schema(exclude=True)
@api_view(["GET"])
@authentication_classes([])
@permission_classes([])
def metrics(request):
    """Prometheus text metrics, protected by a bearer token (METRICS_TOKEN). Off when no token is configured.
    Contains counts and ages only: no personal data."""
    token = settings.METRICS_TOKEN
    given = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    if not token or not hmac.compare_digest(given.encode(), token.encode()):
        return HttpResponse(status=404)
    s = ops.snapshot()
    lines = ["# TYPE doedu_jobs gauge"]
    lines += [f'doedu_jobs{{status="{k}"}} {v}' for k, v in s["jobs"].items()]
    lines += [f"doedu_jobs_oldest_due_age_seconds {s['jobs_oldest_due_age_seconds']}", f"doedu_jobs_stale_running {s['jobs_stale_running']}"]
    lines += [f"doedu_worker_heartbeat_age_seconds {s['worker']['heartbeat_age_seconds'] if s['worker']['heartbeat_age_seconds'] is not None else -1}"]
    lines += [f'doedu_bookings{{status="{k}"}} {v}' for k, v in s["bookings"].items()]
    lines += [f"doedu_pending_bookings_overdue {s['pending_bookings_overdue']}"]
    lines += [f'doedu_replacement_offers{{status="{k}"}} {v}' for k, v in s["replacement_offers"].items()]
    lines += [f"doedu_capacity_inconsistencies {s['capacity_inconsistencies']}", f'doedu_release_info{{release="{s["release"]}"}} 1']
    return HttpResponse("\n".join(lines) + "\n", content_type="text/plain; version=0.0.4")
