from django.contrib import admin

from .models import AuditEvent


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ("event_type", "source", "actor", "route_day", "route_stop", "occurred_at")
    list_filter = ("source", "event_type")
    search_fields = ("event_type", "summary", "actor__username", "actor__email")
    readonly_fields = ("created_at",)
