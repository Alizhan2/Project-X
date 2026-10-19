# Production image: built from the repository root.  docker build --build-arg DOEDU_RELEASE=$(git rev-parse --short HEAD) -t doedu:$VERSION .
# Stages: (1) build the SPA, (2) install the hash-locked Python dependencies, (3) minimal non-root runtime.
# NOTE: written without Docker available on the authoring machine; see docs/verification-report.md for what was executed.

FROM node:24.22.0-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.14.8-slim-bookworm AS deps
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /opt/venv
COPY backend/requirements.txt /tmp/requirements.txt
# --require-hashes: every wheel must match the lockfile; psycopg[binary] bundles libpq so no OS packages are needed.
RUN /opt/venv/bin/pip install --require-hashes -r /tmp/requirements.txt

FROM python:3.14.8-slim-bookworm AS runtime
ARG DOEDU_RELEASE=unknown
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PATH="/opt/venv/bin:$PATH" \
    DJANGO_SETTINGS_MODULE=config.settings DOEDU_RELEASE=${DOEDU_RELEASE} FRONTEND_DIST=/app/frontend_dist
RUN groupadd --system --gid 10001 app && useradd --system --uid 10001 --gid app --no-create-home --shell /usr/sbin/nologin app
WORKDIR /app
COPY --from=deps /opt/venv /opt/venv
COPY backend/ /app/
COPY --from=web /web/dist /app/frontend_dist
# Static files for Django Admin. Built with throw-away settings (DOEDU_ENV=development) so no real secret is needed at build time.
RUN DOEDU_ENV=development DJANGO_DEBUG=false python manage.py collectstatic --noinput \
 && chown -R root:root /app && chmod -R a-w /app && mkdir -p /tmp/gunicorn && chown app:app /tmp/gunicorn
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health/live/', timeout=3)"]
# Graceful shutdown: gunicorn drains on SIGTERM (see gunicorn.conf.py). Migrations are NOT run here: see docs/deployment.md.
CMD ["gunicorn", "config.wsgi:application", "-c", "gunicorn.conf.py"]
