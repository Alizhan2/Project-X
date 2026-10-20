from django.urls import path

from apps.disruptions import views as recovery_views
from apps.payments.views import pay

from . import views, exports

urlpatterns = [
    path("bookings/", views.bookings),
    path("bookings/upcoming/", exports.upcoming),
    path("bookings/<str:reference>/calendar/", exports.calendar),
    path("bookings/<str:reference>/pdf/", exports.pdf),
    path("bookings/<str:reference>/", views.booking_detail),
    path("bookings/<str:reference>/abandon/", views.booking_abandon),
    path("bookings/<str:reference>/cancellation/", views.booking_cancellation_quote),
    path("bookings/<str:reference>/cancel/", views.booking_cancel),
    path("bookings/<str:reference>/pay/", pay),
    path("bookings/<str:reference>/replacements/", recovery_views.replacements),
    path("bookings/<str:reference>/replacements/<int:offer_id>/accept/", recovery_views.accept),
    path("bookings/<str:reference>/replacements/<int:offer_id>/decline/", recovery_views.decline),
]
