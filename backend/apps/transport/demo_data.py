"""Deterministic synthetic network for the fictional "Doedu Valley" region.

Everything here is invented. Distances, prices and timetables are NOT real.
Service dates are generated relative to a reference date so the demo never goes stale.
Day offset 1 ("demo day") carries the special scenarios documented in docs/demo-data.md.
"""

from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import transaction

from .models import (
    CancellationPolicy, Departure, Fare, Hub, Operator, Route, RouteStop, Stop, TaxiOffer, TransferLink,
)

HUBS = [("northgate", "Northgate"), ("riverton", "Riverton"), ("lakeside", "Lakeside"), ("portmouth", "Portmouth")]

# code, name, kind, hub, step_free (None = unknown)
STOPS = [
    ("NG-BUS", "Northgate Bus Station", "bus", "northgate", True),
    ("NG-RAIL", "Northgate Central Station", "rail", "northgate", True),
    ("RV-BUS", "Riverton Bus Station", "bus", "riverton", True),
    ("RV-RAIL", "Riverton Station", "rail", "riverton", False),
    ("LK-BUS", "Lakeside Harbour Stop", "bus", "lakeside", None),
    ("PM-BUS", "Portmouth Bus Station", "bus", "portmouth", True),
    ("PM-RAIL", "Portmouth Harbour Station", "rail", "portmouth", True),
    ("MF-BUS", "Millford Green", "bus", None, None),
    ("OB-BUS", "Oakbridge Crossing", "bus", None, False),
    ("PM-MARINA", "Portmouth Marina (taxi rank)", "taxi", "portmouth", None),
]

OPERATORS = [("valley", "Valley Coaches"), ("greenline", "Greenline Express"), ("rail", "Doedu Rail"), ("cabs", "Valley Cabs (simulated)")]

# name, full-refund hours, partial-refund hours, partial percent
POLICIES = {
    "standard": ("Standard: full refund 24h+, 50% 2h+, none after", 24, 2, 50),
    "flexible": ("Flexible: full refund 2h+, none after", 2, 2, 0),
    "taxi": ("Taxi: free cancellation until 1h before pickup", 1, 1, 0),
}

# Explicit walking links between different stops (minutes). Same-stop changes use the global minimum.
TRANSFERS = [
    ("NG-BUS", "NG-RAIL", 8), ("NG-RAIL", "NG-BUS", 8),
    ("RV-BUS", "RV-RAIL", 10), ("RV-RAIL", "RV-BUS", 10),
    ("PM-BUS", "PM-RAIL", 7), ("PM-RAIL", "PM-BUS", 7),
]

# operator, from, to, price EUR (per vehicle), pickup wait, ride, wheelchair, service window (local)
TAXIS = [
    ("PM-RAIL", "PM-MARINA", "14.00", 8, 12, True),
    ("PM-MARINA", "PM-RAIL", "14.00", 8, 12, True),
    ("NG-BUS", "NG-RAIL", "6.50", 6, 7, None),
    ("NG-RAIL", "NG-BUS", "6.50", 6, 7, None),
    ("LK-BUS", "RV-RAIL", "38.00", 15, 45, False),  # one-way on purpose: no taxi back to Lakeside (see no-alternative case)
]
TAXI_SERVICE = ("05:00", "23:59")

# route code, operator, name, policy, price_per_minute (EUR), capacity, wheelchair, stops [(code, arr, dep)]
BUS_ROUTES = [
    ("VC1", "valley", "Northgate – Millford – Riverton", "standard", "0.10", 40, True,
     [("NG-BUS", 0, 0), ("MF-BUS", 25, 26), ("RV-BUS", 55, 55)]),
    ("VC1R", "valley", "Riverton – Millford – Northgate", "standard", "0.10", 40, True,
     [("RV-BUS", 0, 0), ("MF-BUS", 29, 30), ("NG-BUS", 55, 55)]),
    ("VC2", "valley", "Riverton – Oakbridge – Lakeside", "standard", "0.10", 40, None,
     [("RV-BUS", 0, 0), ("OB-BUS", 20, 21), ("LK-BUS", 50, 50)]),
    ("GL1", "greenline", "Northgate – Riverton Express", "flexible", "0.14", 16, True,
     [("NG-BUS", 0, 0), ("RV-BUS", 40, 40)]),
    ("GL2", "greenline", "Riverton – Portmouth Coastal", "flexible", "0.12", 16, False,
     [("RV-BUS", 0, 0), ("PM-BUS", 70, 70)]),
    ("GL3", "greenline", "Northgate – Riverton Night Service", "flexible", "0.12", 16, True,
     [("NG-BUS", 0, 0), ("RV-BUS", 70, 70)]),
]

# Trains (same tuple layout as BUS_ROUTES, price per minute is higher base). code, op, name, policy, per-min, capacity, wheelchair, stops
TRAIN_ROUTES = [
    ("DR1", "rail", "Northgate – Riverton – Portmouth", "standard", "0.08", 120, True,
     [("NG-RAIL", 0, 0), ("RV-RAIL", 30, 35), ("PM-RAIL", 80, 80)]),
    ("DR1R", "rail", "Portmouth – Riverton – Northgate", "standard", "0.08", 120, True,
     [("PM-RAIL", 0, 0), ("RV-RAIL", 45, 50), ("NG-RAIL", 80, 80)]),
]

# route code -> local departure times, on every day offset 0..6
TIMETABLE = {
    "VC1": ["06:00", "08:00", "10:00", "12:00", "14:00", "16:00", "18:00", "20:00"],
    "VC1R": ["07:00", "09:00", "11:00", "13:00", "15:00", "17:00", "19:00"],
    "VC2": ["07:30", "10:30", "13:30", "16:30", "19:30"],
    "GL1": ["07:30", "09:30", "12:30", "17:30"],
    "GL2": ["08:30", "11:30", "15:30"],
    "GL3": ["23:30"],  # arrives 00:40 next day: crosses midnight
    # DR1 reaches Riverton at hh:30 and leaves at hh:35 + 10 => e.g. 08:10 start leaves RV-RAIL 08:45.
    "DR1": [f"{h:02d}:10" for h in range(6, 24)],
    "DR1R": [f"{h:02d}:30" for h in range(6, 22)],
}

DEMO_DAY = 1  # day offset carrying the special scenarios


def reference_date(value=None) -> date:
    if value:
        return value if isinstance(value, date) else date.fromisoformat(value)
    return datetime.now(ZoneInfo(settings.TIME_ZONE)).date()


def _local(day: date, hhmm: str) -> datetime:
    h, m = map(int, hhmm.split(":"))
    return datetime.combine(day, time(h, m), tzinfo=ZoneInfo(settings.TIME_ZONE))


def _price(per_min: str, minutes: int) -> Decimal:
    return (Decimal("1.50") + Decimal(per_min) * minutes).quantize(Decimal("0.10"), rounding=ROUND_HALF_UP)


def ensure_network() -> dict:
    """Create the synthetic reference network (hubs, stops, operators, policies, routes, fares, transfers, taxis) if
    missing. ADDITIVE and idempotent: existing rows (and everything referencing them) are never modified or deleted.
    Returns {operator code: Operator}."""
    hubs = {c: Hub.objects.get_or_create(code=c, defaults={"name": n})[0] for c, n in HUBS}
    stops = {
        c: Stop.objects.get_or_create(code=c, defaults={"name": n, "kind": k, "hub": hubs.get(h), "step_free": sf})[0]
        for c, n, k, h, sf in STOPS
    }
    operators = {c: Operator.objects.get_or_create(code=c, defaults={"name": n})[0] for c, n in OPERATORS}
    policies = {}
    for k, (n, full, part, pct) in POLICIES.items():
        policies[k] = CancellationPolicy.objects.get_or_create(
            name=n, defaults={"full_refund_hours_before": full, "partial_refund_hours_before": part, "partial_refund_percent": pct})[0]
    all_routes = [(Route.Mode.BUS, r) for r in BUS_ROUTES] + [(Route.Mode.TRAIN, r) for r in TRAIN_ROUTES]
    for mode, (code, op, name, pol, per_min, capacity, wheelchair, rstops) in all_routes:
        route, created = Route.objects.get_or_create(
            code=code, defaults={"operator": operators[op], "name": name, "mode": mode, "policy": policies[pol]})
        if not created:
            continue
        for seq, (sc, arr, dep) in enumerate(rstops):
            RouteStop.objects.create(route=route, sequence=seq, stop=stops[sc], arrival_offset_min=arr, departure_offset_min=dep)
        for i, (a, _, dep_a) in enumerate(rstops):
            for b, arr_b, _ in rstops[i + 1:]:
                Fare.objects.create(route=route, from_stop=stops[a], to_stop=stops[b], price=_price(per_min, arr_b - dep_a))
    for a, b, minutes in TRANSFERS:
        TransferLink.objects.get_or_create(from_stop=stops[a], to_stop=stops[b], defaults={"minutes": minutes})
    start, end = (time.fromisoformat(t) for t in TAXI_SERVICE)
    for a, b, price, wait, ride, wheelchair in TAXIS:
        TaxiOffer.objects.get_or_create(from_stop=stops[a], to_stop=stops[b], defaults={
            "operator": operators["cabs"], "price": Decimal(price), "pickup_wait_min": wait, "ride_min": ride,
            "service_start": start, "service_end": end, "wheelchair_accessible": wheelchair, "policy": policies["taxi"]})
    return operators


def extend_schedule(start: date, days: int) -> int:
    """Create the daily timetable for `days` days from `start` for every route; existing departures (and their
    bookings/capacity) are left untouched. Returns the number of departures created. Safe to run repeatedly."""
    created = 0
    capacities = {r[0]: (r[5], r[6]) for r in BUS_ROUTES + TRAIN_ROUTES}   # route code -> (capacity, wheelchair)
    for code, times in TIMETABLE.items():
        route = Route.objects.get(code=code)
        cap, wheelchair = capacities[code]
        for day_off in range(days):
            day = start + timedelta(days=day_off)
            for t in times:
                _, was_created = Departure.objects.get_or_create(
                    route=route, departs_at=_local(day, t), defaults={"capacity": cap, "wheelchair_accessible": wheelchair})
                created += was_created
    return created


@transaction.atomic
def reset_transport_data(ref: date, with_bookings: bool = False):
    """Delete all demo data (transport + everything that references it) and rebuild the transport network.

    Idempotent and deterministic for a given `ref`. User accounts are kept. Dependents are deleted first
    because bookings legitimately PROTECT the services they were bought on.
    """
    from apps.bookings.models import Booking, BookingLeg, Reservation, Traveller
    from apps.core.models import AuditRecord, Job
    from apps.disruptions.models import DisruptionEvent
    from apps.notifications.models import Notification
    from apps.payments.models import PaymentAttempt, Refund

    for model in (Notification, Refund, PaymentAttempt, DisruptionEvent, Reservation, Traveller, BookingLeg, Booking, Job, AuditRecord, TaxiOffer, TransferLink, Departure, Fare, RouteStop, Route, Stop, Hub, CancellationPolicy, Operator):
        model.objects.all().delete()

    operators = ensure_network()
    extend_schedule(ref, 7)
    _ensure_demo_users(operators)
    _apply_scenarios(ref)
    if with_bookings:
        _seed_demo_bookings(ref)


def _dep(code: str, day_off: int, hhmm: str, ref: date) -> Departure:
    return Departure.objects.get(route__code=code, departs_at=_local(ref + timedelta(days=day_off), hhmm))


def _apply_scenarios(ref: date):
    # One place left (capacity 16, 15 already taken by other, simulated passengers).
    d = _dep("GL1", DEMO_DAY, "07:30", ref)
    d.places_taken = d.baseline_places = d.capacity - 1
    d.save(update_fields=["places_taken", "baseline_places"])
    # Cancelled service.
    d = _dep("VC1", DEMO_DAY, "10:00", ref)
    d.status = Departure.Status.CANCELLED
    d.save(update_fields=["status"])
    # Fully booked service.
    d = _dep("GL2", DEMO_DAY, "11:30", ref)
    d.places_taken = d.baseline_places = d.capacity
    d.save(update_fields=["places_taken", "baseline_places"])
    # Delayed service (breaks onward connections in later stages).
    d = _dep("VC1", DEMO_DAY, "08:00", ref)
    d.status, d.delay_minutes = Departure.Status.DELAYED, 45
    d.save(update_fields=["status", "delay_minutes"])


DEMO_USERS = [
    ("demo.passenger@doedu.test", "Demo Passenger (recovery, equal price)", "passenger", None),
    ("demo.pay@doedu.test", "Demo Passenger (recovery, extra payment)", "passenger", None),
    ("demo.refund@doedu.test", "Demo Passenger (recovery, refund)", "passenger", None),
    ("demo.noalt@doedu.test", "Demo Passenger (no alternative)", "passenger", None),
    ("ops.valley@doedu.test", "Valley Coaches Ops", "operator", "valley"),
    ("ops.greenline@doedu.test", "Greenline Ops", "operator", "greenline"),
    ("ops.rail@doedu.test", "Doedu Rail Ops", "operator", "rail"),
    ("admin@doedu.test", "Demo Admin", "admin", None),
]


def demo_password():
    """Password for the SYNTHETIC demo accounts. The documented default is for local development only: in a deployed
    environment (staging/production) it must be supplied explicitly so a public host never has a well-known password."""
    import os

    from django.conf import settings

    value = os.environ.get("DEMO_USER_PASSWORD")
    if value:
        return value
    if settings.IS_DEPLOYED:
        raise RuntimeError("DEMO_USER_PASSWORD must be set to create demo accounts in a deployed environment.")
    return "doedu-demo-2026"


def _ensure_demo_users(operators):
    """Create/refresh SYNTHETIC demo accounts (dev only; the seed command refuses to run without DEBUG)."""
    from apps.accounts.models import User
    from .models import OperatorMembership

    for email, name, role, op in DEMO_USERS:
        user, _ = User.objects.get_or_create(username=email, defaults={"email": email})
        user.email, user.first_name, user.role = email, name, role
        user.is_staff = user.is_superuser = role == "admin"
        user.set_password(demo_password())
        user.save()
        OperatorMembership.objects.filter(user=user).delete()
        if op:
            OperatorMembership.objects.create(user=user, operator=operators[op])


def _seed_demo_bookings(ref):
    """Confirmed, paid SYNTHETIC bookings (made through the real checkout + simulated payment services) that
    the demo operator disrupts live. See docs/demo-script.md for the exact steps per scenario."""
    import uuid

    from apps.accounts.models import User
    from apps.bookings import services as bookings
    from apps.payments import services as payments
    from .models import TaxiOffer

    def dep(code, hhmm):
        return Departure.objects.get(route__code=code, departs_at=_local(ref + timedelta(days=DEMO_DAY), hhmm))

    def service(code, hhmm, a, b):
        return {"departure_id": dep(code, hhmm).pk, "from_stop": a, "to_stop": b}

    taxi = TaxiOffer.objects.get(from_stop__code="PM-RAIL", to_stop__code="PM-MARINA")
    plans = {
        # A: VC1 14:00 -> (walk 10) -> DR1 15:45 -> taxi. A 45+ min delay on VC1 14:00 breaks the train connection.
        "demo.passenger@doedu.test": [service("VC1", "14:00", "NG-BUS", "RV-BUS"), service("DR1", "15:10", "RV-RAIL", "PM-RAIL"),
                                      {"taxi_offer_id": taxi.pk, "from_stop": "PM-RAIL", "to_stop": "PM-MARINA"}],
        # B: cancel VC1 12:00 -> cheapest replacements cost slightly MORE (Greenline express): extra simulated payment.
        "demo.pay@doedu.test": [service("VC1", "12:00", "NG-BUS", "RV-BUS")],
        # C: cancel GL1 12:30 -> VC1 replacements cost slightly LESS: simulated refund of the difference.
        "demo.refund@doedu.test": [service("GL1", "12:30", "NG-BUS", "RV-BUS")],
        # D: DR1 18:10 -> (walk 10) -> VC2 19:30, the last Lakeside bus. A 60 min delay on DR1 18:10 leaves no alternative.
        "demo.noalt@doedu.test": [service("DR1", "18:10", "NG-RAIL", "RV-RAIL"), service("VC2", "19:30", "RV-BUS", "LK-BUS")],
    }
    for email, selection in plans.items():
        user = User.objects.get(username=email)
        booking, _ = bookings.create_booking(
            user=user, selection=selection, passengers=1, traveller_names=[user.first_name], contact_email=email,
            idempotency_key=uuid.uuid4().hex, expected_total=None)
        payments.pay_booking(user=user, reference=booking.reference, idempotency_key=uuid.uuid4().hex, outcome="success")
