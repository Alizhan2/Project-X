from django.conf import settings
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.decorators import api_view
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from django.http import Http404

from apps.bookings.services import BookingError
from apps.core.throttling import throttle
from apps.bookings.views import Conflict, _own_booking, booking_payload, idempotency_key

from . import services


class PayIn(serializers.Serializer):
    outcome = serializers.ChoiceField(choices=services.OUTCOMES, help_text="Simulator only: force success or failure.")


@extend_schema(
    request=PayIn, responses={200: dict, 409: dict},
    parameters=[OpenApiParameter("Idempotency-Key", str, OpenApiParameter.HEADER, required=True)],
)
@throttle("booking")
@api_view(["POST"])
def pay(request, reference):
    """SIMULATED payment. Never accepts card details. Disabled when the launch mode does not allow simulation."""
    if not settings.SIMULATION_ENABLED:
        return Response({"code": "payments_not_configured", "message": "Payments are not available in this deployment."}, status=503)
    key = idempotency_key(request)
    data = PayIn(data=request.data)
    data.is_valid(raise_exception=True)
    try:
        attempt, replayed = services.pay_booking(
            user=request.user, reference=reference, idempotency_key=key, outcome=data.validated_data["outcome"]
        )
    except BookingError as e:
        raise Conflict(e.code, e.message) from e
    if attempt is None:
        raise Http404
    return Response({
        "replayed": replayed,
        "payment": {"status": attempt.status, "failure_reason": attempt.failure_reason, "amount": f"{attempt.amount:.2f}"},
        "booking": booking_payload(_own_booking(request, reference)),
    })
