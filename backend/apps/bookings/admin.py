from django.contrib import admin

from .models import Booking, BookingLeg, Reservation


class LegInline(admin.TabularInline):
    model = BookingLeg
    extra = 0
    can_delete = False


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ("reference", "user", "status", "passengers", "total_amount", "created_at")
    list_filter = ("status",)
    search_fields = ("reference", "user__email")
    inlines = [LegInline]


admin.site.register(Reservation)
