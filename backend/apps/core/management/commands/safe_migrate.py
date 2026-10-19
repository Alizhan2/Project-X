import os

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import connection

LOCK_KEY = 7_330_001  # arbitrary constant shared by every release process


class Command(BaseCommand):
    help = ("Apply migrations under a PostgreSQL advisory lock so two replicas/pipelines can never migrate at once, "
            "then create the shared cache table. Run ONCE per release, before starting the new application version.")

    def handle(self, *args, **opts):
        with connection.cursor() as cur:
            self.stdout.write("waiting for migration lock…")
            cur.execute("SELECT pg_advisory_lock(%s)", [LOCK_KEY])
            try:
                call_command("migrate", interactive=False, verbosity=1)
                call_command("createcachetable", verbosity=0)
                self.protect_history(cur)
            finally:
                cur.execute("SELECT pg_advisory_unlock(%s)", [LOCK_KEY])
        self.stdout.write(self.style.SUCCESS("migrations applied"))

    def protect_history(self, cur):
        """Let the database itself keep financial and audit history append-only for the runtime role.
        (Skipped where demo tools are enabled, because the demo reset deliberately wipes this data.)"""
        app_role = os.environ.get("APP_POSTGRES_USER")
        if not app_role or settings.ALLOW_DEMO_TOOLS:
            self.stdout.write("history protection skipped" + (" (demo tools enabled)" if settings.ALLOW_DEMO_TOOLS else " (APP_POSTGRES_USER unset)"))
            return
        from psycopg import sql
        role = sql.Identifier(app_role)
        for stmt in ("REVOKE UPDATE, DELETE, TRUNCATE ON core_auditrecord FROM {r}",
                     "REVOKE DELETE, TRUNCATE ON payments_paymentattempt, payments_refund FROM {r}"):
            cur.execute(sql.SQL(stmt).format(r=role))
        self.stdout.write("history protection applied: audit is append-only, payments/refunds cannot be deleted by the app role")
