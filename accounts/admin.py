"""Django admin configuration for the custom user model."""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    """Expose the custom account fields through Django's user administration."""

    fieldsets = UserAdmin.fieldsets + (
        ("Application", {"fields": ("is_admin", "created_at")}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("Application", {"fields": ("email", "is_admin")}),
    )
    readonly_fields = ("created_at",)
    list_display = UserAdmin.list_display + ("email", "is_admin", "created_at")
    search_fields = UserAdmin.search_fields + ("email",)
