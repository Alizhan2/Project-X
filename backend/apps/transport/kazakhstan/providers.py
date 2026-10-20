"""Supplier boundary. No undocumented endpoints, guessed auth or demo fallback.

Implement OneTR.search only after receiving the partner specification and sandbox.
The browser never talks to a supplier directly. Booking is intentionally not exposed.
"""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol


@dataclass(frozen=True)
class SearchQuery:
    origin: str
    destination: str
    depart_after: datetime
    passengers: int
    modes: tuple[str, ...]
    max_journey_hours: int = 72
    currency: str = 'KZT'


@dataclass(frozen=True)
class Offer:
    provider: str
    provider_offer_id: str
    origin: str
    destination: str
    departs_at: datetime
    arrives_at: datetime
    total_price: Decimal
    currency: str
    checked_at: datetime
    expires_at: datetime
    mode: str
    passengers: int

    def __post_init__(self):
        if not self.provider or not self.provider_offer_id:
            raise ValueError('Supplier identity is required')
        if not isinstance(self.total_price, Decimal) or not self.total_price.is_finite() or self.total_price < 0:
            raise ValueError('Price must be a finite nonnegative Decimal')
        if self.total_price != self.total_price.quantize(Decimal('0.01')) or self.currency != 'KZT':
            raise ValueError('Unsupported money format')
        if any(dt.tzinfo is None or dt.utcoffset() is None for dt in (self.departs_at, self.arrives_at, self.checked_at, self.expires_at)):
            raise ValueError('Supplier times must be timezone aware')
        if self.arrives_at <= self.departs_at or self.expires_at <= self.checked_at:
            raise ValueError('Invalid supplier time interval')
        if not 1 <= self.passengers <= 9:
            raise ValueError('Invalid passenger count')
        if self.mode not in ('bus', 'train'):
            raise ValueError('Unsupported transport mode')


class ProviderUnavailable(Exception):
    """A known, public-safe failure; never include supplier payloads or credentials."""


class SearchProvider(Protocol):
    code: str
    def search(self, query: SearchQuery) -> list[Offer]: ...


class OneTR:
    code = '1tr'

    def search(self, query: SearchQuery) -> list[Offer]:
        raise ProviderUnavailable('awaiting_partner_access')


def get_provider() -> SearchProvider:
    return OneTR()
