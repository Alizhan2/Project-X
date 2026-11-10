from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db.models import Sum

from apps.bookings.models import Booking, BookingLeg, Reservation
from apps.core import ops
from apps.payments.models import PaymentAttempt, Refund


class Command(BaseCommand):
    help = ("Verify cross-table business invariants (capacity vs reservations, payments vs bookings, refunds vs payments). "
            "Read-only. Exit code 1 and a list of findings if anything is inconsistent. Run after a restore and on a schedule.")

    def handle(self, *args, **opts):
        findings = []
        for row in ops.capacity_inconsistencies():
            findings.append(f"capacity: departure {row['departure']} has places_taken={row['places_taken']} but expected {row['expected']}")
        # every confirmed booking: exactly one succeeded initial payment, and consumed reservations for its live service legs
        for b in Booking.objects.filter(status=Booking.Status.CONFIRMED):
            paid = PaymentAttempt.objects.filter(booking=b, purpose="initial", status="succeeded").count()
            if paid != 1:
                findings.append(f"booking {b.reference}: {paid} successful initial payments (expected 1)")
            service_legs = BookingLeg.objects.filter(booking=b, status="booked", departure__isnull=False).count()
            consumed = Reservation.objects.filter(leg__booking=b, leg__status="booked", status="consumed").count()
            if service_legs != consumed:
                findings.append(f"booking {b.reference}: {service_legs} service legs but {consumed} consumed reservations")
        # unpaid or terminal bookings must not hold places
        live_on_dead = Reservation.objects.filter(status__in=["held", "consumed"], leg__booking__status__in=["cancelled", "expired"]).count()
        if live_on_dead:
            findings.append(f"{live_on_dead} live reservations belong to cancelled/expired bookings")
        # Aggregate separately: joining two histories multiplies rows and miscounts money.
        for b in Booking.objects.filter(refunds__isnull=False).distinct():
            paid = PaymentAttempt.objects.filter(booking=b, status="succeeded").aggregate(total=Sum("amount"))["total"] or Decimal(0)
            refunded = Refund.objects.filter(booking=b, status__in=["requested", "pending", "completed"]).aggregate(total=Sum("amount"))["total"] or Decimal(0)
            if refunded > paid:
                findings.append(f"booking {b.reference}: refunded/reserved {refunded} exceeds paid {paid}")
        for f in findings:
            self.stdout.write(self.style.ERROR(f))
        self.stdout.write(self.style.SUCCESS("integrity OK") if not findings else f"{len(findings)} finding(s)")
        raise SystemExit(1 if findings else 0)
