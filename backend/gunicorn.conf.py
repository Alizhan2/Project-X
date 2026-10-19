"""Production server settings. Every value can be overridden by an environment variable (see docs/configuration.md)."""

import os

bind = os.environ.get("GUNICORN_BIND", "0.0.0.0:8000")
workers = int(os.environ.get("WEB_CONCURRENCY", "2"))
threads = int(os.environ.get("GUNICORN_THREADS", "4"))
worker_class = "gthread"
timeout = int(os.environ.get("GUNICORN_TIMEOUT", "30"))            # a request running longer is killed and restarted
graceful_timeout = int(os.environ.get("GUNICORN_GRACEFUL_TIMEOUT", "30"))   # time to finish in-flight requests on SIGTERM
keepalive = 5
max_requests = int(os.environ.get("GUNICORN_MAX_REQUESTS", "2000"))        # recycle workers: bounds slow memory growth
max_requests_jitter = 200
worker_tmp_dir = "/tmp/gunicorn" if os.path.isdir("/tmp/gunicorn") else None
# Only trust X-Forwarded-* from the reverse proxy / ingress in front of this container (set to its address or "*"
# ONLY when the container is unreachable except through that proxy, as in docker-compose.prod.yml).
forwarded_allow_ips = os.environ.get("GUNICORN_FORWARDED_ALLOW_IPS", "127.0.0.1")
secure_scheme_headers = {"X-FORWARDED-PROTO": "https"}
accesslog = None           # the application writes its own structured access log (apps/core/middleware.py)
errorlog = "-"
loglevel = os.environ.get("GUNICORN_LOG_LEVEL", "warning")
limit_request_line = 4094
limit_request_fields = 50
limit_request_field_size = 8190
