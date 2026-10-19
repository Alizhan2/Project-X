#!/bin/sh
# Bring up a production-like stack (no containers) against an EXISTING PostgreSQL: roles -> migrate -> static -> demo data ->
# gunicorn (+ worker) -> wait for readiness. Used by CI and for local rehearsals; mirrors docker-compose.prod.yml.
# Required environment: the variables of .env.production.example (DOEDU_ENV=staging) incl. POSTGRES_ADMIN_* and
# MIGRATE_POSTGRES_*, FRONTEND_DIST (built SPA) and GUNICORN_BIND. DOEDU_ALLOW_DEMO_TOOLS=true seeds synthetic demo data.
set -eu
cd "$(dirname "$0")/../backend"
PY="${PYTHON:-python}"
$PY manage.py setup_db_roles
APP_POSTGRES_USER="$POSTGRES_USER" POSTGRES_USER="$MIGRATE_POSTGRES_USER" POSTGRES_PASSWORD="$MIGRATE_POSTGRES_PASSWORD" $PY manage.py safe_migrate
$PY manage.py collectstatic --noinput >/dev/null
[ "${DOEDU_ALLOW_DEMO_TOOLS:-false}" = "true" ] && $PY manage.py seed_demo >/dev/null
nohup gunicorn config.wsgi:application -c gunicorn.conf.py > "${LOG_DIR:-/tmp}/doedu-web.log" 2>&1 &
nohup $PY manage.py run_worker > "${LOG_DIR:-/tmp}/doedu-worker.log" 2>&1 &
url="http://${GUNICORN_BIND:-127.0.0.1:8000}/api/health/ready/"
for i in $(seq 1 60); do
  if curl -fsS "$url" >/dev/null 2>&1; then echo "ready: $(curl -s "$url")"; exit 0; fi
  sleep 1
done
echo "NOT READY after 60s; web log:"; tail -20 "${LOG_DIR:-/tmp}/doedu-web.log"; exit 1
