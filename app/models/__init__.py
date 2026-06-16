"""SQLAlchemy model package.

Importing any model from ``app.models`` triggers registration of *all* model
classes against ``db.Model``'s metadata. This is required for SQLAlchemy
string-based relationships (e.g. ``db.relationship("PostTrip", ...)``) to
resolve regardless of which model is imported first.
"""
from app.models.user import User
from app.models.task import Task
from app.models.trip import PreTrip, PostTrip, ShiftRecord, RouteBreak
from app.models.log import DriverLog, DriverLogPhoto
from app.models.messaging import ChatMessage, Announcement, DirectMessage
from app.models.knowledge import KnowledgeBaseEntry
from app.models.activity import ActivityEvent
from app.models.audit import AuditEvent
from app.models.case import CaseEvent, ExceptionEvent, FollowupCase
from app.models.damage import DamagePhoto, DamageReport
from app.models.autolog import (
    AutoLogSession,
    CandidateAction,
    CandidateStop,
    ConfirmedStop,
    DriverMemory,
    MotionSegment,
    PlaceMemory,
    RawLocationPoint,
    RouteReviewQueue,
    SyncOutbox,
)
from app.models.draft import DraftEntry
from app.models.driver_state import (
    DriverActivityEvent,
    DriverDayState,
    DriverPresence,
    DriverState,
)
from app.models.duty import DutyStatusEvent
from app.models.dispatch_capture import DispatchCapture
from app.models.followup import OperationalFollowUp
from app.models.flow import (
    ContainerItem,
    ContainerTreeSnapshot,
    ContainerType,
    EntityCurrentState,
    FlowContainer,
    FlowEvent,
    FlowManifest,
    FlowNodeSnapshot,
    ManifestLine,
)
from app.models.plant_transfer import PlantTransfer, PlantTransferLine
from app.models.move_request import MoveRequest
from app.models.search import SearchCorpus
from app.models.load_intent import LoadIntent, PlantPredictionRule, PlantTimeSample
from app.models.part import (
    ExternalDocument,
    HotMove,
    HotPartAlert,
    HotPartEvent,
    HotPartPhoto,
    MovePart,
    PartAlias,
    PartLocationHistory,
    PartMaster,
    PartRouteProfile,
    PartScanEvent,
)
from app.models.node import Node
from app.models.packet import (
    AccidentIncidentReport,
    AccidentWitness,
    IftaBulkFuelWithdrawal,
    IftaFuelRecord,
    IftaTripDistanceRow,
    IftaWorksheet,
    PacketManagerReview,
    ProofMediaFile,
)
from app.models.voyager import Voyager

__all__ = [
    "User",
    "Task",
    "PreTrip",
    "PostTrip",
    "ShiftRecord",
    "RouteBreak",
    "DriverLog",
    "DriverLogPhoto",
    "ChatMessage",
    "Announcement",
    "DirectMessage",
    "KnowledgeBaseEntry",
    "ActivityEvent",
    "AuditEvent",
    "ExceptionEvent",
    "FollowupCase",
    "CaseEvent",
    "DamagePhoto",
    "DamageReport",
    "DraftEntry",
    "DriverDayState",
    "DriverPresence",
    "DriverActivityEvent",
    "DriverState",
    "DispatchCapture",
    "OperationalFollowUp",
    "FlowEvent",
    "EntityCurrentState",
    "FlowNodeSnapshot",
    "ContainerType",
    "FlowContainer",
    "ContainerItem",
    "ContainerTreeSnapshot",
    "FlowManifest",
    "ManifestLine",
    "PlantTransfer",
    "PlantTransferLine",
    "MoveRequest",
    "SearchCorpus",
    "PartMaster",
    "PartAlias",
    "PartScanEvent",
    "MovePart",
    "PartLocationHistory",
    "HotPartAlert",
    "HotMove",
    "HotPartPhoto",
    "HotPartEvent",
    "PartRouteProfile",
    "ExternalDocument",
    "LoadIntent",
    "PlantPredictionRule",
    "PlantTimeSample",
    "Node",
    "AccidentIncidentReport",
    "AccidentWitness",
    "ProofMediaFile",
    "IftaWorksheet",
    "IftaTripDistanceRow",
    "IftaFuelRecord",
    "IftaBulkFuelWithdrawal",
    "PacketManagerReview",
    "Voyager",
]
