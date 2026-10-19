import os

import psycopg
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from psycopg import sql


class Command(BaseCommand):
    help = ("Create/refresh the least-privilege PostgreSQL roles. Run as the ADMIN role (POSTGRES_ADMIN_USER/PASSWORD), "
            "once per release before `safe_migrate`. Idempotent.\n"
            "  migrator (MIGRATE_POSTGRES_USER): owns the schema; used only by the migrate job; may run DDL.\n"
            "  app      (POSTGRES_USER):          runtime role: SELECT/INSERT/UPDATE/DELETE + sequence use. No DDL, no TRUNCATE.")

    def handle(self, *args, **opts):
        db = settings.DATABASES["default"]
        need = {k: os.environ.get(k) for k in ("POSTGRES_ADMIN_USER", "POSTGRES_ADMIN_PASSWORD", "MIGRATE_POSTGRES_USER",
                                              "MIGRATE_POSTGRES_PASSWORD")}
        missing = [k for k, v in need.items() if not v]
        if missing or not db["PASSWORD"]:
            raise CommandError(f"Missing environment variables: {', '.join(missing) or 'POSTGRES_PASSWORD'}")
        migrator, app = need["MIGRATE_POSTGRES_USER"], db["USER"]
        if migrator == app:
            raise CommandError("The migrate role and the runtime role must be different roles.")
        ident = sql.Identifier
        with psycopg.connect(host=db["HOST"], port=db["PORT"], dbname=db["NAME"], user=need["POSTGRES_ADMIN_USER"],
                             password=need["POSTGRES_ADMIN_PASSWORD"], autocommit=True) as conn:
            for role, password in ((migrator, need["MIGRATE_POSTGRES_PASSWORD"]), (app, db["PASSWORD"])):
                exists = conn.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", [role]).fetchone()
                verb = "ALTER" if exists else "CREATE"
                conn.execute(sql.SQL("{} ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB NOCREATEROLE").format(
                    sql.SQL(verb), ident(role), sql.Literal(password)))
            dbn = ident(db["NAME"])
            for stmt in (
                "REVOKE ALL ON DATABASE {db} FROM PUBLIC",
                "GRANT CONNECT ON DATABASE {db} TO {m}, {a}",
                "ALTER SCHEMA public OWNER TO {m}",
                "REVOKE ALL ON SCHEMA public FROM PUBLIC",
                "GRANT USAGE ON SCHEMA public TO {a}",
                "ALTER DEFAULT PRIVILEGES FOR ROLE {m} IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {a}",
                "ALTER DEFAULT PRIVILEGES FOR ROLE {m} IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO {a}",
                "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {a}",
                "GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {a}",
            ):
                conn.execute(sql.SQL(stmt).format(db=dbn, m=ident(migrator), a=ident(app)))
        self.stdout.write(self.style.SUCCESS(f"roles ready: migrator={migrator}, app={app}"))
