from django.db import transaction
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.core.throttling import throttle

from .models import SavedTraveller, User

MAX_SAVED = 10


class TravellerIn(serializers.Serializer):
    full_name = serializers.CharField(max_length=150)

    def validate_full_name(self, value):
        value = " ".join(value.split())          # trim and collapse whitespace
        if not value:
            raise serializers.ValidationError("Enter a name.")
        return value


class TravellerOut(serializers.ModelSerializer):
    class Meta:
        model = SavedTraveller
        fields = ["id", "full_name"]


@extend_schema(methods=["GET"], responses=TravellerOut(many=True))
@extend_schema(methods=["POST"], request=TravellerIn, responses={200: TravellerOut, 201: TravellerOut})
@throttle("booking")
@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def collection(request):
    if request.method == "GET":
        return Response(TravellerOut(SavedTraveller.objects.filter(user=request.user), many=True).data)
    data = TravellerIn(data=request.data)
    data.is_valid(raise_exception=True)
    name = data.validated_data["full_name"]
    with transaction.atomic():
        User.objects.select_for_update().get(pk=request.user.pk)    # serialise saves per account: limit and de-duplication stay exact
        existing = SavedTraveller.objects.filter(user=request.user, full_name__iexact=name).first()
        if existing:
            return Response(TravellerOut(existing).data)
        if SavedTraveller.objects.filter(user=request.user).count() >= MAX_SAVED:
            raise ValidationError({"detail": f"You can save up to {MAX_SAVED} travellers. Remove one before adding another."})
        saved = SavedTraveller.objects.create(user=request.user, full_name=name)
    return Response(TravellerOut(saved).data, status=201)


@extend_schema(responses={204: None})
@throttle("booking")
@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def remove(request, pk):
    get_object_or_404(SavedTraveller, pk=pk, user=request.user).delete()     # someone else's id behaves like a missing one
    return Response(status=204)
