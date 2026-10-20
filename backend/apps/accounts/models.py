from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Platform user. `role` drives server-side permission checks.

    Operator staff additionally need an OperatorMembership (added in the
    transport domain) which scopes them to their own operator's services.
    """

    class Role(models.TextChoices):
        PASSENGER = "passenger", "Passenger"
        OPERATOR = "operator", "Operator"
        ADMIN = "admin", "Administrator"

    role = models.CharField(max_length=16, choices=Role.choices, default=Role.PASSENGER)

    email_verified_at = models.DateTimeField(null=True, blank=True)


class FavoriteRoute(models.Model):
    """An account-owned direction, never a price, departure or reservation."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="favorite_routes")
    origin = models.ForeignKey("transport.Stop", on_delete=models.CASCADE, related_name="+")
    destination = models.ForeignKey("transport.Stop", on_delete=models.CASCADE, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["user", "origin", "destination"], name="favorite_unique_direction"),
            models.CheckConstraint(condition=~models.Q(origin=models.F("destination")), name="favorite_different_stops"),
        ]
