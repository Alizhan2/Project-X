"""Presentation timezones follow the transport market, never the fare currency."""
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone


def timezone_for_stops(*stops):
    codes = [getattr(stop, "code", stop) for stop in stops]
    return "Asia/Almaty" if any(isinstance(code, str) and code.startswith("KZ-") for code in codes) else settings.TIME_ZONE


def itinerary_timezone(itinerary):
    return timezone_for_stops(*(stop for leg in itinerary.legs for stop in (leg.from_stop, leg.to_stop)))


def route_timezone(route):
    first = next(iter(route.route_stops.all()), None)
    return timezone_for_stops(first.stop if first else None)


def booking_timezone(booking):
    return timezone_for_stops(*(stop for leg in booking.legs.all() for stop in (leg.from_stop, leg.to_stop)))


def local_datetime(value, zone):
    return timezone.localtime(value, ZoneInfo(zone)) if value is not None else None


def local_iso(value, zone):
    return local_datetime(value, zone).isoformat() if value is not None else None


def city_id_for_stop(stop):
    from .kazakhstan.catalog import CITIES

    code = getattr(stop, "code", stop)
    bits = code.split("-") if isinstance(code, str) else []
    if len(bits) != 3 or bits[0] != "KZ" or len(bits[1]) != 9 or not bits[1].isdigit() or bits[2] not in ("B", "R"):
        return None
    return next((city["id"] for city in CITIES if city.get("kato") == bits[1]), None)
