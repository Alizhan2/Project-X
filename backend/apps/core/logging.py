"""Structured, redacted logging. Request bodies, headers, cookies, passwords and tokens are never logged; free-text
messages and tracebacks are additionally scrubbed of e-mail addresses and credential-looking values."""

import contextvars
import json
import logging
import re
from datetime import datetime, timezone

request_id_var = contextvars.ContextVar("request_id", default="-")

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_BEARER = re.compile(r"(?i)bearer\s+\S+")
_SECRET = re.compile(r"(?i)(password|passwd|secret|token|sessionid|csrftoken|authorization|api[_-]?key)(\s*[=:]\s*|\s+)\S+")
# Structured fields that may be attached with `extra=`; anything else is dropped from JSON output.
_ALLOWED_EXTRA = ("method", "path", "status", "duration_ms", "user_id", "job_id", "kind", "booking", "event", "worker", "count")


def redact(text: str) -> str:
    text = _BEARER.sub("bearer [redacted]", _EMAIL.sub("[email]", text))
    return _SECRET.sub(lambda m: f"{m.group(1)}=[redacted]", text)


class RequestIdFilter(logging.Filter):
    def filter(self, record):
        record.request_id = request_id_var.get()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record):
        out = {
            "ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname, "logger": record.name, "request_id": getattr(record, "request_id", request_id_var.get()),
            "message": redact(record.getMessage()),
        }
        for key in _ALLOWED_EXTRA:
            if hasattr(record, key):
                out[key] = getattr(record, key)
        if record.exc_info:
            out["exception"] = redact(self.formatException(record.exc_info))
        return json.dumps(out, default=str)
