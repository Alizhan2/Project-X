from django.db import models
from django.db.models import Q

from apps.bookings.models import Booking


class PaymentAttempt(models.Model):
    """One SIMULATED payment attempt. No card data exists anywhere in this system."""

    class Status(models.TextChoices):
        CREATED = "created", "Created"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"

    class Purpose(models.TextChoices):
        INITIAL = "initial", "Initial payment"
        REPLACEMENT = "replacement", "Replacement journey top-up"

    booking = models.ForeignKey(Booking, on_delete=models.PROTECT, related_name="payment_attempts")
    purpose = models.CharField(max_length=12, choices=Purpose.choices, default=Purpose.INITIAL)
    idempotency_key = models.CharField(max_length=64)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.CREATED)
    failure_reason = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        constraints = [
            models.UniqueConstraint(fields=["booking", "idempotency_key"], name="payment_unique_key_per_booking"),
            # Hard guarantee against double charging: at most one successful *initial* payment per booking.
            # (A replacement top-up is a separate purpose, keyed per offer in the application layer.)
            models.UniqueConstraint(
                fields=["booking"], condition=Q(status="succeeded", purpose="initial"), name="payment_one_success_per_booking"
            ),
            models.CheckConstraint(condition=Q(amount__gt=0), name="payment_amount_positive"),
        ]


class Refund(models.Model):
    """SIMULATED refund. `key` makes it unique per booking and purpose, so repeating a cancellation (or a
    replacement settlement) can never pay the passenger twice."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        COMPLETED = "completed", "Completed (simulated)"

    class Reason(models.TextChoices):
        PASSENGER_CANCEL = "passenger_cancel", "Cancelled by passenger"
        DISRUPTION_CANCEL = "disruption_cancel", "Cancelled after disruption"
        REPLACEMENT_DIFFERENCE = "replacement_difference", "Cheaper replacement journey"

    booking = models.ForeignKey(Booking, on_delete=models.PROTECT, related_name="refunds")
    key = models.CharField(max_length=64)
    reason = models.CharField(max_length=24, choices=Reason.choices)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    detail = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at", "id"]
        constraints = [
            models.UniqueConstraint(fields=["booking", "key"], name="refund_unique_key_per_booking"),
            models.CheckConstraint(condition=Q(amount__gte=0), name="refund_amount_not_negative"),
        ]
