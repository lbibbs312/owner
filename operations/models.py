from django.conf import settings
from django.db import models


class DriverRouteDay(models.Model):
    class Status(models.TextChoices):
        PLANNED = "planned", "Planned"
        ACTIVE = "active", "Active"
        FINALIZED = "finalized", "Finalized"
        CANCELLED = "cancelled", "Cancelled"

    driver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="route_days",
    )
    service_date = models.DateField(db_index=True)
    route_number = models.CharField(max_length=64, blank=True)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.PLANNED)
    started_at = models.DateTimeField(blank=True, null=True)
    ended_at = models.DateTimeField(blank=True, null=True)
    odometer_start = models.PositiveIntegerField(blank=True, null=True)
    odometer_end = models.PositiveIntegerField(blank=True, null=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-service_date", "driver_id", "route_number"]
        indexes = [
            models.Index(fields=["driver", "service_date"]),
            models.Index(fields=["status", "service_date"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["driver", "service_date", "route_number"],
                name="unique_driver_route_day_number",
            )
        ]

    def __str__(self) -> str:
        label = self.route_number or "route"
        return f"{self.driver_id} {self.service_date} {label}"


class RouteStop(models.Model):
    class StopType(models.TextChoices):
        PICKUP = "pickup", "Pickup"
        DELIVERY = "delivery", "Delivery"
        SERVICE = "service", "Service"
        FUEL = "fuel", "Fuel"
        YARD = "yard", "Yard"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        PLANNED = "planned", "Planned"
        ARRIVED = "arrived", "Arrived"
        COMPLETED = "completed", "Completed"
        SKIPPED = "skipped", "Skipped"

    route_day = models.ForeignKey(
        DriverRouteDay,
        on_delete=models.CASCADE,
        related_name="stops",
    )
    sequence = models.PositiveSmallIntegerField()
    stop_type = models.CharField(max_length=24, choices=StopType.choices, default=StopType.OTHER)
    name = models.CharField(max_length=160)
    location = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.PLANNED)
    requires_cargo = models.BooleanField(default=True)
    is_hot = models.BooleanField(default=False)
    arrived_at = models.DateTimeField(blank=True, null=True)
    departed_at = models.DateTimeField(blank=True, null=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["route_day", "sequence"]
        indexes = [
            models.Index(fields=["route_day", "sequence"]),
            models.Index(fields=["status"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["route_day", "sequence"],
                name="unique_route_stop_sequence",
            )
        ]

    def __str__(self) -> str:
        return f"{self.route_day_id} stop {self.sequence}: {self.name}"
