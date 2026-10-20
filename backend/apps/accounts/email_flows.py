"""Purpose-bound, expiring links. Tokens travel in URL fragments, never server access logs."""
import hashlib

from django.conf import settings
from django.contrib.auth import password_validation
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.core.cache import cache
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from apps.core.throttling import throttle
from apps.core.jobs import enqueue, handler
from .models import User
from .views import StrictCsrfSessionAuth


class VerifyToken(PasswordResetTokenGenerator):
    key_salt = 'doedu.email.verification'

    def _make_hash_value(self, user, timestamp):
        return super()._make_hash_value(user, timestamp) + str(user.email_verified_at)


TOKENS = {'reset': PasswordResetTokenGenerator(), 'verify': VerifyToken()}


def deliver(user, purpose):
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = TOKENS[purpose].make_token(user)
    page = 'reset-password' if purpose == 'reset' else 'verify-email'
    url = f'{settings.PUBLIC_APP_URL}/{page}#uid={uid}&token={token}'
    action = 'Reset your password' if purpose == 'reset' else 'Verify your email'
    try:
        send_mail(f'Doedu: {action}',
                  f'{action}:\n\n{url}\n\nThis link expires in one hour and works once. '
                  'If you did not request it, ignore this message.\n',
                  settings.DEFAULT_FROM_EMAIL, [user.email])
    except Exception:
        # The worker retries. Suppress SMTP details in logs and persisted job errors.
        raise RuntimeError("Account email delivery failed") from None


def credential_version(user):
    return hashlib.sha256(f'{user.password}:{user.email}:{user.email_verified_at}'.encode()).hexdigest()


def queue_email(user, purpose, identifier):
    key = 'mail:' + hashlib.sha256(f'{purpose}:{identifier}'.encode()).hexdigest()
    if cache.add(key, True, 60):
        try:
            enqueue('account_email', {'user_id': user.pk if user else None, 'purpose': purpose,
                                     'version': credential_version(user) if user else ''})
        except Exception:
            cache.delete(key)
            raise


@handler('account_email')
def deliver_queued(user_id, purpose, version):
    user = User.objects.filter(pk=user_id, is_active=True).first() if user_id else None
    if not user or credential_version(user) != version or not user.has_usable_password():
        return
    if purpose == 'verify' and user.email_verified_at:
        return
    deliver(user, purpose)


def require_delivery():
    if settings.IS_DEPLOYED and not settings.ACCOUNT_EMAIL_CONFIGURED:
        error = APIException('Account email is not configured on this deployment. Contact the operator.')
        error.status_code = 503
        raise error


class EmailIn(serializers.Serializer):
    email = serializers.EmailField()


class TokenIn(serializers.Serializer):
    uid = serializers.CharField(max_length=100)
    token = serializers.CharField(max_length=200)


class ResetIn(TokenIn):
    password = serializers.CharField(trim_whitespace=False, write_only=True)


@extend_schema(request=EmailIn, responses={202: OpenApiTypes.OBJECT})
@throttle('account_email', by_ip=True)
@api_view(['POST'])
@authentication_classes([StrictCsrfSessionAuth])
@permission_classes([AllowAny])
def reset_request(request):
    require_delivery()
    data = EmailIn(data=request.data)
    data.is_valid(raise_exception=True)
    user = User.objects.filter(username=data.validated_data['email'].lower(), is_active=True).first()
    queue_email(user, 'reset', data.validated_data['email'].lower())
    return Response({'detail': 'If an eligible account exists, a reset link will be sent. Check your inbox and spam folder.'}, status=202)


@extend_schema(request=None, responses={202: OpenApiTypes.OBJECT})
@throttle('account_email', by_ip=True)
@api_view(['POST'])
@authentication_classes([StrictCsrfSessionAuth])
@permission_classes([IsAuthenticated])
def verification_request(request):
    require_delivery()
    if not request.user.email_verified_at:
        queue_email(request.user, 'verify', request.user.email)
    return Response({'detail': 'If your email is not verified, a verification link will be sent. Check your inbox and spam folder.'}, status=202)


def consume(data, purpose):
    try:
        uid = urlsafe_base64_decode(data['uid']).decode()
        if not uid.isdecimal():
            raise ValueError()
        user = User.objects.select_for_update().get(pk=int(uid), is_active=True)
    except (ValueError, UnicodeDecodeError, OverflowError, User.DoesNotExist):
        raise ValidationError({'detail': 'This link is invalid or expired. Request a new link.'})
    if not TOKENS[purpose].check_token(user, data['token']):
        raise ValidationError({'detail': 'This link is invalid or expired. Request a new link.'})
    return user


@extend_schema(request=ResetIn, responses={200: OpenApiTypes.OBJECT})
@throttle('account_token', by_ip=True)
@api_view(['POST'])
@authentication_classes([StrictCsrfSessionAuth])
@permission_classes([AllowAny])
def reset_confirm(request):
    data = ResetIn(data=request.data)
    data.is_valid(raise_exception=True)
    with transaction.atomic():
        user = consume(data.validated_data, 'reset')
        try:
            password_validation.validate_password(data.validated_data['password'], user)
        except DjangoValidationError as e:
            raise ValidationError({'password': e.messages})
        user.set_password(data.validated_data['password'])
        user.email_verified_at = timezone.now()
        user.save(update_fields=['password', 'email_verified_at'])
        cache.delete(f'loginfail:{user.username}')
    return Response({'detail': 'Password updated. Sign in with your new password.'})


@extend_schema(request=TokenIn, responses={200: OpenApiTypes.OBJECT})
@throttle('account_token', by_ip=True)
@api_view(['POST'])
@authentication_classes([StrictCsrfSessionAuth])
@permission_classes([AllowAny])
def verification_confirm(request):
    data = TokenIn(data=request.data)
    data.is_valid(raise_exception=True)
    with transaction.atomic():
        user = consume(data.validated_data, 'verify')
        user.email_verified_at = timezone.now()
        user.save(update_fields=['email_verified_at'])
    return Response({'detail': 'Email verified. You can return to your journeys.'})
