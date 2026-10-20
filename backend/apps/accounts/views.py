from django.conf import settings
from django.core.cache import cache
from django.contrib.auth import authenticate, login, logout, password_validation
from django.core.exceptions import ValidationError as DjangoValidationError
from django.middleware.csrf import get_token
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.exceptions import PermissionDenied, Throttled, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from apps.core.throttling import throttle

from .models import User


class StrictCsrfSessionAuth(SessionAuthentication):
    """Session auth that enforces CSRF even for anonymous requests (login/register CSRF)."""

    def authenticate(self, request):
        self.enforce_csrf(request)
        return super().authenticate(request)


def user_payload(user):
    operator = getattr(getattr(user, "membership", None), "operator", None)
    return {
        "id": user.pk,
        "email_verified": user.email_verified_at is not None,
        "email": user.email,
        "name": user.get_full_name() or user.email,
        "role": user.role,
        "operator": operator.name if operator else None,
    }


class RegisterIn(serializers.Serializer):
    email = serializers.EmailField()
    full_name = serializers.CharField(max_length=150)
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate_email(self, value):
        value = value.lower()
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return value

    def validate(self, attrs):
        try:
            password_validation.validate_password(attrs["password"], User(username=attrs["email"], email=attrs["email"]))
        except DjangoValidationError as e:
            raise serializers.ValidationError({"password": list(e.messages)})
        return attrs


class LoginIn(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(trim_whitespace=False)


@extend_schema(responses=inline_serializer("Csrf", {"detail": serializers.CharField()}))
@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def csrf(request):
    """Sets the `csrftoken` cookie. The SPA echoes it in the X-CSRFToken header on unsafe requests."""
    get_token(request)
    return Response({"detail": "CSRF cookie set."})


@extend_schema(request=RegisterIn, responses={201: OpenApiTypes.OBJECT})
@throttle("register", by_ip=True)
@api_view(["POST"])
@authentication_classes([StrictCsrfSessionAuth])
@permission_classes([AllowAny])
def register(request):
    """Create a passenger account (the only self-service role) and sign in. Can be closed with REGISTRATION_ENABLED=false.
    Email verification is available separately; the synthetic demo does not gate bookings on it."""
    if not settings.REGISTRATION_ENABLED:
        raise PermissionDenied("Registration is closed.")
    data = RegisterIn(data=request.data)
    data.is_valid(raise_exception=True)
    v = data.validated_data
    user = User.objects.create_user(
        username=v["email"], email=v["email"], password=v["password"],
        first_name=v["full_name"], role=User.Role.PASSENGER,
    )
    login(request, user)
    return Response(user_payload(user), status=201)


@extend_schema(request=LoginIn, responses={200: OpenApiTypes.OBJECT})
@throttle("login", by_ip=True)
@api_view(["POST"])
@authentication_classes([StrictCsrfSessionAuth])
@permission_classes([AllowAny])
def login_view(request):
    data = LoginIn(data=request.data)
    data.is_valid(raise_exception=True)
    email = data.validated_data["email"].lower()
    key = f"loginfail:{email}"
    fails = cache.get(key, 0)
    if fails >= settings.LOGIN_FAILURE_LIMIT:   # per-account lockout, independent of the per-IP throttle
        raise Throttled(wait=settings.LOGIN_FAILURE_WINDOW_SECONDS)
    user = authenticate(request, username=email, password=data.validated_data["password"])
    if user is None:
        cache.set(key, fails + 1, settings.LOGIN_FAILURE_WINDOW_SECONDS)
        raise ValidationError({"detail": "Email or password is incorrect."})
    cache.delete(key)
    login(request, user)
    return Response(user_payload(user))


@extend_schema(request=None, responses={204: None})
@api_view(["POST"])
@authentication_classes([StrictCsrfSessionAuth])
@permission_classes([IsAuthenticated])
def logout_view(request):
    logout(request)
    return Response(status=204)


@extend_schema(responses={200: OpenApiTypes.OBJECT})
@api_view(["GET"])
@authentication_classes([StrictCsrfSessionAuth])
@permission_classes([AllowAny])
def me(request):
    """`{"user": {...}}`, or `{"user": null}` when anonymous (200 either way so the SPA can bootstrap)."""
    return Response({"user": user_payload(request.user) if request.user.is_authenticated else None})
