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
