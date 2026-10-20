from django.db import transaction
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.core.throttling import throttle
from apps.transport.models import Stop
from .models import FavoriteRoute, User


class FavoriteIn(serializers.Serializer):
    origin = serializers.SlugRelatedField(slug_field='code', queryset=Stop.objects.all())
    destination = serializers.SlugRelatedField(slug_field='code', queryset=Stop.objects.all())

    def validate(self, attrs):
        if attrs['origin'] == attrs['destination']:
            raise serializers.ValidationError({'destination': 'Destination must differ from origin.'})
        return attrs


class FavoriteOut(serializers.ModelSerializer):
    origin = serializers.CharField(source='origin.code')
    origin_name = serializers.CharField(source='origin.name')
    destination = serializers.CharField(source='destination.code')
    destination_name = serializers.CharField(source='destination.name')

    class Meta:
        model = FavoriteRoute
        fields = ['id', 'origin', 'origin_name', 'destination', 'destination_name']


@extend_schema(methods=['GET'], responses=FavoriteOut(many=True))
@extend_schema(methods=['POST'], request=FavoriteIn, responses={200: FavoriteOut, 201: FavoriteOut})
@throttle('booking')
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def routes(request):
    if request.method == 'GET':
        favorites = FavoriteRoute.objects.filter(user=request.user).select_related('origin', 'destination')
        return Response(FavoriteOut(favorites, many=True).data)
    data = FavoriteIn(data=request.data)
    data.is_valid(raise_exception=True)
    with transaction.atomic():
        # Serialize saves per account so retries and the size limit remain deterministic.
        User.objects.select_for_update().get(pk=request.user.pk)
        fields = {'user': request.user, **data.validated_data}
        existing = FavoriteRoute.objects.filter(**fields).first()
        if existing:
            return Response(FavoriteOut(existing).data)
        if FavoriteRoute.objects.filter(user=request.user).count() >= 50:
            raise ValidationError({'detail': 'You can save up to 50 directions. Remove one before adding another.'})
        favorite = FavoriteRoute.objects.create(**fields)
    return Response(FavoriteOut(favorite).data, status=201)


@extend_schema(responses={204: None})
@throttle('booking')
@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def remove(request, pk):
    favorite = get_object_or_404(FavoriteRoute, pk=pk, user=request.user)
    favorite.delete()
    return Response(status=204)
