import logging

from django.db import InterfaceError, OperationalError
from django.http import HttpResponse, JsonResponse
from rest_framework.views import exception_handler as drf_handler

log = logging.getLogger(__name__)


def exception_handler(exc, context):
    """DRF errors keep their shape; unexpected exceptions are logged (redacted) and become a generic 500 that
    carries only the request id, never a stack trace or message."""
    response = drf_handler(exc, context)
    if response is None and isinstance(exc, (OperationalError, InterfaceError)):
        # Database unreachable/timeout: a retryable condition, not a bug. (The failed transaction was rolled back.)
        log.error("database unavailable: %s", type(exc).__name__)
        request = context.get("request")
        rid = getattr(getattr(request, "_request", request), "request_id", "-")
        res = JsonResponse({"code": "service_unavailable", "message": "The service is temporarily unavailable. Please retry shortly.", "request_id": rid}, status=503)
        res["Retry-After"] = "5"
        return res
    if response is None:
        log.exception("unhandled error in API view")
        request = context.get("request")
        rid = getattr(getattr(request, "_request", request), "request_id", "-")
        return JsonResponse({"code": "server_error", "message": "Something went wrong on our side.", "request_id": rid}, status=500)
    return response


def server_error(request, *args, **kwargs):
    rid = getattr(request, "request_id", "-")
    if request.path.startswith("/api/"):
        return JsonResponse({"code": "server_error", "message": "Something went wrong on our side.", "request_id": rid}, status=500)
    return HttpResponse(f"Something went wrong. Reference: {rid}", status=500, content_type="text/plain")


def not_found(request, exception=None):
    if request.path.startswith("/api/"):
        return JsonResponse({"code": "not_found", "message": "Not found."}, status=404)
    return HttpResponse("Not found.", status=404, content_type="text/plain")
