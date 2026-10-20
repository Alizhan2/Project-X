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


class SavedTraveller(models.Model):
    """A passenger name the account owner chose to keep for faster checkout. Name only (data minimisation):
    no documents, birth dates or contact details. Created only on explicit opt-in; deletable at any time."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="saved_travellers")
    full_name = models.CharField(max_length=150)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        constraints = [
            models.UniqueConstraint(models.functions.Lower("full_name"), "user", name="savedtraveller_unique_name_per_user"),
            models.CheckConstraint(condition=~models.Q(full_name=""), name="savedtraveller_name_not_blank"),
        ]


class JourneyPlan(models.Model):
    """Private Kazakhstan travel intent; never a booking or supplier inventory."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='journey_plans')
    origin = models.CharField(max_length=40)
    destination = models.CharField(max_length=40)
    date = models.DateField()
    time = models.TimeField()
    passengers = models.PositiveSmallIntegerField(default=1)
    modes = models.CharField(max_length=16, default='bus,train')
    note = models.CharField(max_length=1000, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at', '-id']
        constraints = [
            models.CheckConstraint(condition=~models.Q(origin=models.F('destination')), name='plan_different_cities'),
            models.CheckConstraint(condition=models.Q(passengers__gte=1, passengers__lte=9), name='plan_valid_party'),
        ]
