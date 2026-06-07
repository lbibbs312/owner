from django.contrib import admin

from .models import DriverRouteDay, RouteStop


@admin.register(DriverRouteDay)
class DriverRouteDayAdmin(admin.ModelAdmin):
    list_display = ("service_date", "driver", "route_number", "status", "started_at", "ended_at")
    list_filter = ("status", "service_date")
    search_fields = ("route_number", "driver__username", "driver__email")


@admin.register(RouteStop)
class RouteStopAdmin(admin.ModelAdmin):
    list_display = ("route_day", "sequence", "name", "stop_type", "status", "is_hot")
    list_filter = ("stop_type", "status", "is_hot", "requires_cargo")
    search_fields = ("name", "location", "route_day__route_number")
