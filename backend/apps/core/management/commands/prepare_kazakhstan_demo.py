"""Add the Kazakhstan demo geography and scoped operator accounts without resetting data."""
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from apps.accounts.models import User
from apps.core.models import AuditRecord
from apps.transport.demo_data import demo_password
from apps.transport.kazakhstan.demo import ensure_network
from apps.transport.models import OperatorMembership


class Command(BaseCommand):
    help = "Add Kazakhstan demo stops and two operator accounts once; preserve all existing records and passwords."

    def handle(self, *args, **options):
        if not settings.SIMULATION_ENABLED:
            raise CommandError("Kazakhstan demonstration setup requires simulation mode.")
        password = demo_password()
        if settings.IS_DEPLOYED and len(password) < 16:
            raise CommandError("Provide a generated DEMO_USER_PASSWORD of at least 16 characters for hosted demo operators.")
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_xact_lock(%s)", [7_330_004])
            operators = ensure_network()
            for code, email, name in (
                ("kz-demo-bus", "ops.kzbus@doedu.test", "Kazakhstan Bus Operator"),
                ("kz-demo-rail", "ops.kzrail@doedu.test", "Kazakhstan Rail Operator"),
            ):
                user, created = User.objects.get_or_create(username=email, defaults={
                    "email": email, "first_name": name, "role": User.Role.OPERATOR,
                })
                if created:
                    user.set_password(password)
                    user.save(update_fields=["password"])
                if user.role != User.Role.OPERATOR or user.is_staff or user.is_superuser:
                    self.stderr.write("A conflicting existing account was left unchanged; administrator review is required for that demo operator.")
                    continue
                membership = (OperatorMembership.objects.create(user=user, operator=operators[code]) if created
                              else OperatorMembership.objects.filter(user=user).first())
                if membership is None or membership.operator_id != operators[code].pk:
                    self.stderr.write("An existing operator membership was left unchanged; administrator review is required.")
            AuditRecord.objects.get_or_create(action="demo.kz_prepared", object_type="deployment",
                                              object_id="kazakhstan-demo-v1", defaults={"detail": {"cities": 90, "simulated": True}})
        self.stdout.write("Kazakhstan demo prepared; existing users, passwords, fares and bookings are preserved.")
