import hashlib
import json

from django.core.management.base import BaseCommand

from apps.bookings.models import Booking, BookingLeg, Reservation
from apps.core.models import AuditRecord
from apps.disruptions.models import ReplacementOffer
from apps.payments.models import PaymentAttempt, Refund
from apps.transport.models import Departure


class Command(BaseCommand):
    help = ("Print row counts and a SHA-256 over the business-critical state (bookings, legs, reservations, payments, "
            "refunds, offers, capacity counters). Compare before a backup and after a restore: identical = nothing lost or altered. "
            "Contains no personal data.")

    def handle(self, *args, **opts):
        parts = {
            "bookings": list(Booking.objects.order_by("reference").values_list("reference", "status", "total_amount", "passengers")),
            "legs": list(BookingLeg.objects.order_by("booking__reference", "sequence").values_list("booking__reference", "sequence", "status", "unit_price", "departs_at")),
            "reservations": list(Reservation.objects.order_by("leg__booking__reference", "leg__sequence", "pk").values_list("leg__booking__reference", "leg__sequence", "status", "places")),
            "payments": list(PaymentAttempt.objects.order_by("booking__reference", "pk").values_list("booking__reference", "purpose", "status", "amount")),
            "refunds": list(Refund.objects.order_by("booking__reference", "key").values_list("booking__reference", "key", "status", "amount")),
            "offers": list(ReplacementOffer.objects.order_by("booking__reference", "fingerprint").values_list("booking__reference", "status", "difference")),
            "capacity": list(Departure.objects.order_by("route__code", "departs_at").values_list("route__code", "departs_at", "capacity", "places_taken", "status", "delay_minutes")),
        }
        digest = hashlib.sha256(json.dumps(parts, default=str, sort_keys=True).encode()).hexdigest()
        out = {"sha256": digest, "counts": {k: len(v) for k, v in parts.items()}, "audit_records": AuditRecord.objects.count()}
        self.stdout.write(json.dumps(out, indent=2, sort_keys=True))
