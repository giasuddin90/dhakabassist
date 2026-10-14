from django.contrib import admin

from .models import ContactMessage, Faq, LegalPage


@admin.register(Faq)
class FaqAdmin(admin.ModelAdmin):
    list_display = ("question", "position", "is_published")
    list_editable = ("position", "is_published")
    search_fields = ("question", "answer")


@admin.register(LegalPage)
class LegalPageAdmin(admin.ModelAdmin):
    list_display = ("title", "slug", "is_published", "updated_at")
    list_filter = ("is_published",)


@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ("name", "email", "created_at", "is_handled")
    list_filter = ("is_handled",)
    search_fields = ("name", "email", "message")
    readonly_fields = ("name", "email", "message", "created_at")
