from django.urls import path

from . import views

urlpatterns = [
    path("notifications/", views.notifications),
    path("notifications/read-all/", views.mark_all_read),
    path("notifications/<int:pk>/read/", views.mark_read),
]
