from django.urls import path

from . import views

urlpatterns = [
    path("health/", views.health, name="health"),
    path("health/live/", views.live, name="health-live"),
    path("health/ready/", views.ready, name="health-ready"),
    path("config/", views.config, name="config"),
    path("ops/metrics/", views.metrics, name="metrics"),
]
