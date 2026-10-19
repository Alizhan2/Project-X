"""Purchased bookings. Unlike search results, these snapshot everything that was sold:
later fare/schedule/policy edits never rewrite a purchase (see BookingLeg snapshot fields)."""

import secrets

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.transport.models import Departure, Stop, TaxiOffer

_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I


def new_reference():
    return "DD-" + "".join(secrets.choice(_ALPHABET) for _ in range(8))


class Booking(models.Model):
    class Status(models.TextChoices):
        PENDING_PAYMENT = "pending_payment", "Awaiting payment"
        CONFIRMED = "confirmed", "Confirmed (simulated)"
        CANCELLED = "cancelled", "Cancelled"
        EXPIRED = "expired", "Reservation expired"

    reference = models.CharField(max_length=12, unique=True, default=new_reference)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="bookings")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING_PAYMENT)
    passengers = models.PositiveSmallIntegerField()
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3)
    contact_email = models.EmailField()
    idempotency_key = models.CharField(max_length=64)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["status", "expires_at"])]
        constraints = [
            models.UniqueConstraint(fields=["user", "idempotency_key"], name="booking_unique_idempotency_per_user"),
            models.CheckConstraint(condition=Q(passengers__gte=1, passengers__lte=9), name="booking_passengers_1_9"),
            models.CheckConstraint(condition=Q(total_amount__gt=0), name="booking_total_positive"),
        ]


class Traveller(models.Model):
    """Minimal personal data: a name per passenger (no documents, no phone numbers)."""

    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name="travellers")
    full_name = models.CharField(max_length=150)


class BookingLeg(models.Model):
    class Status(models.TextChoices):
        BOOKED = "booked", "Booked"
        CANCELLED = "cancelled", "Cancelled"
        REPLACED = "replaced", "Replaced"

    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name="legs")
    sequence = models.PositiveSmallIntegerField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.BOOKED)
    # Exactly one of departure (bus/train) or taxi_offer is set.
    departure = models.ForeignKey(Departure, null=True, blank=True, on_delete=models.PROTECT, related_name="booking_legs")
    taxi_offer = models.ForeignKey(TaxiOffer, null=True, blank=True, on_delete=models.PROTECT, related_name="booking_legs")
    from_stop = models.ForeignKey(Stop, on_delete=models.PROTECT, related_name="+")
    to_stop = models.ForeignKey(Stop, on_delete=models.PROTECT, related_name="+")
    # ---- snapshots taken at purchase ----
    mode = models.CharField(max_length=8)  # bus | train | taxi
    operator_name = models.CharField(max_length=100)
    route_code = models.CharField(max_length=16)
    route_name = models.CharField(max_length=120)
    from_name = models.CharField(max_length=100)
    to_name = models.CharField(max_length=100)
    departs_at = models.DateTimeField()
    arrives_at = models.DateTimeField()
    unit_price = models.DecimalField(max_digits=8, decimal_places=2)
    price_basis = models.CharField(max_length=10, default="passenger")  # "passenger" or "vehicle" (taxi)
    policy_name = models.CharField(max_length=100)
    policy_full_refund_hours = models.PositiveIntegerField()
    policy_partial_refund_hours = models.PositiveIntegerField()
    policy_partial_percent = models.PositiveSmallIntegerField()

    class Meta:
        ordering = ["booking", "sequence"]
        constraints = [
            models.UniqueConstraint(fields=["booking", "sequence"], name="bookingleg_unique_sequence"),
            models.CheckConstraint(
                condition=(Q(departure__isnull=False) & Q(taxi_offer__isnull=True))
                | (Q(departure__isnull=True) & Q(taxi_offer__isnull=False)),
                name="bookingleg_service_xor_taxi",
            ),
        ]


class Reservation(models.Model):
    """A hold on `places` of a departure's capacity on behalf of one booking leg."""

    class Status(models.TextChoices):
        HELD = "held", "Held"
        CONSUMED = "consumed", "Consumed"
        RELEASED = "released", "Released"
        EXPIRED = "expired", "Expired"

    leg = models.ForeignKey(BookingLeg, on_delete=models.CASCADE, related_name="reservations")
    departure = models.ForeignKey(Departure, on_delete=models.PROTECT, related_name="reservations")
    places = models.PositiveSmallIntegerField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.HELD)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(places__gte=1), name="reservation_places_positive"),
            # A leg can have only one live (held/consumed) reservation at a time.
            models.UniqueConstraint(
                fields=["leg"], condition=Q(status__in=["held", "consumed"]), name="reservation_one_live_per_leg"
            ),
        ]
