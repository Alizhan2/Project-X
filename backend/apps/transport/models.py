"""Transport domain: who runs what, where, and when.

Conventions
- Money is `Decimal` with an explicit currency (single demo currency, settings.DEMO_CURRENCY).
- Every timestamp is timezone-aware (stored UTC). A route stores stop times as *minute offsets*
  from the departure's start, so a service crossing midnight needs no special casing.
- Capacity is whole-service: `Departure.places_taken` counts passengers (held + confirmed) for the
  entire run, regardless of which stops they use. A CHECK constraint makes overselling impossible
  even if application code is wrong.
"""

from django.conf import settings
from django.db import models
from django.db.models import F, Q


class Operator(models.Model):
    code = models.SlugField(max_length=16, unique=True)
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name


class OperatorMembership(models.Model):
    """Scopes an operator-role user to exactly one operator (enforced by the unique user FK)."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="membership")
    operator = models.ForeignKey(Operator, on_delete=models.CASCADE, related_name="memberships")


class Hub(models.Model):
    """A town / interchange area grouping several stops (e.g. bus station + railway station)."""

    code = models.SlugField(max_length=16, unique=True)
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name


class Stop(models.Model):
    class Kind(models.TextChoices):
        BUS = "bus", "Bus stop"
        RAIL = "rail", "Railway station"
        TAXI = "taxi", "Taxi rank"

    code = models.SlugField(max_length=16, unique=True)
    name = models.CharField(max_length=100)
    kind = models.CharField(max_length=8, choices=Kind.choices)
    hub = models.ForeignKey(Hub, null=True, blank=True, on_delete=models.PROTECT, related_name="stops")
    # Accessibility: null means "unknown" and is shown as such, never as "no".
    step_free = models.BooleanField(null=True, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class CancellationPolicy(models.Model):
    """Refund rule applied at cancellation time, snapshotted into each booking leg at purchase."""

    name = models.CharField(max_length=100)
    full_refund_hours_before = models.PositiveIntegerField(help_text="Full refund if cancelled at least this many hours before departure.")
    partial_refund_hours_before = models.PositiveIntegerField(help_text="Partial refund if cancelled at least this many hours before departure.")
    partial_refund_percent = models.PositiveSmallIntegerField()

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(partial_refund_percent__lte=100), name="policy_percent_lte_100"),
            models.CheckConstraint(
                condition=Q(partial_refund_hours_before__lte=F("full_refund_hours_before")),
                name="policy_partial_window_within_full",
            ),
        ]

    def __str__(self):
        return self.name


class Route(models.Model):
    class Mode(models.TextChoices):
        BUS = "bus", "Bus"
        TRAIN = "train", "Train"

    operator = models.ForeignKey(Operator, on_delete=models.PROTECT, related_name="routes")
    code = models.SlugField(max_length=16, unique=True)
    name = models.CharField(max_length=120)
    mode = models.CharField(max_length=8, choices=Mode.choices)
    policy = models.ForeignKey(CancellationPolicy, on_delete=models.PROTECT, related_name="routes")

    def __str__(self):
        return f"{self.code} {self.name}"


class RouteStop(models.Model):
    """A stop on a route. Offsets are minutes after the departure's `departs_at` (origin = 0)."""

    route = models.ForeignKey(Route, on_delete=models.CASCADE, related_name="route_stops")
    sequence = models.PositiveSmallIntegerField()
    stop = models.ForeignKey(Stop, on_delete=models.PROTECT, related_name="route_stops")
    arrival_offset_min = models.PositiveIntegerField()
    departure_offset_min = models.PositiveIntegerField()

    class Meta:
        ordering = ["route", "sequence"]
        constraints = [
            models.UniqueConstraint(fields=["route", "sequence"], name="routestop_unique_sequence"),
            models.UniqueConstraint(fields=["route", "stop"], name="routestop_unique_stop"),
            models.CheckConstraint(
                condition=Q(departure_offset_min__gte=F("arrival_offset_min")),
                name="routestop_departs_after_arrival",
            ),
        ]


class Fare(models.Model):
    """Current price for travelling from one stop to a later stop on a route (per passenger)."""

    route = models.ForeignKey(Route, on_delete=models.CASCADE, related_name="fares")
    from_stop = models.ForeignKey(Stop, on_delete=models.PROTECT, related_name="+")
    to_stop = models.ForeignKey(Stop, on_delete=models.PROTECT, related_name="+")
    price = models.DecimalField(max_digits=8, decimal_places=2)
    currency = models.CharField(max_length=3, default=settings.DEMO_CURRENCY)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["route", "from_stop", "to_stop"], name="fare_unique_pair"),
            models.CheckConstraint(condition=Q(price__gt=0), name="fare_price_positive"),
            models.CheckConstraint(condition=~Q(from_stop=F("to_stop")), name="fare_distinct_stops"),
        ]


class Departure(models.Model):
    """One dated run of a route. `departs_at` is the time at the first stop (before any delay)."""

    class Status(models.TextChoices):
        SCHEDULED = "scheduled", "Scheduled"
        DELAYED = "delayed", "Delayed"
        CANCELLED = "cancelled", "Cancelled"

    route = models.ForeignKey(Route, on_delete=models.PROTECT, related_name="departures")
    departs_at = models.DateTimeField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.SCHEDULED)
    delay_minutes = models.PositiveIntegerField(default=0)
    capacity = models.PositiveIntegerField()
    places_taken = models.PositiveIntegerField(default=0)
    # Places occupied outside this system's bookings (only the synthetic demo seed uses this). Invariant checked by
    # `manage.py check_integrity`: places_taken == baseline_places + live reservations.
    baseline_places = models.PositiveIntegerField(default=0)
    wheelchair_accessible = models.BooleanField(null=True, blank=True)  # null = unknown

    class Meta:
        ordering = ["departs_at"]
        indexes = [models.Index(fields=["route", "departs_at"]), models.Index(fields=["departs_at"], name="departure_departs_at_idx")]
        constraints = [
            models.UniqueConstraint(fields=["route", "departs_at"], name="departure_unique_run"),
            models.CheckConstraint(condition=Q(places_taken__lte=F("capacity")), name="departure_no_oversell"),
            models.CheckConstraint(condition=Q(baseline_places__lte=F("places_taken")), name="departure_baseline_within_taken"),
            models.CheckConstraint(
                condition=Q(status="delayed", delay_minutes__gt=0) | ~Q(status="delayed"),
                name="departure_delayed_has_delay",
            ),
        ]

    @property
    def places_left(self):
        return self.capacity - self.places_taken

    def __str__(self):
        return f"{self.route.code} {self.departs_at:%Y-%m-%d %H:%M}"


class TransferLink(models.Model):
    """Explicit movement between two *different* stops (e.g. walking from bus station to railway station).

    Changing at the *same* stop needs no link: settings-level minimum applies (MIN_SAME_STOP_TRANSFER_MIN).
    A pair with no link cannot be used as a connection.
    """

    from_stop = models.ForeignKey(Stop, on_delete=models.CASCADE, related_name="transfers_out")
    to_stop = models.ForeignKey(Stop, on_delete=models.CASCADE, related_name="transfers_in")
    minutes = models.PositiveSmallIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["from_stop", "to_stop"], name="transfer_unique_pair"),
            models.CheckConstraint(condition=~Q(from_stop=F("to_stop")), name="transfer_distinct_stops"),
            models.CheckConstraint(condition=Q(minutes__gt=0), name="transfer_minutes_positive"),
        ]


class TaxiOffer(models.Model):
    """SIMULATED taxi: always dispatchable within service hours, pickup `pickup_wait_min` after the passenger is ready.

    Price is per vehicle (up to `max_passengers`), not per passenger. There is no capacity pool to reserve.
    """

    operator = models.ForeignKey(Operator, on_delete=models.PROTECT, related_name="taxi_offers")
    from_stop = models.ForeignKey(Stop, on_delete=models.PROTECT, related_name="taxi_from")
    to_stop = models.ForeignKey(Stop, on_delete=models.PROTECT, related_name="taxi_to")
    price = models.DecimalField(max_digits=8, decimal_places=2)
    currency = models.CharField(max_length=3, default=settings.DEMO_CURRENCY)
    pickup_wait_min = models.PositiveSmallIntegerField()
    ride_min = models.PositiveSmallIntegerField()
    max_passengers = models.PositiveSmallIntegerField(default=4)
    service_start = models.TimeField(help_text="Earliest local pickup time")
    service_end = models.TimeField(help_text="Latest local pickup time")
    wheelchair_accessible = models.BooleanField(null=True, blank=True)
    policy = models.ForeignKey(CancellationPolicy, on_delete=models.PROTECT, related_name="taxi_offers")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["from_stop", "to_stop"], name="taxi_unique_pair"),
            models.CheckConstraint(condition=Q(price__gt=0), name="taxi_price_positive"),
            models.CheckConstraint(condition=~Q(from_stop=F("to_stop")), name="taxi_distinct_stops"),
        ]
