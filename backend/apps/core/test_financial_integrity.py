from datetime import timedelta
from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.bookings.models import Booking
from apps.payments.models import PaymentAttempt, Refund


class FinancialIntegrityTests(TestCase):
    def booking(self):
        user = User.objects.create_user("integrity@example.com", "Integrity", "synthetic-test-password")
        return Booking.objects.create(user=user, status="cancelled", passengers=1, total_amount=30,
                                      currency="KZT", contact_email=user.email, idempotency_key="integrity-check",
                                      expires_at=timezone.now() + timedelta(minutes=5))

    def payment(self, booking, amount, key):
        PaymentAttempt.objects.create(booking=booking, purpose="replacement", idempotency_key=key,
                                      amount=Decimal(amount), currency="KZT", status="succeeded")

    def refund(self, booking, amount, key, status="completed"):
        Refund.objects.create(booking=booking, key=key, reason="passenger_cancel", amount=Decimal(amount),
                              currency="KZT", status=status)

    def test_multiple_payments_do_not_multiply_a_refund(self):
        b = self.booking()
        for key, amount in enumerate(("10", "20", "30")):
            self.payment(b, amount, str(key))
        self.refund(b, "50", "refund")
        out = StringIO()
        with self.assertRaises(SystemExit) as result:
            call_command("check_integrity", stdout=out)
        self.assertEqual(result.exception.code, 0, out.getvalue())

    def test_multiple_refunds_do_not_multiply_a_payment(self):
        b = self.booking()
        self.payment(b, "30", "paid")
        self.refund(b, "20", "one")
        self.refund(b, "20", "two", status="pending")
        out = StringIO()
        with self.assertRaises(SystemExit) as result:
            call_command("check_integrity", stdout=out)
        self.assertEqual(result.exception.code, 1)
        self.assertIn("exceeds paid", out.getvalue())
