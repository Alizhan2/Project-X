from datetime import datetime, timedelta, time
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from apps.core.throttling import throttle
from .catalog import CITIES, CITY_IDS, CURRENCY, TIMEZONE, MAX_JOURNEY_HOURS
from .providers import ProviderUnavailable, SearchQuery, get_provider


class SearchInput(serializers.Serializer):
    origin = serializers.ChoiceField(choices=CITY_IDS)
    destination = serializers.ChoiceField(choices=CITY_IDS)
    date = serializers.DateField()
    time = serializers.TimeField(default=time(6, 0), input_formats=['%H:%M'])
    passengers = serializers.IntegerField(min_value=1, max_value=9, default=1)
    modes = serializers.ChoiceField(choices=('bus,train', 'bus', 'train'), default='bus,train')

    def validate(self, data):
        if data['origin'] == data['destination']:
            raise serializers.ValidationError({'destination': 'Origin and destination must differ.'})
        local = datetime.combine(data['date'], data['time'], tzinfo=ZoneInfo(TIMEZONE))
        now = timezone.now()
        if local <= now:
            raise serializers.ValidationError({'date': 'Choose a departure time in the future.'})
        if local > now + timedelta(days=365):
            raise serializers.ValidationError({'date': 'Choose a date within the next year.'})
        data['depart_after'] = local
        return data


@extend_schema(responses={200: dict})
@api_view(['GET'])
@permission_classes([AllowAny])
def catalog(request):
    return Response({'country': 'KZ', 'currency': CURRENCY, 'timezone': TIMEZONE,
                     'max_journey_hours': MAX_JOURNEY_HOURS, 'cities': CITIES,
                     'provider': {'code': '1tr', 'name': '1TR.kz', 'status': 'awaiting_partner_access'},
                     'booking_enabled': False})


@extend_schema(parameters=[SearchInput], responses={200: dict, 400: dict, 503: dict})
@throttle('search')
@api_view(['GET'])
@permission_classes([AllowAny])
def search(request):
    data = SearchInput(data=request.query_params)
    data.is_valid(raise_exception=True)
    v = data.validated_data
    query = SearchQuery(v['origin'], v['destination'], v['depart_after'], v['passengers'], tuple(v['modes'].split(',')))
    try:
        offers = get_provider().search(query)
    except ProviderUnavailable:
        return Response({'code': 'provider_not_connected', 'provider': '1tr',
                         'message': 'Real ticket search is awaiting provider access. No prices or availability have been checked.',
                         'currency': CURRENCY, 'timezone': TIMEZONE, 'booking_enabled': False}, status=503)
    # Future adapter output must pass this boundary before being offered to a customer.
    now = timezone.now()
    valid = [o for o in offers if o.provider == '1tr' and o.origin == query.origin and o.destination == query.destination
             and o.passengers == query.passengers and o.mode in query.modes and o.currency == query.currency and o.departs_at >= query.depart_after
             and o.expires_at > now and o.checked_at <= now
             and o.arrives_at - o.departs_at <= timedelta(hours=query.max_journey_hours)]
    return Response({'currency': CURRENCY, 'timezone': TIMEZONE, 'booking_enabled': False,
                     'results': [{'provider': o.provider, 'offer_id': o.provider_offer_id,
                                  'departs_at': o.departs_at.astimezone(ZoneInfo(TIMEZONE)),
                                  'arrives_at': o.arrives_at.astimezone(ZoneInfo(TIMEZONE)),
                                  'total_price': str(o.total_price.quantize(Decimal('0.01'))),
                                  'currency': o.currency, 'mode': o.mode,
                                  'checked_at': o.checked_at, 'expires_at': o.expires_at} for o in valid]})
