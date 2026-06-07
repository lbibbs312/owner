from django.contrib import admin

from .models import DamageReport, EvidenceAttachment, InspectionProof


@admin.register(InspectionProof)
class InspectionProofAdmin(admin.ModelAdmin):
    list_display = ("route_day", "driver", "proof_type", "status", "submitted_at")
    list_filter = ("proof_type", "status")
    search_fields = ("driver__username", "driver__email", "route_day__route_number")


@admin.register(DamageReport)
class DamageReportAdmin(admin.ModelAdmin):
    list_display = ("title", "reported_by", "severity", "status", "created_at")
    list_filter = ("severity", "status")
    search_fields = ("title", "description", "reported_by__username", "reported_by__email")


@admin.register(EvidenceAttachment)
class EvidenceAttachmentAdmin(admin.ModelAdmin):
    list_display = ("original_filename", "uploaded_by", "inspection_proof", "damage_report", "created_at")
    list_filter = ("content_type", "created_at")
    search_fields = ("original_filename", "caption", "uploaded_by__username", "uploaded_by__email")
