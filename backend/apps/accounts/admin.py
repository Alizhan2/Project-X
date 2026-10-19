from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class DoeduUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (("Doedu", {"fields": ("role",)}),)
    list_display = ("username", "email", "role", "is_staff")
    list_filter = UserAdmin.list_filter + ("role",)
