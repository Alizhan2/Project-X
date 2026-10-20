from django.db import transaction
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from apps.core.throttling import throttle
from apps.transport.kazakhstan.views import SearchInput
from .models import JourneyPlan, User


class PlanInput(SearchInput):
    note = serializers.CharField(max_length=1000, allow_blank=True, default='')

    def validate(self, data):
        data = super().validate(data)
        data.pop('depart_after')
        return data


class PlanOutput(serializers.ModelSerializer):
    class Meta:
        model = JourneyPlan
        fields = ['id', 'origin', 'destination', 'date', 'time', 'passengers', 'modes', 'note', 'updated_at']


@extend_schema(methods=['GET'], responses=PlanOutput(many=True))
@extend_schema(methods=['POST'], request=PlanInput, responses={201: PlanOutput})
@throttle('booking')
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def collection(request):
    if request.method == 'GET':
        return Response(PlanOutput(JourneyPlan.objects.filter(user=request.user), many=True).data)
    data = PlanInput(data=request.data)
    data.is_valid(raise_exception=True)
    with transaction.atomic():
        User.objects.select_for_update().get(pk=request.user.pk)
        if JourneyPlan.objects.filter(user=request.user).count() >= 50:
            raise serializers.ValidationError({'detail': 'You can save up to 50 plans. Delete one before adding another.'})
        plan = JourneyPlan.objects.create(user=request.user, **data.validated_data)
    return Response(PlanOutput(plan).data, status=201)


@extend_schema(methods=['PUT'], request=PlanInput, responses=PlanOutput)
@extend_schema(methods=['DELETE'], responses={204: None})
@throttle('booking')
@api_view(['PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def detail(request, pk):
    with transaction.atomic():
        plan = get_object_or_404(JourneyPlan.objects.select_for_update(), user=request.user, pk=pk)
        if request.method == 'DELETE':
            plan.delete()
            return Response(status=204)
        data = PlanInput(data=request.data)
        data.is_valid(raise_exception=True)
        for key, value in data.validated_data.items():
            setattr(plan, key, value)
        plan.save()
    return Response(PlanOutput(plan).data)
