"""SQLAlchemy model package.

Importing any model from ``app.models`` triggers registration of *all* model
classes against ``db.Model``'s metadata. This is required for SQLAlchemy
string-based relationships (e.g. ``db.relationship("PostTrip", ...)``) to
resolve regardless of which model is imported first.
"""
from app.models.user import User
from app.models.task import Task
from app.models.trip import PreTrip, PostTrip, ShiftRecord
from app.models.log import DriverLog
from app.models.messaging import ChatMessage, Announcement, DirectMessage
from app.models.knowledge import KnowledgeBaseEntry
from app.models.activity import ActivityEvent
from app.models.audit import AuditEvent
from app.models.damage import DamagePhoto, DamageReport
from app.models.followup import OperationalFollowUp
from app.models.plant_transfer import PlantTransfer, PlantTransferLine
from app.models.search import SearchCorpus

__all__ = [
    "User",
    "Task",
    "PreTrip",
    "PostTrip",
    "ShiftRecord",
    "DriverLog",
    "ChatMessage",
    "Announcement",
    "DirectMessage",
    "KnowledgeBaseEntry",
    "ActivityEvent",
    "AuditEvent",
    "DamagePhoto",
    "DamageReport",
    "OperationalFollowUp",
    "PlantTransfer",
    "PlantTransferLine",
    "SearchCorpus",
]
