from django.contrib import admin

from .models import Download


@admin.register(Download)
class DownloadAdmin(admin.ModelAdmin):
    list_display = ("__str__", "kind", "access", "price", "status", "position")
    list_filter = ("status", "access", "kind")
    search_fields = ("title_bn", "title_en", "slug")
