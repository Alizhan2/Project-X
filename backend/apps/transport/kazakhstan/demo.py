"""Bookable synthetic services between real Kazakhstan city names.

Prices, station accessibility, durations and timetables are invented examples.
There is no supplier API, distance calculation or real ticket availability here.
Geography is additive; dated services are created only for the requested pair.
"""
from datetime import datetime, time, timedelta
from decimal import Decimal
import hashlib
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import connection, models, transaction
from django.db.models import F, Value
from django.utils import timezone

from apps.core.models import AuditRecord
from apps.planning.services import Itinerary, Leg, SORTS
from apps.transport.models import CancellationPolicy, Departure, Fare, Hub, Operator, Route, RouteStop, Stop, TransferLink

from .catalog import CITIES, CURRENCY, TIMEZONE

NETWORK_LOCK = 7_330_003
SCHEDULE_ACTION = 'demo.kz_schedule'
POLICY_NAME = 'Kazakhstan demo: full refund 24h+, 50% 2h+, none after'
OPERATORS = {
    'bus': ('kz-demo-bus', 'Doedu KZ Bus (simulated)'),
    'train': ('kz-demo-rail', 'Doedu KZ Rail (simulated)'),
}
_CITIES = {city['id']: city for city in CITIES}
_ZONE = ZoneInfo(TIMEZONE)


class DemoUnavailable(Exception):
    """Synthetic inventory cannot be created outside a simulation-enabled launch."""


def _require_demo():
    if not settings.SIMULATION_ENABLED:
        raise DemoUnavailable('Kazakhstan demo services require simulation mode.')


def _lock_network():
    with connection.cursor() as cursor:
        cursor.execute('SELECT pg_advisory_xact_lock(%s)', [NETWORK_LOCK])


def stop_code(city_id, mode):
    """Stable fictional bus/rail stop code, separate from any supplier station ID."""
    suffix = {'bus': 'B', 'train': 'R'}[mode]
    return f"KZ-{_CITIES[city_id]['kato']}-{suffix}"


def _ensure_network():
    hubs = Hub.objects.filter(code__startswith='KZ-').in_bulk(field_name='code')
    missing_hubs = [Hub(code='KZ-' + city['kato'], name=city['name']['en']) for city in CITIES
                    if 'KZ-' + city['kato'] not in hubs]
    if missing_hubs:
        Hub.objects.bulk_create(missing_hubs, ignore_conflicts=True)
        hubs = Hub.objects.filter(code__startswith='KZ-').in_bulk(field_name='code')
    stops = Stop.objects.filter(code__startswith='KZ-').in_bulk(field_name='code')
    missing_stops = [Stop(code=stop_code(city['id'], mode), name=city['name']['en'],
                          kind='bus' if mode == 'bus' else 'rail', hub=hubs['KZ-' + city['kato']], step_free=True)
                     for city in CITIES for mode in OPERATORS if stop_code(city['id'], mode) not in stops]
    if missing_stops:
        Stop.objects.bulk_create(missing_stops, ignore_conflicts=True)
        stops = Stop.objects.filter(code__startswith='KZ-').in_bulk(field_name='code')
    operators = {mode: Operator.objects.get_or_create(code=code, defaults={'name': name})[0]
                 for mode, (code, name) in OPERATORS.items()}
    # Policy names have no unique constraint; the shared transaction lock prevents duplicate first creation.
    policy = CancellationPolicy.objects.filter(name=POLICY_NAME).order_by('pk').first()
    if policy is None:
        policy = CancellationPolicy.objects.create(name=POLICY_NAME, full_refund_hours_before=24,
                                                   partial_refund_hours_before=2, partial_refund_percent=50)
    existing = set(TransferLink.objects.filter(from_stop_id__in=[stop.pk for stop in stops.values()])
                   .values_list('from_stop_id', 'to_stop_id'))
    links = []
    for city in CITIES:
        bus, rail = (stops[stop_code(city['id'], mode)] for mode in OPERATORS)
        for origin, destination in ((bus, rail), (rail, bus)):
            if (origin.pk, destination.pk) not in existing:
                links.append(TransferLink(from_stop=origin, to_stop=destination, minutes=10,
                                          boarding_buffer_minutes=5, step_free=True))
    if links:
        TransferLink.objects.bulk_create(links, ignore_conflicts=True)
    return operators, policy, stops


@transaction.atomic
def ensure_network():
    """Add missing 90 hubs, 180 stops/transfers, two operators and one policy; return operators by code.

    No routes, departures, accounts or reservations are created by this helper.
    Existing transport records and operator changes are preserved.
    """
    _require_demo()
    _lock_network()
    operators, _policy, _stops = _ensure_network()
    return {operator.code: operator for operator in operators.values()}


def _illustrative_values(origin, destination, mode):
    pair = ':'.join(sorted((origin['kato'], destination['kato'])))
    seed = int(hashlib.sha256(pair.encode()).hexdigest()[:12], 16)
    bus_minutes = 90 + (seed % 11) * 45
    minutes = bus_minutes if mode == 'bus' else max(60, bus_minutes * 4 // 5)
    price = 1800 + (seed % 25) * 350 if mode == 'bus' else 3500 + (seed % 31) * 450
    return minutes, Decimal(price).quantize(Decimal('0.01'))


def _ensure_pair(query, operators, policy, stops):
    origin, destination = _CITIES[query.origin], _CITIES[query.destination]
    identity = f"{origin['kato']}:{destination['kato']}"
    digest = hashlib.sha256(identity.encode()).hexdigest()[:12]
    day = query.depart_after.astimezone(_ZONE).date()
    choices = []
    for mode in dict.fromkeys(query.modes):
        first, last = stops[stop_code(query.origin, mode)], stops[stop_code(query.destination, mode)]
        minutes, price = _illustrative_values(origin, destination, mode)
        route, _ = Route.objects.get_or_create(code=('KZB' if mode == 'bus' else 'KZT') + digest,
                    defaults={'name': f"{origin['name']['en']} – {destination['name']['en']}",
                              'mode': mode, 'operator': operators[mode], 'policy': policy})
        start, _ = RouteStop.objects.get_or_create(route=route, sequence=0,
                    defaults={'stop': first, 'arrival_offset_min': 0, 'departure_offset_min': 0})
        end, _ = RouteStop.objects.get_or_create(route=route, sequence=1,
                    defaults={'stop': last, 'arrival_offset_min': minutes, 'departure_offset_min': minutes})
        fare, _ = Fare.objects.get_or_create(route=route, from_stop=first, to_stop=last,
                                             defaults={'price': price, 'currency': CURRENCY})
        times = (6, 12, 18) if mode == 'bus' else (7, 13, 19)
        for offset in (0, 1):
            service_day = day + timedelta(days=offset)
            marker = {'action': SCHEDULE_ACTION, 'object_type': 'route_day',
                      'object_id': f'{route.pk}:{service_day.isoformat()}'}
            if AuditRecord.objects.filter(**marker).exists():
                continue
            # A moved/deleted departure must not resurrect its original template slot on the next search.
            Departure.objects.bulk_create([
                Departure(route=route, departs_at=datetime.combine(service_day, time(hour), tzinfo=_ZONE),
                          capacity=40 if mode == 'bus' else 100, wheelchair_accessible=True)
                for hour in times
            ], ignore_conflicts=True)
            AuditRecord.objects.create(**marker, detail={'simulated': True})
        if start.stop_id == first.pk and end.stop_id == last.pk:
            choices.append((route, start, end, fare, first, last))
    return choices


@transaction.atomic
def search_demo(query, sort='departure'):
    """Generate this pair's two-day synthetic timetable and return current direct planner itineraries."""
    _require_demo()
    if (query.origin not in _CITIES or query.destination not in _CITIES or query.origin == query.destination
            or query.currency != CURRENCY or type(query.passengers) is not int or not 1 <= query.passengers <= 9
            or not query.modes or not set(query.modes) <= set(OPERATORS)
            or timezone.is_naive(query.depart_after) or sort not in SORTS):
        raise ValueError('Invalid Kazakhstan demo search.')
    _lock_network()
    operators, policy, stops = _ensure_network()
    choices = _ensure_pair(query, operators, policy, stops)
    # Positive delays can move a previously scheduled departure into this search's live window.
    delay = models.ExpressionWrapper(F('delay_minutes') * Value(timedelta(minutes=1)), output_field=models.DurationField())
    effective = models.ExpressionWrapper(F('departs_at') + delay, output_field=models.DateTimeField())
    window_end = query.depart_after + timedelta(hours=24)
    departures = (Departure.objects.filter(route_id__in=[choice[0].pk for choice in choices])
                  .exclude(status=Departure.Status.CANCELLED)
                  .annotate(effective_at=effective)
                  .filter(effective_at__gte=query.depart_after, effective_at__lt=window_end,
                          capacity__gte=F('places_taken') + query.passengers)
                  .select_related('route__operator', 'route__policy'))
    by_route = {route.pk: (start, end, fare, first, last) for route, start, end, fare, first, last in choices}
    found = []
    for departure in departures:
        start, end, fare, first, last = by_route[departure.route_id]
        if fare.currency != CURRENCY:
            continue
        base = departure.departs_at.astimezone(_ZONE) + timedelta(minutes=departure.delay_minutes)
        leaves = base + timedelta(minutes=start.departure_offset_min)
        arrives = base + timedelta(minutes=end.arrival_offset_min)
        if (not query.depart_after <= leaves < window_end or arrives <= leaves
                or arrives - leaves > timedelta(hours=query.max_journey_hours)):
            continue
        leg = Leg(first, last, leaves, arrives, fare.price, fare.currency, departure=departure)
        found.append(Itinerary([leg], query.passengers, buffers=[], connections=[]))
    return sorted(found, key=SORTS[sort])
