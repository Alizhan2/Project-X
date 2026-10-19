"""Journey planning. Read-only: nothing here writes to the database.

Search approach (bounded, time-aware depth-first search over an in-memory snapshot of the network):
  * `load_network` reads routes, stops, fares, transfer links, taxi offers and the dated departures that can matter
    for the search window (a few hundred rows for the demo region).
  * `_extend` grows an itinerary leg by leg, up to MAX_LEGS (3). A next leg may start at the arrival stop (needs
    MIN_SAME_STOP_TRANSFER_MIN) or after an explicit TransferLink to a different stop. No stop is visited twice.
  * Real times = departs_at + stop offset + current delay, as absolute datetimes, so midnight crossings need no
    special handling. Cancelled services and services with fewer free places than passengers are skipped.
  * Pruning: transfer waits above MAX_TRANSFER_WAIT_MIN and journeys above MAX_JOURNEY_HOURS are dropped; at
    transfers only the PER_EDGE_DEPARTURES earliest departures per (route, destination stop) are explored.
Limitations: not guaranteed to find every possible combination; fixed 24h first-departure window; capacity is
whole-service (a passenger blocks a place for the entire run); taxis are simulated and priced per vehicle.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from django.conf import settings
from django.utils import timezone

from apps.transport.models import Departure, Fare, RouteStop, Stop, TaxiOffer, TransferLink

SEARCH_WINDOW = timedelta(hours=24)
MAX_PASSENGERS = 9
MAX_LEGS = 3
PER_EDGE_DEPARTURES = 2
MAX_RESULTS = 40


class OfferError(Exception):
    """A selected offer is no longer valid. `code` is machine-readable for the UI."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


# ----------------------------------------------------------------------------------------- data classes

@dataclass
class Leg:
    from_stop: Stop
    to_stop: Stop
    departs_at: datetime
    arrives_at: datetime
    unit_price: Decimal
    currency: str
    departure: Departure | None = None   # bus / train
    taxi: TaxiOffer | None = None        # simulated taxi

    @property
    def mode(self):
        return "taxi" if self.taxi else self.departure.route.mode

    @property
    def operator_name(self):
        return (self.taxi or self.departure.route).operator.name

    @property
    def route_code(self):
        return "TAXI" if self.taxi else self.departure.route.code

    @property
    def route_name(self):
        return "Taxi (simulated)" if self.taxi else self.departure.route.name

    @property
    def policy(self):
        return (self.taxi or self.departure.route).policy

    @property
    def price_basis(self):
        return "vehicle" if self.taxi else "passenger"

    @property
    def wheelchair_accessible(self):
        return (self.taxi or self.departure).wheelchair_accessible

    def total(self, passengers: int) -> Decimal:
        return self.unit_price if self.taxi else self.unit_price * passengers

    @property
    def selection(self) -> dict:
        if self.taxi:
            ready = self.departs_at - timedelta(minutes=self.taxi.pickup_wait_min)
            return {"taxi_offer_id": self.taxi.pk, "from_stop": self.from_stop.code,
                    "to_stop": self.to_stop.code, "ready_at": ready.isoformat()}
        return {"departure_id": self.departure.pk, "from_stop": self.from_stop.code, "to_stop": self.to_stop.code}

    @property
    def token(self) -> str:
        if self.taxi:
            ready = self.departs_at - timedelta(minutes=self.taxi.pickup_wait_min)
            return f"t{self.taxi.pk}:{self.from_stop.code}:{self.to_stop.code}:{int(ready.timestamp())}"
        return f"d{self.departure.pk}:{self.from_stop.code}:{self.to_stop.code}"

    @property
    def key(self):
        return ("t", self.taxi.pk, self.departs_at) if self.taxi else ("d", self.departure.pk, self.from_stop.pk, self.to_stop.pk)


@dataclass
class Itinerary:
    legs: list[Leg]
    passengers: int
    # Spare minutes at each connection into a fixed-time service (see `_buffers`); empty for direct journeys.
    buffers: list[int] | None = None

    @property
    def currency(self):
        return self.legs[0].currency

    @property
    def departs_at(self):
        return self.legs[0].departs_at

    @property
    def arrives_at(self):
        return self.legs[-1].arrives_at

    @property
    def duration_minutes(self) -> int:
        return int((self.arrives_at - self.departs_at).total_seconds() // 60)

    @property
    def transfers(self) -> int:
        return len(self.legs) - 1

    @property
    def total_price(self) -> Decimal:
        return sum((leg.total(self.passengers) for leg in self.legs), Decimal("0"))

    @property
    def transfer_buffers(self) -> list[int]:
        return [int((b.departs_at - a.arrives_at).total_seconds() // 60) for a, b in zip(self.legs, self.legs[1:])]

    @property
    def min_transfer_buffer_minutes(self):
        """Spare time at the tightest connection, or None when there is no connection to miss."""
        return min(self.buffers) if self.buffers else None

    @property
    def min_places_left(self):
        left = [l.departure.places_left for l in self.legs if l.departure]
        return min(left) if left else None

    @property
    def legs_param(self) -> str:
        return ",".join(l.token for l in self.legs)


def transfer_minutes(net_transfers: dict, a: Stop, b: Stop):
    """Required minutes to change from stop a to stop b, or None if no connection is modelled."""
    if a.pk == b.pk:
        return settings.MIN_SAME_STOP_TRANSFER_MIN
    return net_transfers.get((a.pk, b.pk))


def _buffers(legs, transfers) -> list[int]:
    """Spare minutes per connection: (next departure - arrival) - required transfer time.

    Only connections into fixed-time services (bus/train) count: a taxi leaves when the passenger is ready, so
    there is nothing to miss. This is a plain time difference, not a measured probability of making the connection.
    """
    out = []
    for a, b in zip(legs, legs[1:]):
        if b.taxi:
            continue
        need = transfer_minutes(transfers, a.to_stop, b.from_stop) or 0
        out.append(int((b.departs_at - a.arrives_at).total_seconds() // 60) - need)
    return out


def make_itinerary(legs, passengers, transfers) -> Itinerary:
    it = Itinerary(legs, passengers)
    it.buffers = _buffers(legs, transfers)
    return it


# ------------------------------------------------------------------------------------------- network

class Network:
    def __init__(self, window_start: datetime, window_end: datetime):
        horizon = timedelta(hours=settings.MAX_JOURNEY_HOURS)
        self.stops = {s.pk: s for s in Stop.objects.all()}
        self.route_stops: dict[int, list[RouteStop]] = {}
        for rs in RouteStop.objects.order_by("route_id", "sequence"):
            self.route_stops.setdefault(rs.route_id, []).append(rs)
        self.stops_at: dict[int, list[tuple[int, int]]] = {}
        for rid, lst in self.route_stops.items():
            for i, rs in enumerate(lst):
                self.stops_at.setdefault(rs.stop_id, []).append((rid, i))
        self.fares = {(f.route_id, f.from_stop_id, f.to_stop_id): f for f in Fare.objects.all()}
        self.departures: dict[int, list[Departure]] = {}
        qs = (
            Departure.objects.exclude(status=Departure.Status.CANCELLED)
            .filter(departs_at__gte=window_start - timedelta(hours=12), departs_at__lte=window_end + horizon)
            .select_related("route__operator", "route__policy").order_by("departs_at")
        )
        for d in qs:
            self.departures.setdefault(d.route_id, []).append(d)
        self.transfers = {(t.from_stop_id, t.to_stop_id): t.minutes for t in TransferLink.objects.all()}
        self.taxis: dict[int, list[TaxiOffer]] = {}
        for t in TaxiOffer.objects.select_related("operator", "policy"):
            self.taxis.setdefault(t.from_stop_id, []).append(t)

    def leaves(self, dep: Departure, rs: RouteStop) -> datetime:
        return dep.departs_at + timedelta(minutes=rs.departure_offset_min + dep.delay_minutes)

    def arrives(self, dep: Departure, rs: RouteStop) -> datetime:
        return dep.departs_at + timedelta(minutes=rs.arrival_offset_min + dep.delay_minutes)


def _taxi_leg(offer: TaxiOffer, from_stop: Stop, to_stop: Stop, ready: datetime, passengers: int):
    if passengers > offer.max_passengers:
        return None
    pickup = ready + timedelta(minutes=offer.pickup_wait_min)
    local = timezone.localtime(pickup).time()
    if not (offer.service_start <= local <= offer.service_end):
        return None
    return Leg(from_stop, to_stop, pickup, pickup + timedelta(minutes=offer.ride_min), offer.price, offer.currency, taxi=offer)


# ------------------------------------------------------------------------------------------- search

def search(origin: Stop, destination: Stop, depart_after: datetime, passengers: int, sort: str = "departure",
           now: datetime | None = None, *, max_legs: int = MAX_LEGS, window: timedelta = SEARCH_WINDOW,
           walk_from_start: bool = False, latest_arrival: datetime | None = None) -> list[Itinerary]:
    """`max_legs`, `window`, `walk_from_start` and `latest_arrival` serve disruption recovery: the passenger is
    already at `origin` (and may first walk via a TransferLink), has fewer legs left, and wants to arrive by a deadline."""
    if origin.pk == destination.pk:
        raise ValueError("Origin and destination must differ.")
    now = now or timezone.now()
    window_end = depart_after + window
    net = Network(depart_after, window_end)
    found: dict[tuple, Itinerary] = {}
    earliest = max(depart_after, now)
    max_total = timedelta(hours=settings.MAX_JOURNEY_HOURS)

    def record(legs):
        if legs[-1].arrives_at - legs[0].departs_at > max_total:
            return
        if latest_arrival is not None and legs[-1].arrives_at > latest_arrival:
            return
        key = tuple(l.key for l in legs)
        found.setdefault(key, make_itinerary(list(legs), passengers, net.transfers))

    def options_from(stop: Stop, ready: datetime, first: bool):
        """Yield candidate next legs leaving `stop` no earlier than `ready`."""
        for rid, idx in net.stops_at.get(stop.pk, []):
            rs_list = net.route_stops[rid]
            o_rs = rs_list[idx]
            taken_per_dest: dict[int, int] = {}
            for dep in net.departures.get(rid, []):
                if dep.capacity - dep.places_taken < passengers:
                    continue
                leaves = net.leaves(dep, o_rs)
                if leaves < ready:
                    continue
                if first and leaves > window_end:
                    continue
                if not first and leaves - ready > timedelta(minutes=settings.MAX_TRANSFER_WAIT_MIN):
                    continue
                for d_rs in rs_list[idx + 1:]:
                    fare = net.fares.get((rid, stop.pk, d_rs.stop_id))
                    if fare is None:
                        continue
                    if not first and taken_per_dest.get(d_rs.stop_id, 0) >= PER_EDGE_DEPARTURES:
                        continue
                    taken_per_dest[d_rs.stop_id] = taken_per_dest.get(d_rs.stop_id, 0) + 1
                    yield Leg(stop, net.stops[d_rs.stop_id], leaves, net.arrives(dep, d_rs), fare.price, fare.currency, departure=dep)
        for offer in net.taxis.get(stop.pk, []):
            leg = _taxi_leg(offer, stop, net.stops[offer.to_stop_id], ready, passengers)
            if leg:
                yield leg

    def extend(stop: Stop, ready: datetime, legs: list[Leg], visited: frozenset, first: bool):
        for leg in options_from(stop, ready, first):
            if leg.to_stop.pk in visited:
                continue
            new_legs = legs + [leg]
            if leg.to_stop.pk == destination.pk:
                record(new_legs)
                continue
            if len(new_legs) >= max_legs:
                continue
            seen = visited | {leg.to_stop.pk}
            # Continue at the same stop, or after an explicit transfer to another stop.
            extend(leg.to_stop, leg.arrives_at + timedelta(minutes=settings.MIN_SAME_STOP_TRANSFER_MIN), new_legs, seen, False)
            for (a, b), minutes in net.transfers.items():
                if a == leg.to_stop.pk and b not in seen:
                    extend(net.stops[b], leg.arrives_at + timedelta(minutes=minutes), new_legs, seen | {b}, False)

    extend(origin, earliest, [], frozenset({origin.pk}), True)
    if walk_from_start:
        for (a, b), minutes in net.transfers.items():
            if a == origin.pk and b != destination.pk:
                extend(net.stops[b], earliest + timedelta(minutes=minutes), [], frozenset({origin.pk, b}), True)
    results = sorted(found.values(), key=SORTS[sort])
    return results[:MAX_RESULTS]


def _buffer_key(i: Itinerary):
    b = i.min_transfer_buffer_minutes
    return (0, 0) if b is None else (1, -b)  # direct journeys (no connection to miss) first, then largest buffer


SORTS = {
    "price": lambda i: (i.total_price, i.departs_at),
    "duration": lambda i: (i.duration_minutes, i.departs_at),
    "departure": lambda i: (i.departs_at, i.total_price),
    "buffer": lambda i: (_buffer_key(i), i.duration_minutes, i.total_price),
}


# ---------------------------------------------------------------------------------------- validation

def build_itinerary(selection: list[dict], passengers: int, now: datetime, previous: Leg | None = None) -> Itinerary:
    """Recompute an itinerary from current database state for the selected legs (used at checkout).

    Items: {"departure_id", "from_stop", "to_stop"} for bus/train or {"taxi_offer_id", "from_stop", "to_stop",
    "ready_at"} for a simulated taxi. Times, prices and statuses are derived from the database, never from the
    client. Connections are validated: same-stop changes need MIN_SAME_STOP_TRANSFER_MIN, different stops need an
    explicit TransferLink, and the next departure must leave after arrival + transfer time. Capacity is NOT
    checked here: the caller does that under a row lock. `previous` is an already-travelled/booked leg that the
    first selected leg must connect to (disruption recovery); it is not part of the returned itinerary.
    """
    if not selection:
        raise OfferError("invalid_leg", "No legs selected.")
    if len(selection) > MAX_LEGS:
        raise OfferError("invalid_leg", f"A journey has at most {MAX_LEGS} legs.")
    transfers = {(t.from_stop_id, t.to_stop_id): t.minutes for t in TransferLink.objects.all()}
    legs: list[Leg] = []
    for i, item in enumerate(selection):
        origin = Stop.objects.filter(code=item["from_stop"]).first()
        dest = Stop.objects.filter(code=item["to_stop"]).first()
        if origin is None or dest is None or origin.pk == dest.pk:
            raise OfferError("invalid_leg", "Unknown or identical stops.")
        ready = None
        prev = legs[-1] if legs else previous
        if prev is not None:
            if prev.to_stop.pk != origin.pk and (prev.to_stop.pk, origin.pk) not in transfers:
                raise OfferError("invalid_connection", f"No transfer is possible from {prev.to_stop.name} to {origin.name}.")
            need = transfer_minutes(transfers, prev.to_stop, origin)
            ready = prev.arrives_at + timedelta(minutes=need)
        if item.get("taxi_offer_id") is not None:
            leg = _build_taxi(item, origin, dest, ready, passengers, now)
        else:
            leg = _build_service(item, origin, dest, now)
        if ready is not None and leg.departs_at < ready + timedelta(minutes=leg.taxi.pickup_wait_min if leg.taxi else 0):
            raise OfferError("connection_missed", "The connection is no longer possible: the previous service arrives too late.")
        legs.append(leg)
    return make_itinerary(legs, passengers, transfers)


def _build_service(item, origin, dest, now) -> Leg:
    dep = Departure.objects.select_related("route__operator", "route__policy").filter(pk=item.get("departure_id")).first()
    if dep is None:
        raise OfferError("unavailable", "This service is no longer available.")
    if dep.status == Departure.Status.CANCELLED:
        raise OfferError("unavailable", "This service has been cancelled.")
    o_rs = RouteStop.objects.filter(route=dep.route, stop=origin).first()
    d_rs = RouteStop.objects.filter(route=dep.route, stop=dest).first()
    fare = Fare.objects.filter(route=dep.route, from_stop=origin, to_stop=dest).first()
    if not (o_rs and d_rs and fare) or o_rs.sequence >= d_rs.sequence:
        raise OfferError("invalid_leg", "These stops are not served in this order by the service.")
    delay = timedelta(minutes=dep.delay_minutes)
    leaves = dep.departs_at + timedelta(minutes=o_rs.departure_offset_min) + delay
    if leaves <= now:
        raise OfferError("unavailable", "This service has already departed.")
    arrives = dep.departs_at + timedelta(minutes=d_rs.arrival_offset_min) + delay
    return Leg(origin, dest, leaves, arrives, fare.price, fare.currency, departure=dep)


def _build_taxi(item, origin, dest, ready, passengers, now) -> Leg:
    offer = TaxiOffer.objects.select_related("operator", "policy").filter(pk=item["taxi_offer_id"]).first()
    if offer is None or offer.from_stop_id != origin.pk or offer.to_stop_id != dest.pk:
        raise OfferError("unavailable", "This taxi is no longer available.")
    if ready is None:  # first leg: the passenger-provided ready time
        try:
            ready = datetime.fromisoformat(item["ready_at"])
        except (KeyError, ValueError):
            raise OfferError("invalid_leg", "A taxi as first leg needs a ready time.")
        if timezone.is_naive(ready):
            ready = timezone.make_aware(ready)
    leg = _taxi_leg(offer, origin, dest, ready, passengers)
    if leg is None:
        raise OfferError("unavailable", "No taxi is available at that time for this group size.")
    if leg.departs_at <= now:
        raise OfferError("unavailable", "This pickup time has already passed.")
    return leg
