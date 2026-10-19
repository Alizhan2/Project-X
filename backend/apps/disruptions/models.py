from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.transport.models import Departure


class DisruptionEvent(models.Model):
    """A recorded operator change to a service. One row per distinct change, so repeating the same change
    (same departure, kind and resulting delay) is a no-op that creates no new notifications."""

    class Kind(models.TextChoices):
        DELAY = "delay", "Delay"
        CANCEL = "cancel", "Cancellation"
        CLEAR = "clear", "Delay cleared"

    departure = models.ForeignKey(Departure, on_delete=models.PROTECT, related_name="disruption_events")
    kind = models.CharField(max_length=8, choices=Kind.choices)
    delay_minutes = models.PositiveIntegerField(default=0, help_text="Resulting total delay (delay events only)")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    affected_bookings = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.CheckConstraint(condition=Q(kind="delay", delay_minutes__gt=0) | ~Q(kind="delay"), name="disruption_delay_positive"),
        ]


class ReplacementOffer(models.Model):
    """A proposed replacement for the *remaining* part of a disrupted booking. Not a booking: nothing is held
    until the passenger accepts. Offers expire, and become invalid if the underlying conditions change."""

    class Status(models.TextChoices):
        PROPOSED = "proposed", "Proposed"
        ACCEPTED = "accepted", "Accepted"
        DECLINED = "declined", "Declined"
        EXPIRED = "expired", "Expired"
        INVALIDATED = "invalidated", "No longer valid"

    booking = models.ForeignKey("bookings.Booking", on_delete=models.CASCADE, related_name="replacement_offers")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PROPOSED)
    problem_sequence = models.PositiveSmallIntegerField(help_text="First booking leg that can no longer be used")
    legs_selection = models.JSONField(help_text="Selection items accepted by planning.build_itinerary")
    legs_snapshot = models.JSONField(help_text="Display copy of the replacement legs when proposed")
    legs_param = models.CharField(max_length=400)
    total_new = models.DecimalField(max_digits=10, decimal_places=2, help_text="Price of the replacement legs")
    replaced_value = models.DecimalField(max_digits=10, decimal_places=2, help_text="Paid for the legs being replaced")
    difference = models.DecimalField(max_digits=10, decimal_places=2, help_text="+ passenger pays more, - passenger is refunded")
    currency = models.CharField(max_length=3)
    arrives_at = models.DateTimeField()
    fingerprint = models.CharField(max_length=40)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    note = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["arrives_at", "id"]
        constraints = [
            # Repeated/concurrent recovery runs cannot create duplicate live offers.
            models.UniqueConstraint(fields=["booking", "fingerprint"], condition=Q(status="proposed"), name="replacement_one_live_per_fingerprint"),
        ]
