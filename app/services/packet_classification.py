"""Packet classification helpers for route, issue, and proof records."""
from dataclasses import dataclass
from enum import Enum
import re


class PacketClassification(str, Enum):
    PRETRIP_DVIR_ISSUE = "pretrip_dvir_issue"
    DAMAGE_ISSUE = "damage_issue"
    ACCIDENT_INCIDENT = "accident_incident"
    FUEL_ODO_IFTA = "fuel_odo_ifta"
    CARGO_PLANT_TRANSFER_ISSUE = "cargo_plant_transfer_issue"
    ROUTE_ISSUE = "route_issue"
    DOCUMENT_RECORD = "document_record"
    OTHER_ISSUE = "other_issue"


PACKET_TYPE_LABELS = {
    PacketClassification.PRETRIP_DVIR_ISSUE.value: "Pretrip / DVIR Issue Packet",
    PacketClassification.DAMAGE_ISSUE.value: "Damage Issue Packet",
    PacketClassification.ACCIDENT_INCIDENT.value: "Accident / Incident Packet",
    PacketClassification.FUEL_ODO_IFTA.value: "Fuel / Odometer / IFTA Worksheet",
    PacketClassification.CARGO_PLANT_TRANSFER_ISSUE.value: "Cargo / Plant Transfer Issue Packet",
    PacketClassification.ROUTE_ISSUE.value: "Route Issue Packet",
    PacketClassification.DOCUMENT_RECORD.value: "Document Record Packet",
    PacketClassification.OTHER_ISSUE.value: "Other Issue Packet",
}


@dataclass(frozen=True)
class PacketClassificationResult:
    packet_type: str
    label: str
    needs_clarification: bool = False
    question: str = ""


ACCIDENT_PATTERNS = (
    r"\bcrash(?:ed)?\b",
    r"\bhit\b",
    r"\bcollision\b",
    r"\bbacking incident\b",
    r"\binjur(?:y|ies|ed)\b",
    r"\btow[- ]?away\b",
    r"\bpolice\b",
    r"\bother vehicle\b",
    r"\bproperty damage\b",
    r"\binsurance claim\b",
    r"\bclaim\b",
)

FUEL_ODO_PATTERNS = (
    r"\blow fuel\b",
    r"\bfuel\b",
    r"\bodometer\b",
    r"\bodo\b",
    r"\breceipt\b",
    r"\bgallons?\b",
    r"\bfuel stop\b",
    r"\bmileage\b",
    r"\bjurisdiction distance\b",
    r"\bjurisdiction miles?\b",
)

DAMAGE_PATTERNS = (
    r"\bdent(?:ed)?\b",
    r"\bscratch(?:ed|es)?\b",
    r"\bscrape(?:d|s)?\b",
    r"\bbroken mirror\b",
    r"\bbroken light\b",
    r"\btrailer damage\b",
    r"\bcargo damage\b",
    r"\bphysical vehicle damage\b",
    r"\bvehicle damage\b",
    r"\bdamaged (?:mirror|light|trailer|truck|vehicle|door|bumper)\b",
    r"\bbent (?:door|bumper|trailer|mirror|light)\b",
    r"\bcracked (?:mirror|light|windshield|bumper)\b",
)

CARGO_PATTERNS = (
    r"\bplant transfer\b",
    r"\btransfer sheet\b",
    r"\bcargo\b",
    r"\bload(?:ed|ing)?\b",
    r"\bmanifest\b",
)

ROUTE_PATTERNS = (
    r"\broute\b",
    r"\bstop\b",
    r"\bdock\b",
    r"\bdeparture\b",
    r"\barrival\b",
)

DOCUMENT_PATTERNS = (
    r"\bdocument\b",
    r"\bpaperwork\b",
    r"\bbol\b",
    r"\bmanifest\b",
    r"\bpacket\b",
)

PRETRIP_PATTERNS = (
    r"\bpre[- ]?trip\b",
    r"\bpretrip\b",
    r"\bdvir\b",
    r"\binspection\b",
)


def _joined_text(*parts):
    return " ".join(str(part or "") for part in parts).lower()


def _has_match(text, patterns):
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


def _result(packet_type, *, needs_clarification=False):
    return PacketClassificationResult(
        packet_type=packet_type.value,
        label=PACKET_TYPE_LABELS[packet_type.value],
        needs_clarification=needs_clarification,
        question="What type of record should this be?" if needs_clarification else "",
    )


def classify_packet_text(*parts):
    text = _joined_text(*parts)
    if _has_match(text, ACCIDENT_PATTERNS):
        return _result(PacketClassification.ACCIDENT_INCIDENT)
    if _has_match(text, FUEL_ODO_PATTERNS):
        return _result(PacketClassification.FUEL_ODO_IFTA)
    if _has_match(text, DAMAGE_PATTERNS):
        return _result(PacketClassification.DAMAGE_ISSUE)
    if _has_match(text, PRETRIP_PATTERNS):
        return _result(PacketClassification.PRETRIP_DVIR_ISSUE)
    if _has_match(text, CARGO_PATTERNS):
        return _result(PacketClassification.CARGO_PLANT_TRANSFER_ISSUE)
    if _has_match(text, ROUTE_PATTERNS):
        return _result(PacketClassification.ROUTE_ISSUE)
    if _has_match(text, DOCUMENT_PATTERNS):
        return _result(PacketClassification.DOCUMENT_RECORD)
    return _result(PacketClassification.OTHER_ISSUE, needs_clarification=True)


def classify_damage_report(report):
    return classify_packet_text(
        getattr(report, "description", None),
        getattr(report, "move_reference", None),
        getattr(report, "plant_name", None),
        getattr(report, "truck_number", None),
        getattr(report, "trailer_number", None),
    )


def packet_label_for_report(report):
    return classify_damage_report(report).label
