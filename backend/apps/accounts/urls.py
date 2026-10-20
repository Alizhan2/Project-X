from django.urls import path

from . import views, email_flows

urlpatterns = [
    path("auth/password-reset/", email_flows.reset_request),
    path("auth/password-reset/confirm/", email_flows.reset_confirm),
    path("auth/email-verification/", email_flows.verification_request),
    path("auth/email-verification/confirm/", email_flows.verification_confirm),
    path("auth/csrf/", views.csrf),
    path("auth/register/", views.register),
    path("auth/login/", views.login_view),
    path("auth/logout/", views.logout_view),
    path("auth/me/", views.me),
]
