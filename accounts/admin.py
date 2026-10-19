from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _

from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Email-keyed user admin. No username field to configure."""

    list_display = ("email", "full_name", "access_enabled", "is_staff", "date_joined")
    list_filter = ("is_staff", "is_superuser", "is_active", "access_enabled")
    search_fields = ("email", "full_name")
    ordering = ("-date_joined",)
    readonly_fields = ("last_login", "date_joined")

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (
            _("Personal details"),
            {
                "fields": (
                    "full_name", "profession", "education", "location", "marketing_opt_in",
                )
            },
        ),
        (
            _("Access"),
            {
                "fields": (
                    "access_enabled", "is_active", "is_staff",
                    "is_superuser", "groups", "user_permissions",
                )
            },
        ),
        (_("Dates"), {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("email", "full_name", "password1", "password2")}),
    )
