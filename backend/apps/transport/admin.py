from django.contrib import admin

from . import models

for m in (
    models.Operator, models.OperatorMembership, models.Hub, models.Stop, models.CancellationPolicy,
    models.Fare,
):
    admin.site.register(m)


class RouteStopInline(admin.TabularInline):
    model = models.RouteStop
    extra = 0


@admin.register(models.Route)
class RouteAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "operator", "mode")
    inlines = [RouteStopInline]


@admin.register(models.Departure)
class DepartureAdmin(admin.ModelAdmin):
    list_display = ("route", "departs_at", "status", "delay_minutes", "capacity", "places_taken")
    list_filter = ("status", "route__operator")


@admin.register(models.TransferLink)
class TransferLinkAdmin(admin.ModelAdmin):
    list_display = ("from_stop", "to_stop", "minutes", "boarding_buffer_minutes", "step_free")
    list_filter = ("step_free",)
    list_select_related = ("from_stop", "to_stop")
