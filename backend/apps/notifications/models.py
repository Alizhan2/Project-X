from django.conf import settings
from django.db import models


class Notification(models.Model):
    """In-app notification, fetched by polling. `dedupe_key` makes creation idempotent per user, so a repeated
    disruption event or retried job cannot spam the passenger."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    kind = models.CharField(max_length=32)
    title = models.CharField(max_length=140)
    body = models.TextField()
    booking = models.ForeignKey("bookings.Booking", null=True, blank=True, on_delete=models.CASCADE, related_name="notifications")
    dedupe_key = models.CharField(max_length=128)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [models.UniqueConstraint(fields=["user", "dedupe_key"], name="notification_unique_per_user")]
