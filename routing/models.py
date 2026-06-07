from django.conf import settings
from django.db import models


class AuditEvent(models.Model):
    class Source(models.TextChoices):
        USER = "user", "User"
        SYSTEM = "system", "System"
        IMPORT = "import", "Import"

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="audit_events",
    )
    route_day = models.ForeignKey(
        "operations.DriverRouteDay",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="audit_events",
    )
    route_stop = models.ForeignKey(
        "operations.RouteStop",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="audit_events",
    )
    event_type = models.CharField(max_length=80)
    source = models.CharField(max_length=24, choices=Source.choices, default=Source.USER)
    summary = models.CharField(max_length=255, blank=True)
    details = models.JSONField(default=dict, blank=True)
    occurred_at = models.DateTimeField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-occurred_at", "-id"]
        indexes = [
            models.Index(fields=["event_type", "occurred_at"]),
            models.Index(fields=["route_day", "occurred_at"]),
            models.Index(fields=["actor", "occurred_at"]),
        ]

    def __str__(self) -> str:
        return self.summary or self.event_type
