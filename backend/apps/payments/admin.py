from django.contrib import admin

from .models import PaymentAttempt, Refund


class ReadOnly(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register(PaymentAttempt, ReadOnly)
admin.site.register(Refund, ReadOnly)
