from django.conf import settings
from django.db import models


class InspectionProof(models.Model):
    class ProofType(models.TextChoices):
        PRETRIP = "pretrip", "Pretrip"
        POSTTRIP = "posttrip", "Posttrip"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SUBMITTED = "submitted", "Submitted"
        ACCEPTED = "accepted", "Accepted"
        REJECTED = "rejected", "Rejected"

    route_day = models.ForeignKey(
        "operations.DriverRouteDay",
        on_delete=models.CASCADE,
        related_name="inspection_proofs",
    )
    driver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="inspection_proofs",
    )
    proof_type = models.CharField(max_length=16, choices=ProofType.choices)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.DRAFT)
    submitted_at = models.DateTimeField(blank=True, null=True)
    odometer = models.PositiveIntegerField(blank=True, null=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["route_day", "proof_type"]),
            models.Index(fields=["driver", "proof_type"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["route_day", "proof_type"],
                name="unique_route_inspection_proof_type",
            )
        ]

    def __str__(self) -> str:
        return f"{self.proof_type} proof for route {self.route_day_id}"


class DamageReport(models.Model):
    class Severity(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        REVIEWED = "reviewed", "Reviewed"
        CLOSED = "closed", "Closed"

    route_day = models.ForeignKey(
        "operations.DriverRouteDay",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="damage_reports",
    )
    route_stop = models.ForeignKey(
        "operations.RouteStop",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="damage_reports",
    )
    reported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="damage_reports",
    )
    title = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    severity = models.CharField(max_length=16, choices=Severity.choices, default=Severity.LOW)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.OPEN)
    observed_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "severity"]),
            models.Index(fields=["route_day", "status"]),
        ]

    def __str__(self) -> str:
        return self.title


class EvidenceAttachment(models.Model):
    inspection_proof = models.ForeignKey(
        InspectionProof,
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name="attachments",
    )
    damage_report = models.ForeignKey(
        DamageReport,
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name="attachments",
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="evidence_attachments",
    )
    file = models.FileField(upload_to="evidence/%Y/%m/%d/")
    caption = models.CharField(max_length=255, blank=True)
    content_type = models.CharField(max_length=120, blank=True)
    original_filename = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["uploaded_by", "created_at"]),
        ]

    def __str__(self) -> str:
        return self.caption or self.original_filename or f"attachment {self.pk}"
