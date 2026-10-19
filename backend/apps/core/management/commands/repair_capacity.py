from django.core.management.base import BaseCommand
from django.db import transaction

from apps.core import ops
from apps.core.models import AuditRecord
from apps.transport.models import Departure


class Command(BaseCommand):
    help = ("Recompute Departure.places_taken = baseline_places + live reservations for departures flagged by check_integrity. "
            "DRY RUN unless --apply. Locks each departure, refuses to exceed capacity, and writes an audit record. "
            "Investigate WHY it drifted first (docs/runbook.md); this command only restores the invariant.")

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **opts):
        rows = ops.capacity_inconsistencies()
        if not rows:
            self.stdout.write("no inconsistencies")
            return
        for row in rows:
            with transaction.atomic():
                dep = Departure.objects.select_for_update().get(pk=row["departure"])
                expected = row["expected"]
                if expected > dep.capacity:
                    self.stdout.write(self.style.ERROR(f"departure {dep.pk}: expected {expected} exceeds capacity {dep.capacity}: manual review required"))
                    continue
                self.stdout.write(f"departure {dep.pk}: places_taken {dep.places_taken} -> {expected}" + ("" if opts["apply"] else "  (dry run)"))
                if opts["apply"]:
                    AuditRecord.objects.create(action="capacity.repaired", object_type="departure", object_id=str(dep.pk),
                                               detail={"from": dep.places_taken, "to": expected})
                    Departure.objects.filter(pk=dep.pk).update(places_taken=expected)
