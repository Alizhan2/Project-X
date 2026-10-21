from django.conf import settings
from django.db import models
from django.db.models import F, Q


class Notification(models.Model):
    """In-app notification, fetched by polling. `dedupe_key` makes creation idempotent per user, so a repeated
    disruption event or retried job cannot spam the passenger."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    kind = models.CharField(max_length=32)
    title = models.CharField(max_length=140)
    body = models.TextField()
    booking = models.ForeignKey("bookings.Booking", null=True, blank=True, on_delete=models.CASCADE, related_name="notifications")
    # Optional in-app path to open (always starts with "/"): lets an alert lead straight to the relevant search.
    link = models.CharField(max_length=300, blank=True)
    dedupe_key = models.CharField(max_length=128)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [models.UniqueConstraint(fields=["user", "dedupe_key"], name="notification_unique_per_user")]


class Watch(models.Model):
    """A passenger's request to be told when something changes for a search. It reserves nothing and promises
    nothing: it only produces an in-app notification. Evaluated by the worker (and lazily when the owner lists
    their watches), using the same planner as the search screen so numbers always match."""

    class Kind(models.TextChoices):
        PRICE = "price", "Price drop"
        AVAILABILITY = "availability", "Journey becomes available"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        TRIGGERED = "triggered", "Notified"        # one-shot availability watches end here
        EXPIRED = "expired", "Date passed"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="watches")
    kind = models.CharField(max_length=14, choices=Kind.choices)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    origin = models.ForeignKey("transport.Stop", on_delete=models.CASCADE, related_name="+")
    destination = models.ForeignKey("transport.Stop", on_delete=models.CASCADE, related_name="+")
    date = models.DateField(help_text="Travel date in the demo timezone")
    time = models.TimeField(help_text="Earliest departure")
    passengers = models.PositiveSmallIntegerField()
    modes = models.CharField(max_length=20, default="bus,train,taxi")
    baseline_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Last cheapest total seen (price watches)")
    currency = models.CharField(max_length=3, blank=True)
    last_checked_at = models.DateTimeField(null=True, blank=True)
    last_notified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["status", "date"])]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "kind", "origin", "destination", "date", "time", "passengers", "modes"], name="watch_unique_per_user"),
            models.CheckConstraint(condition=~Q(origin=F("destination")), name="watch_different_stops"),
            models.CheckConstraint(condition=Q(passengers__gte=1, passengers__lte=9), name="watch_passengers_1_9"),
            models.CheckConstraint(condition=~Q(kind="price") | Q(baseline_price__isnull=False), name="watch_price_has_baseline"),
        ]
