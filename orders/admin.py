from django.contrib import admin

from .models import Order


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    """Orders are records of what the gateway reported; most fields are read-only.

    Marking an order refunded here does not call the gateway — issue the refund
    there first, then record it.
    """

    list_display = (
        "reference", "student", "course", "download", "amount", "method", "status", "created_at",
    )
    list_filter = ("status", "method", "course", "download")
    search_fields = ("reference", "gateway_reference", "student__email", "student__full_name")
    autocomplete_fields = ("student",)
    readonly_fields = ("reference", "callback_token", "created_at", "updated_at", "paid_at")
    fields = (
        "reference", "student", "course", "download", "amount", "method", "status",
        "gateway", "gateway_reference", "failure_reason",
        "paid_at", "created_at", "updated_at", "callback_token",
    )
