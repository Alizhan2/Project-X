from django.urls import path

from . import views, watch_views

urlpatterns = [
    path("watches/", watch_views.collection),
    path("watches/<int:pk>/", watch_views.remove),
    path("notifications/", views.notifications),
    path("notifications/read-all/", views.mark_all_read),
    path("notifications/<int:pk>/read/", views.mark_read),
]
