import logging
import re
import time
import uuid

from django.conf import settings

from .logging import request_id_var

access_log = logging.getLogger("doedu.access")
_VALID_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")


class RequestIdMiddleware:
    """Gives every request an id (accepted from a trusted proxy's X-Request-ID if well-formed), returns it in the
    response and writes one structured access-log line. No query string, body, header or client IP is logged."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        incoming = request.headers.get("X-Request-ID", "")
        rid = incoming if _VALID_ID.match(incoming) else uuid.uuid4().hex
        request.request_id = rid
        token = request_id_var.set(rid)
        started = time.monotonic()
        try:
            response = self.get_response(request)
        finally:
            duration = round((time.monotonic() - started) * 1000)
            user = getattr(request, "user", None)
            status = locals().get("response").status_code if "response" in locals() else 500
            if not request.path.startswith("/api/health/"):
                access_log.info("request", extra={
                    "method": request.method, "path": request.path, "status": status, "duration_ms": duration,
                    "user_id": user.pk if user is not None and getattr(user, "is_authenticated", False) else None})
            request_id_var.reset(token)
        response["X-Request-ID"] = rid
        return response


CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; "
       "connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")


class SecurityHeadersMiddleware:
    """CSP for the SPA/API (not Django Admin or Swagger UI, which need inline code), no-store for API responses
    (they carry personal booking data), and a restrictive Permissions-Policy."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        path = request.path
        if not (path.startswith("/admin/") or path.startswith("/api/docs/")):
            response.headers.setdefault("Content-Security-Policy", CSP)
        if path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        response.headers.setdefault("Permissions-Policy", "geolocation=(), camera=(), microphone=(), payment=()")
        response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        return response
