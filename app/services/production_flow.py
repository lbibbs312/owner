"""Production-flow view models derived from real MoveDefense records.

This service is the widescreen / manager / plant-floor counterpart to
``route_map.py``.  It summarizes production movement pressure from existing
MoveRequest, DriverLog, PlantTransfer, issue, timing, and proof records.  It
does not invent unavailable production asset snapshots.
"""
from datetime import date as date_cls, datetime, timedelta
import math
import re

from flask import has_request_context, url_for
import pytz
from sqlalchemy import or_
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.routing import BuildError

from app.extensions import db
from app.models import DamageReport, DriverLog, ExceptionEvent, FlowEvent, FlowManifest, ManifestLine, MoveRequest, PlantTransfer
from app.models.user import User
from app.services.cargo_state import cargo_state_for_log, cargo_state_for_request
from app.services.driver_wait import wait_minutes_for_log
from app.services.floor_operations import ACTIVE_STATUSES, next_action_for_request
from app.services.issue_severity import classify_issue
from app.services.plant_addresses import PLANT_LABELS, plant_label
from app.services.plant_time import plant_forecast_rows


SAFE_EMPTY = "No current data"
NOT_TRACKED = "Not tracked yet"
DOCUMENT_MISSING = "Document not attached"
CARRIER_SNAPSHOT_EMPTY = "Carrier unit snapshot not connected yet"
RACK_SNAPSHOT_EMPTY = "Rack/capacity data not connected yet"
DATA_SCOPE_EMPTY = "Using route and move request data only"
DATA_SCOPE_ROUTE_ONLY = "Using route proof data only"
DETROIT_TZ = pytz.timezone("America/Detroit")

OPEN_STATUSES = {"open", "acknowledged"}
ACTIVE_MOVE_STATUSES = {"assigned", "in_progress"}
WAITING_STATUSES = {"waiting"}
BLOCKED_STATUSES = {"blocked", "needs_review"}
COMPLETED_STATUSES = {"completed"}
FRIENDLY_SOURCE = {
    "MoveRequest": "Move request",
    "DriverLog": "Driver route log",
    "PlantTransfer": "Plant transfer",
    "DamageReport": "Damage report",
    "IssueEvent": "Issue event",
    "Document": "Document proof",
    "PlantFlowConfig": "Configured plant flow",
}

PRODUCTION_DISPLAY_LABELS = {
    "ppl": "Raleigh West",
    "plastic_logistics": "Raleigh West",
    "plastic logistics": "Raleigh West",
    "plastic_logistics_buffer": "Raleigh West",
    "plastic logistics buffer": "Raleigh West",
    "molding": "Raleigh West",
    "rw": "Raleigh West",
    "raleigh_west": "Raleigh West",
    "raleigh west": "Raleigh West",
    "kp": "Kraft Plater",
    "kraft_plant": "Kraft Plater",
    "kraft plant": "Kraft Plater",
    "kraft_plater": "Kraft Plater",
    "kraft plater": "Kraft Plater",
    "pw": "Paint West",
    "plastic_west": "Paint West",
    "plastic west": "Paint West",
    "paint_west": "Paint West",
    "paint west": "Paint West",
    "pc": "Paint Central",
    "paint_central": "Paint Central",
    "paint central": "Paint Central",
    "52l": "52nd Street DC",
    "52dc": "52nd Street DC",
    "52nd_street_l": "52nd Street DC",
    "52nd street l": "52nd Street DC",
    "52nd_street_dc": "52nd Street DC",
    "52nd street dc": "52nd Street DC",
    "trim_dc": "Trim DC",
    "trim dc": "Trim DC",
    "re": "Raleigh East",
    "raleigh_east": "Raleigh East",
    "raleigh east": "Raleigh East",
    "helios": "Helios",
    "lab": "Quality Hold",
    "quality": "Quality Hold",
    "quality_hold": "Quality Hold",
    "quality hold": "Quality Hold",
}

PRODUCTION_SHORT_CODES = {
    "Raleigh West": "RW",
    "Kraft Plater": "KP",
    "Paint West": "PW",
    "Paint Central": "PC",
    "52nd Street DC": "52L",
    "Trim DC": "Trim DC",
    "Raleigh East": "RE",
    "Helios": "Helios",
    "Quality Hold": "QA",
}

CONFIGURED_PLANT_NODES = (
    "Raleigh West",
    "Kraft Plater",
    "Paint West",
    "Paint Central",
    "52nd Street DC",
    "Trim DC",
    "Raleigh East",
    "Helios",
    "Quality Hold",
)

CONFIGURED_PLANT_FLOW = (
    ("Raleigh West", "Kraft Plater"),
    ("Kraft Plater", "Paint West"),
    ("Paint West", "52nd Street DC"),
    ("Paint Central", "52nd Street DC"),
    ("52nd Street DC", "Raleigh East"),
    ("Trim DC", "Raleigh West"),
    ("Helios", "Kraft Plater"),
)

PRODUCTION_NODE_PROFILES = {
    "ppl": {
        "aliases": {"ppl", "plastic_logistics", "plastic_logistics_buffer", "molding"},
        "sequence": "1",
        "role_label": "MOLDING",
        "console_title": "PLASTIC LOGISTICS BUFFER & MOLDING (PPL)",
        "description": "Raw plastic substrates and outbound molding buffer.",
        "primary_label": "Material queued",
        "secondary_label": "Molding press",
        "console_left_title": "RAW INJECTION MOLDING",
        "console_right_title": "COMPONENT STAGING WMS",
        "theme": "cyan",
        "size": "primary",
        "x": 19,
        "y": 48,
    },
    "kraft_plant": {
        "aliases": {"kp", "kraft_plant", "kraft_plater", "kraft", "plating"},
        "sequence": "2",
        "role_label": "PLATING",
        "console_title": "KRAFT PLATER / PLATING (KP)",
        "description": "Plating, racking, loading/unloading, staged skids, and overflow risk.",
        "primary_label": "Staged skids",
        "secondary_label": "Overflow risk",
        "console_left_title": "PLATING / RACKING",
        "console_right_title": "LOAD / OVERFLOW STATUS",
        "theme": "cyan",
        "size": "primary",
        "x": 38,
        "y": 23,
    },
    "plastic_west": {
        "aliases": {"pw", "plastic_west", "paint_west", "paint", "coating"},
        "sequence": "3",
        "role_label": "COATING / PAINT",
        "console_title": "PAINT / COATING OPERATIONS (PW)",
        "description": "Coating, masking, paint line, and painted WIP release.",
        "primary_label": "Painted WIP",
        "secondary_label": "Paint line",
        "console_left_title": "MASKING / COATING LINE",
        "console_right_title": "PAINTED WIP",
        "theme": "cyan",
        "size": "primary",
        "x": 64,
        "y": 24,
    },
    "paint_central": {
        "aliases": {"pc", "paint_central", "paint_center", "central_paint"},
        "sequence": "3B",
        "role_label": "PAINT / FINISH SUPPORT",
        "console_title": "PAINT CENTRAL FINISH BUFFER (PC)",
        "description": "Central paint staging, finish checks, and release buffer.",
        "primary_label": "Finish WIP",
        "secondary_label": "Release buffer",
        "console_left_title": "FINISH LINE READOUT",
        "console_right_title": "STAGING RELEASE",
        "theme": "cyan",
        "size": "secondary",
        "x": 58,
        "y": 47,
    },
    "raleigh_west": {
        "aliases": {"rw", "raleigh_west", "ppl", "plastic_logistics", "plastic_logistics_buffer", "molding", "front_end", "intake", "empty_pack_return"},
        "sequence": "1",
        "role_label": "FRONT END / INTAKE / EMPTY PACK RETURN",
        "console_title": "RALEIGH WEST INTAKE / EMPTY PACK RETURN (RW)",
        "description": "Intake, empty packs, raw substrates, and staging capacity.",
        "primary_label": "Intake / empty packs",
        "secondary_label": "Staging capacity",
        "console_left_title": "INTAKE / RAW SUBSTRATES",
        "console_right_title": "EMPTY PACK RETURN",
        "theme": "cyan",
        "size": "primary",
        "x": 16,
        "y": 40,
    },
    "52nd_street_l": {
        "aliases": {"52l", "52nd_street_l", "52nd_street", "52nd_street_logistics", "52nd_street_dc", "52dc"},
        "sequence": "4",
        "role_label": "ASSEMBLY / CARRIER ALLOCATION",
        "console_title": "52ND STREET ASSEMBLY / LOGISTICS (52L)",
        "description": "Assembly, carrier allocation, and trailer assignment.",
        "primary_label": "Carrier allocation",
        "secondary_label": "Trailer assignment",
        "console_left_title": "ASSEMBLY / CARRIER TABLE",
        "console_right_title": "TRAILER ASSIGNMENT",
        "theme": "cyan",
        "size": "primary",
        "x": 82,
        "y": 56,
    },
    "52nd_street_dc": {
        "aliases": {"52dc"},
        "sequence": "4",
        "role_label": "ASSEMBLY / CARRIER ALLOCATION",
        "console_title": "52ND STREET DC LOAD BUILD",
        "description": "Assembly, carrier allocation, and trailer assignment.",
        "primary_label": "Carrier allocation",
        "secondary_label": "Trailer assignment",
        "console_left_title": "ASSEMBLY / CARRIER TABLE",
        "console_right_title": "TRAILER ASSIGNMENT",
        "theme": "cyan",
        "size": "primary",
        "x": 82,
        "y": 56,
    },
    "raleigh_east": {
        "aliases": {"re", "raleigh_east", "oem_dock", "receiving"},
        "sequence": "5",
        "role_label": "OEM DOCK / JIT DELIVERY",
        "console_title": "RALEIGH EAST OEM DOCK (RE)",
        "description": "OEM dock delivery, JIT status, and unload state.",
        "primary_label": "JIT status",
        "secondary_label": "Unload state",
        "console_left_title": "OEM DOCK DELIVERY",
        "console_right_title": "JIT / UNLOAD STATE",
        "theme": "cyan",
        "size": "primary",
        "x": 82,
        "y": 82,
    },
    "helios": {
        "aliases": {"helios", "helios_sub_plater", "sub_plater"},
        "sequence": "",
        "role_label": "SUB-PLATER / SUPPORT",
        "console_title": "HELIOS SUPPORT CHAMBERS",
        "description": "Auxiliary plating support and standby staging.",
        "primary_label": "Staged",
        "secondary_label": "Support line",
        "console_left_title": "SUB-PRODUCTION STAGING",
        "console_right_title": "AUXILIARY RELEASE",
        "theme": "cyan",
        "size": "secondary",
        "x": 18,
        "y": 78,
    },
    "trim_dc": {
        "aliases": {"trim_dc", "trim"},
        "sequence": "",
        "role_label": "EXTRACTION / EMPTY PACK RETURN",
        "console_title": "TRIM PACKING DC",
        "description": "Empty packs created, staged, and returned to Raleigh West.",
        "primary_label": "Empty packs created",
        "secondary_label": "Return staging",
        "console_left_title": "EXTRACTION / PACK CREATION",
        "console_right_title": "RW RETURN STAGING",
        "theme": "cyan",
        "size": "secondary",
        "x": 44,
        "y": 64,
    },
    "lab": {
        "aliases": {"lab", "corporate_lab", "quality_hold_lab", "quality", "quality_hold", "qa_hold", "corp", "corporate"},
        "sequence": "",
        "role_label": "QA / CONTAINMENT",
        "console_title": "QUALITY HOLD / QA CONTAINMENT",
        "description": "Scrap, QA holds, damage review, and containment proof.",
        "primary_label": "Scrap / holds",
        "secondary_label": "Containment",
        "console_left_title": "SCRAP / QA HOLD LOG",
        "console_right_title": "CONTAINMENT STATUS",
        "theme": "red",
        "size": "secondary",
        "x": 56,
        "y": 84,
    },
}

PRODUCTION_NODE_ALIAS_INDEX = {}
for _profile_key, _profile in PRODUCTION_NODE_PROFILES.items():
    PRODUCTION_NODE_ALIAS_INDEX[_profile_key] = _profile_key
    for _alias in _profile["aliases"]:
        PRODUCTION_NODE_ALIAS_INDEX[_alias] = _profile_key


def _clean(value):
    return str(value or "").strip()


def _target_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date_cls):
        return value
    if isinstance(value, str):
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError:
            return date_cls.today()
    return date_cls.today()


def _day_bounds(target):
    local_start = DETROIT_TZ.localize(datetime.combine(target, datetime.min.time()))
    utc_start = local_start.astimezone(pytz.utc).replace(tzinfo=None)
    return utc_start, utc_start + timedelta(days=1)


def _record_matches_date(record, target, attrs):
    for attr in attrs:
        value = getattr(record, attr, None)
        if not value:
            continue
        value_date = value.date() if isinstance(value, datetime) else value
        if value_date == target:
            return True
    return False


def _safe_url(endpoint, **values):
    if not has_request_context():
        return None
    try:
        return url_for(endpoint, **values)
    except (BuildError, RuntimeError):
        return None


def _location_label(value):
    text = _clean(value)
    if not text:
        return None
    text_key = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    configured = PRODUCTION_DISPLAY_LABELS.get(text.lower()) or PRODUCTION_DISPLAY_LABELS.get(text_key)
    if configured:
        return configured
    label = plant_label(text) or text
    label_key = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
    return PRODUCTION_DISPLAY_LABELS.get(label.lower()) or PRODUCTION_DISPLAY_LABELS.get(label_key) or label


def _location_key(value):
    text = _location_label(value) or "unspecified"
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_") or "unspecified"


def _short_code(value):
    text = _clean(value)
    if not text:
        return ""
    configured_label = _location_label(text)
    if configured_label in PRODUCTION_SHORT_CODES:
        return PRODUCTION_SHORT_CODES[configured_label]
    if text in PLANT_LABELS:
        return text
    for code, label in PLANT_LABELS.items():
        if label.lower() == text.lower():
            return code
    words = re.findall(r"[A-Za-z0-9]+", text)
    if not words:
        return text[:4].upper()
    if len(words) == 1:
        return words[0][:4].upper()
    return "".join(word[0] for word in words[:4]).upper()


def _profile_key_for_node(node):
    candidates = []

    def add_candidates(value):
        raw = _clean(value)
        if not raw:
            return
        for candidate in (_location_label(raw), raw):
            if not candidate:
                continue
            normalized = re.sub(r"[^a-z0-9]+", "_", candidate.lower()).strip("_")
            lowered = candidate.lower()
            for key in (normalized, lowered):
                if key and key not in candidates:
                    candidates.append(key)

    add_candidates(node.get("label"))
    add_candidates(node.get("short_code"))
    for code, label in PLANT_LABELS.items():
        if label == node.get("label"):
            add_candidates(code)
    for candidate in candidates:
        if candidate in PRODUCTION_NODE_ALIAS_INDEX:
            return PRODUCTION_NODE_ALIAS_INDEX[candidate]
    return None


def _production_profile_for_node(node):
    profile_key = _profile_key_for_node(node)
    if profile_key:
        base = dict(PRODUCTION_NODE_PROFILES[profile_key])
        base["profile_key"] = profile_key
        return base
    return {
        "profile_key": "generic",
        "sequence": "",
        "role_label": node.get("short_code") or "PLANT NODE",
        "console_title": f"{node.get('label') or SAFE_EMPTY} PRODUCTION POSITION",
        "description": "Configurable production, staging, receiving, or transport location.",
        "primary_label": "Material signals",
        "secondary_label": "Position state",
        "console_left_title": "CURRENT POSITION READOUT",
        "console_right_title": "FLOW PROOF",
        "theme": "cyan",
        "size": "primary",
        "x": None,
        "y": None,
    }


def _status_state_label(node):
    if node.get("blocked_count") or node.get("issue_count"):
        return "Blocked"
    if node.get("waiting_count"):
        return "Waiting"
    if node.get("active_count") or node.get("open_count"):
        return "Active"
    if node.get("completed_count"):
        return "Complete"
    return "Standby"


def _work_signal_count(node):
    return (
        node.get("open_count", 0)
        + node.get("active_count", 0)
        + node.get("waiting_count", 0)
        + node.get("completed_count", 0)
    )


def _singular_plural(count, singular, plural=None):
    return f"{count} {singular if count == 1 else (plural or singular + 's')}"


def _item_node_keys(item):
    keys = set()
    for field in ("related_node_key",):
        value = _clean(item.get(field))
        if value:
            keys.add(value)
    for field in ("origin_label", "destination_label", "plant_location"):
        value = _clean(item.get(field))
        if not value:
            continue
        for part in value.split("->"):
            key = _location_key(part)
            if key and key != "unspecified":
                keys.add(key)
    return keys


def _material_line_for_item(item):
    part = _clean(item.get("part_number"))
    quantity = _clean(item.get("quantity_text"))
    trailer = _clean(item.get("trailer"))
    candidates = [
        f"Part {part}" if part else "",
        _clean(item.get("cargo_text")),
        _clean(item.get("departed_with")),
        _clean(item.get("arrived_with")),
        _clean(item.get("description")),
    ]
    ignored = {
        "empty",
        "none",
        "no current data",
        "not tracked yet",
        "document not attached",
        "waiting",
        "completed",
        "proof",
        "no action needed",
        "record departure",
        "review issue",
    }
    label = next((candidate for candidate in candidates if candidate and candidate.lower() not in ignored), "")
    if not label:
        return ""
    suffixes = []
    if quantity:
        suffixes.append(quantity)
    if trailer:
        suffixes.append(f"Trailer {trailer}")
    if suffixes:
        return f"{label} ({', '.join(suffixes)})"
    return label


def _material_lines_for_node(node, items, limit=3):
    node_key = node.get("key")
    lines = []
    seen = set()
    for item in items:
        if node_key not in _item_node_keys(item):
            continue
        line = _material_line_for_item(item)
        if not line or line in seen:
            continue
        seen.add(line)
        lines.append(line)
        if len(lines) >= limit:
            break
    return lines


def _primary_value_for_node(node, material_lines, profile):
    count = _work_signal_count(node)
    if count:
        return _singular_plural(count, "flow signal")
    primary_label = (profile.get("primary_label") if profile else "material").lower()
    if primary_label:
        return f"No {primary_label} record"
    return "No material record"


def _console_lines_for_node(node, material_lines, profile):
    source = ", ".join(node.get("source_labels") or node.get("meta", {}).get("source_labels") or []) or SAFE_EMPTY
    work_count = _work_signal_count(node)
    material = material_lines[0] if material_lines else "No material record on this date"
    if len(material_lines) > 1:
        material = f"{material} +{len(material_lines) - 1}"
    primary_label = profile.get("primary_label") or "Material"
    secondary_label = profile.get("secondary_label") or "State"
    return {
        "left": [
            {"label": primary_label, "value": material},
            {"label": "Station records", "value": str(work_count)},
            {"label": secondary_label, "value": _status_state_label(node)},
        ],
        "right": [
            {"label": "Evidence source", "value": source},
            {"label": "Hot parts", "value": str(node.get("hot_count", 0))},
            {"label": "Proof needed", "value": str(node.get("proof_needed_count", 0))},
            {"label": "Issues", "value": str(node.get("issue_count", 0))},
        ],
    }


def _apply_production_profiles(nodes, items):
    for node in nodes:
        profile = _production_profile_for_node(node)
        material_lines = _material_lines_for_node(node, items)
        console_lines = _console_lines_for_node(node, material_lines, profile)
        state_label = _status_state_label(node)
        profile.update({
            "state_label": state_label,
            "primary_value": _primary_value_for_node(node, material_lines, profile),
            "secondary_value": state_label,
            "material_lines": material_lines,
            "console_left": console_lines["left"],
            "console_right": console_lines["right"],
            "signal_count": _work_signal_count(node),
            "attention_count": node.get("blocked_count", 0) + node.get("issue_count", 0) + node.get("hot_count", 0),
        })
        node["production_profile"] = profile


def _status_label(status):
    text = _clean(status).replace("_", " ")
    return text.title() if text else SAFE_EMPTY


def _date_label(value):
    if not value:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%b %d %I:%M%p").replace(" 0", " ").lower()
    return _clean(value)


def _age_minutes(value, *, now=None):
    if not isinstance(value, datetime):
        return None
    now = now or datetime.utcnow()
    minutes = int((now - value).total_seconds() // 60)
    return max(0, minutes)


def _quantity_text(req):
    return _clean(getattr(req, "quantity_display", "")) or _clean(getattr(req, "quantity_text", ""))


def _status_bucket(status):
    status = (status or "open").lower()
    if status in BLOCKED_STATUSES:
        return "blocked"
    if status in WAITING_STATUSES:
        return "waiting"
    if status in ACTIVE_MOVE_STATUSES:
        return "active"
    if status in COMPLETED_STATUSES:
        return "completed"
    return "open"


def _worst_status(*, blocked_count=0, waiting_count=0, active_count=0, open_count=0, completed_count=0):
    if blocked_count:
        return "blocked"
    if waiting_count:
        return "waiting"
    if active_count:
        return "active"
    if open_count:
        return "open"
    if completed_count:
        return "completed"
    return "none"


def _node_next_action(node):
    if node["blocked_count"] or node["issue_count"]:
        return "Review issue"
    if node["waiting_count"]:
        return "Check waiting moves"
    if node["active_count"]:
        return "Track active moves"
    if node["open_count"]:
        return "Assign or acknowledge move"
    return "No action needed"


def _lane_type(status):
    if status == "blocked":
        return "blocked_flow"
    if status == "waiting":
        return "active_move"
    if status == "active":
        return "active_move"
    if status == "completed":
        return "completed_move"
    return "requested_move"


def _is_hold_signal(*values):
    text = " ".join(_clean(value) or "" for value in values).lower()
    return any(token in text for token in ("quality hold", "qa hold", "containment", "on hold", "held", "hold area"))


def _replay_status(*, hot_count=0, hold_count=0, blocked_count=0, waiting_count=0, active_count=0, open_count=0, completed_count=0):
    if hot_count:
        return "hot"
    if hold_count:
        return "held"
    if blocked_count or waiting_count:
        return "held-up"
    if completed_count and not (active_count or open_count):
        return "completed"
    return "normal"


def _node_weight(node, degree_by_key):
    pressure = (
        node["blocked_count"] * 8
        + node["waiting_count"] * 5
        + node["active_count"] * 4
        + node["open_count"] * 3
        + node["issue_count"] * 6
        + node["completed_count"]
    )
    return pressure + degree_by_key.get(node["key"], 0) * 3


def _ring_point(center_x, center_y, radius_x, radius_y, angle_degrees):
    radians = math.radians(angle_degrees)
    return {
        "x": round(center_x + math.cos(radians) * radius_x, 2),
        "y": round(center_y + math.sin(radians) * radius_y, 2),
    }


def _clamp_layout(value, minimum=6, maximum=94):
    return max(minimum, min(maximum, value))


def _lane_pair_key(lane):
    return tuple(sorted((lane["origin_key"], lane["destination_key"])))


def _lane_curve(origin, destination, lane, lane_index_by_pair):
    x1, y1 = origin["x"], origin["y"]
    x2, y2 = destination["x"], destination["y"]
    pair_key = _lane_pair_key(lane)
    pair_index = lane_index_by_pair[pair_key]
    lane_index_by_pair[pair_key] += 1

    if lane["origin_key"] == lane["destination_key"]:
        loop_x = _clamp_layout(x1 + 12)
        loop_y = _clamp_layout(y1 - 18)
        end_y = _clamp_layout(y1 + 9)
        return {
            "x1": x1,
            "y1": y1,
            "x2": x1,
            "y2": end_y,
            "cx": loop_x,
            "cy": loop_y,
            "label_x": _clamp_layout(loop_x + 2),
            "label_y": _clamp_layout(loop_y + 5),
            "path_d": f"M {x1:.2f} {y1:.2f} C {loop_x:.2f} {loop_y:.2f} {loop_x:.2f} {end_y:.2f} {x1:.2f} {end_y:.2f}",
            "slot": pair_index,
        }

    dx = x2 - x1
    dy = y2 - y1
    length = math.hypot(dx, dy) or 1
    nx = -dy / length
    ny = dx / length
    direction = 1 if lane["origin_key"] < lane["destination_key"] else -1
    spread = 8 + (pair_index * 5)
    offset = spread * direction
    mid_x = (x1 + x2) / 2
    mid_y = (y1 + y2) / 2
    cx = _clamp_layout(mid_x + nx * offset)
    cy = _clamp_layout(mid_y + ny * offset)
    label_x = _clamp_layout(mid_x + nx * offset * 0.72)
    label_y = _clamp_layout(mid_y + ny * offset * 0.72)
    return {
        "x1": x1,
        "y1": y1,
        "x2": x2,
        "y2": y2,
        "cx": round(cx, 2),
        "cy": round(cy, 2),
        "label_x": round(label_x, 2),
        "label_y": round(label_y, 2),
        "path_d": f"M {x1:.2f} {y1:.2f} Q {cx:.2f} {cy:.2f} {x2:.2f} {y2:.2f}",
        "slot": pair_index,
    }


def _route_proof_curve(origin, destination, index):
    x1, y1 = origin["x"], origin["y"]
    x2, y2 = destination["x"], destination["y"]
    dx = x2 - x1
    dy = y2 - y1
    length = math.hypot(dx, dy) or 1
    nx = -dy / length
    ny = dx / length
    offset = 4 + (index % 2) * 3
    cx = _clamp_layout((x1 + x2) / 2 + nx * offset, 8, 92)
    cy = _clamp_layout((y1 + y2) / 2 + ny * offset, 8, 92)
    return f"M {x1:.2f} {y1:.2f} Q {cx:.2f} {cy:.2f} {x2:.2f} {y2:.2f}"


def _apply_map_layout(nodes, lanes, items, *, selected_node_key=None):
    """Attach deterministic spatial graph coordinates for the production map."""
    if not nodes:
        return

    degree_by_key = {node["key"]: 0 for node in nodes}
    connected_to = {node["key"]: set() for node in nodes}
    for lane in lanes:
        origin_key = lane["origin_key"]
        destination_key = lane["destination_key"]
        lane_weight = max(1, lane["open_count"] + lane["active_count"] + lane["waiting_count"] + lane["blocked_count"] + lane["completed_count"])
        if origin_key in degree_by_key:
            degree_by_key[origin_key] += lane_weight
            connected_to[origin_key].add(destination_key)
        if destination_key in degree_by_key:
            degree_by_key[destination_key] += lane_weight
            connected_to[destination_key].add(origin_key)

    node_by_key = {node["key"]: node for node in nodes}
    selected_hub = node_by_key.get(selected_node_key)
    hub = selected_hub or max(nodes, key=lambda node: (_node_weight(node, degree_by_key), node["label"]))
    hub_key = hub["key"]
    hub["layout"] = {"x": 50.0, "y": 50.0, "cx": 50.0, "cy": 50.0, "ring": "hub", "slot": 0, "is_hub": True}

    remaining = [node for node in nodes if node["key"] != hub_key]
    remaining.sort(
        key=lambda node: (
            node["key"] not in connected_to.get(hub_key, set()),
            -degree_by_key.get(node["key"], 0),
            -_node_weight(node, degree_by_key),
            node["label"],
        )
    )

    node_count = len(nodes)
    if node_count == 2 and remaining:
        remaining[0]["layout"] = {"x": 67.0, "y": 34.0, "cx": 67.0, "cy": 34.0, "ring": "inner", "slot": 1, "is_hub": False}
    elif node_count == 3:
        for index, node in enumerate(remaining):
            point = _ring_point(50, 50, 30, 25, -35 + index * 140)
            node["layout"] = {**point, "cx": point["x"], "cy": point["y"], "ring": "inner", "slot": index + 1, "is_hub": False}
    else:
        inner_count = min(len(remaining), 6)
        outer_count = max(0, len(remaining) - inner_count)
        for index, node in enumerate(remaining):
            if index < inner_count:
                angle_step = 360 / max(inner_count, 1)
                angle = -90 + (index * angle_step)
                point = _ring_point(50, 50, 31, 25, angle)
                ring = "inner"
            else:
                outer_index = index - inner_count
                angle_step = 360 / max(outer_count, 1)
                angle = -72 + (outer_index * angle_step)
                point = _ring_point(50, 50, 42, 35, angle)
                ring = "outer"
            point["x"] = _clamp_layout(point["x"], 12, 88)
            point["y"] = _clamp_layout(point["y"], 10, 90)
            node["layout"] = {**point, "cx": point["x"], "cy": point["y"], "ring": ring, "slot": index + 1, "is_hub": False}

    production_slot_counts = {}
    for node in nodes:
        profile = _production_profile_for_node(node)
        if profile.get("x") is None or profile.get("y") is None:
            continue
        count = production_slot_counts.get(profile["profile_key"], 0)
        production_slot_counts[profile["profile_key"]] = count + 1
        offset_x = (count % 2) * 5
        offset_y = (count // 2) * 6
        x = _clamp_layout(profile["x"] + offset_x, 12, 88)
        y = _clamp_layout(profile["y"] + offset_y, 10, 90)
        node["layout"] = {
            "x": round(x, 2),
            "y": round(y, 2),
            "cx": round(x, 2),
            "cy": round(y, 2),
            "ring": "production",
            "slot": count,
            "is_hub": node["key"] == selected_node_key,
        }

    slot_by_key = {node["key"]: node["layout"] for node in nodes}
    lane_index_by_pair = {}
    for lane in lanes:
        lane_index_by_pair.setdefault(_lane_pair_key(lane), 0)
    for lane in lanes:
        origin = slot_by_key.get(lane["origin_key"])
        destination = slot_by_key.get(lane["destination_key"])
        if not origin or not destination:
            lane["layout"] = {
                "x1": 14,
                "y1": 18,
                "x2": 86,
                "y2": 82,
                "cx": 50,
                "cy": 50,
                "label_x": 50,
                "label_y": 50,
                "path_d": "M 14 18 Q 50 50 86 82",
                "slot": 0,
            }
            continue
        lane["layout"] = _lane_curve(origin, destination, lane, lane_index_by_pair)

    lane_by_pair = {(lane["origin_label"], lane["destination_label"]): lane for lane in lanes}
    item_offsets = ((-9, -9), (10, 8), (-12, 9), (12, -8), (0, 14), (0, -14))
    route_chip_offsets = ((18, 16), (-18, 16), (18, 24), (-18, 24), (0, 27), (0, -24))
    node_item_counts = {}
    for index, item in enumerate(items):
        lane = lane_by_pair.get((item.get("origin_label"), item.get("destination_label")))
        if item.get("item_type") == "route_stop":
            node_key = item.get("related_node_key") or _location_key(item.get("plant_location"))
            node_layout = slot_by_key.get(node_key) or hub["layout"]
            count = node_item_counts.get(f"route:{node_key}", 0)
            node_item_counts[f"route:{node_key}"] = count + 1
            offset = route_chip_offsets[count % len(route_chip_offsets)]
            base_x = node_layout["x"]
            base_y = node_layout["y"]
        elif lane and lane.get("layout"):
            offset = item_offsets[index % len(item_offsets)]
            base_x = lane["layout"].get("label_x", 50)
            base_y = lane["layout"].get("label_y", 50)
        else:
            offset = item_offsets[index % len(item_offsets)]
            node_key = _location_key(item.get("plant_location"))
            node_layout = slot_by_key.get(node_key) or hub["layout"]
            node_item_counts[node_key] = node_item_counts.get(node_key, 0) + 1
            count = node_item_counts[node_key]
            base_x = node_layout["x"] + (count % 3 - 1) * 7
            base_y = node_layout["y"] + 13 + (count // 3) * 5
        item["layout"] = {
            "x": round(_clamp_layout(base_x + offset[0], 12, 86), 2),
            "y": round(_clamp_layout(base_y + offset[1], 8, 88), 2),
            "slot": index,
        }


def _node(nodes, label, *, node_type="plant"):
    label = _location_label(label)
    if not label:
        return None
    key = _location_key(label)
    if key not in nodes:
        nodes[key] = {
            "key": key,
            "label": label,
            "short_code": _short_code(label),
            "node_type": node_type,
            "open_count": 0,
            "active_count": 0,
            "waiting_count": 0,
            "blocked_count": 0,
            "completed_count": 0,
            "issue_count": 0,
            "hot_count": 0,
            "hold_count": 0,
            "worst_status": "none",
            "next_action": "No action needed",
            "meta": {
                "timing": None,
                "data_sources": [],
                "source_labels": [],
                "carrier_unit_snapshot": None,
                "rack_capacity_snapshot": None,
                "production_snapshot_available": False,
                "snapshot_empty_state": CARRIER_SNAPSHOT_EMPTY,
                "rack_empty_state": RACK_SNAPSHOT_EMPTY,
            },
            "view_url": _safe_url("manager.move_requests", location=label),
            "active_moves_url": _safe_url("manager.move_requests", location=label),
            "timing_url": _safe_url("manager.driver_logs"),
        }
    return nodes[key]


def _lane(lanes, origin, destination, *, configured=False):
    origin = _location_label(origin)
    destination = _location_label(destination)
    if not origin or not destination:
        return None
    origin_key = _location_key(origin)
    destination_key = _location_key(destination)
    key = (origin_key, destination_key)
    if key not in lanes:
        lanes[key] = {
            "origin_key": origin_key,
            "destination_key": destination_key,
            "origin_label": origin,
            "destination_label": destination,
            "lane_type": "requested_move",
            "is_configured_flow": bool(configured),
            "default_visible": bool(configured),
            "open_count": 0,
            "active_count": 0,
            "completed_count": 0,
            "blocked_count": 0,
            "waiting_count": 0,
            "hot_count": 0,
            "hold_count": 0,
            "worst_status": "none",
            "oldest_age_minutes": None,
            "linked_request_ids": [],
            "linked_driver_log_ids": [],
            "linked_transfer_ids": [],
            "view_url": _safe_url("manager.move_requests", origin=origin, destination=destination),
        }
    elif configured:
        lanes[key]["is_configured_flow"] = True
        lanes[key]["default_visible"] = True
    return lanes[key]


def _seed_configured_plant_flow(nodes, lanes):
    for label in CONFIGURED_PLANT_NODES:
        node = _node(nodes, label)
        if node:
            _add_source(node["meta"], "PlantFlowConfig")
    for index, (origin, destination) in enumerate(CONFIGURED_PLANT_FLOW):
        lane = _lane(lanes, origin, destination, configured=True)
        if lane:
            lane["lane_type"] = "plant_flow"
            lane["flow_sequence"] = index


def _bump_status(target, status, *, has_issue=False):
    bucket = _status_bucket(status)
    if bucket == "blocked":
        target["blocked_count"] += 1
    elif bucket == "waiting":
        target["waiting_count"] += 1
    elif bucket == "active":
        target["active_count"] += 1
    elif bucket == "completed":
        target["completed_count"] += 1
    else:
        target["open_count"] += 1
    if has_issue:
        target["issue_count"] = target.get("issue_count", 0) + 1


def _add_source(meta, source):
    sources = meta.setdefault("data_sources", [])
    if source not in sources:
        sources.append(source)
    friendly = meta.setdefault("source_labels", [])
    nice = FRIENDLY_SOURCE.get(source, source)
    if nice not in friendly:
        friendly.append(nice)


def _move_requests(target, *, driver_id=None, selected_move_request_id=None):
    start, end = _day_bounds(target)
    active_query = MoveRequest.query.filter(MoveRequest.status.in_(ACTIVE_STATUSES))
    completed_query = MoveRequest.query.filter(
        MoveRequest.status == "completed",
        or_(
            MoveRequest.updated_at.between(start, end),
            MoveRequest.created_at.between(start, end),
        ),
    )
    if driver_id:
        driver_scope = or_(
            MoveRequest.assigned_driver_id == driver_id,
            MoveRequest.linked_driver_log.has(DriverLog.driver_id == driver_id),
        )
        active_query = active_query.filter(driver_scope)
        completed_query = completed_query.filter(driver_scope)
    active = [
        req for req in active_query.all()
        if _record_matches_date(req, target, ("due_at", "requested_at", "created_at", "updated_at"))
        or (getattr(req, "linked_driver_log", None) is not None and req.linked_driver_log.date == target)
    ]
    completed = completed_query.all()
    by_id = {req.id: req for req in active + completed}
    if selected_move_request_id and selected_move_request_id not in by_id:
        selected = MoveRequest.query.get(selected_move_request_id)
        if selected:
            by_id[selected.id] = selected
    rows = list(by_id.values())
    rows.sort(
        key=lambda req: (
            getattr(req, "due_at", None) is None,
            getattr(req, "due_at", None) or datetime.max,
            getattr(req, "requested_at", None) or datetime.min,
            getattr(req, "id", 0),
        )
    )
    return rows


def _driver_logs(target, *, driver_id=None, selected_stop_id=None):
    query = DriverLog.query.filter(DriverLog.deleted_at.is_(None), DriverLog.date == target)
    if driver_id:
        query = query.filter_by(driver_id=driver_id)
    logs = query.order_by(DriverLog.driver_id.asc(), DriverLog.created_at.asc(), DriverLog.id.asc()).all()
    if selected_stop_id and selected_stop_id not in {log.id for log in logs}:
        selected = DriverLog.query.get(selected_stop_id)
        if selected and not selected.deleted_at:
            logs.append(selected)
    return logs


def _plant_transfers(target, *, driver_id=None):
    query = PlantTransfer.query.filter(
        PlantTransfer.deleted_at.is_(None),
        PlantTransfer.transfer_date == target,
    )
    if driver_id:
        query = query.filter_by(user_id=driver_id)
    return query.order_by(PlantTransfer.created_at.desc(), PlantTransfer.id.desc()).all()


def _damage_reports(target, *, driver_id=None):
    start, end = _day_bounds(target)
    query = DamageReport.query.filter(
        DamageReport.status != "closed",
        or_(
            DamageReport.damage_time.between(start, end),
            DamageReport.created_at.between(start, end),
        ),
    )
    if driver_id:
        query = query.filter_by(reported_by_id=driver_id)
    return query.order_by(DamageReport.created_at.desc(), DamageReport.id.desc()).all()


RESOLVED_EXCEPTION_EVENT_TYPES = {
    "manager_review_resolved",
    "exception_resolved",
    "issue_resolved",
    "resolved",
}


def _issue_events(target, *, driver_id=None):
    start, end = _day_bounds(target)
    query = ExceptionEvent.query.filter(
        or_(
            ExceptionEvent.event_date == target,
            ExceptionEvent.created_at.between(start, end),
        )
    )
    if driver_id:
        query = query.filter_by(driver_id=driver_id)
    events = query.order_by(ExceptionEvent.created_at.desc(), ExceptionEvent.id.desc()).all()
    resolved_at_by_stop = {}
    for event in events:
        event_type = (event.event_type or "").lower()
        if event_type not in RESOLVED_EXCEPTION_EVENT_TYPES:
            continue
        for stop_id in (event.stop_id, event.driver_log_id):
            if not stop_id:
                continue
            previous = resolved_at_by_stop.get(stop_id)
            if previous is None or event.created_at > previous:
                resolved_at_by_stop[stop_id] = event.created_at

    active = []
    for event in events:
        event_type = (event.event_type or "").lower()
        if event_type in RESOLVED_EXCEPTION_EVENT_TYPES:
            continue
        stop_ids = [stop_id for stop_id in (event.stop_id, event.driver_log_id) if stop_id]
        if any(resolved_at_by_stop.get(stop_id) and resolved_at_by_stop[stop_id] >= event.created_at for stop_id in stop_ids):
            continue
        active.append(event)
    return active


def _scoped_flow_event_query(target, *, driver_id=None, scoped_log_ids=frozenset()):
    start, end = _day_bounds(target)
    query = FlowEvent.query.filter(FlowEvent.occurred_at >= start, FlowEvent.occurred_at < end)
    if driver_id:
        log_ids = [log_id for log_id in scoped_log_ids if log_id]
        entity_ids = [str(log_id) for log_id in log_ids]
        scope_filters = [FlowEvent.actor_user_id == driver_id]
        if log_ids:
            scope_filters.append(FlowEvent.stop_id.in_(log_ids))
        if entity_ids:
            scope_filters.append(
                FlowEvent.entity_type.in_(("route_stop", "driver_log")) & FlowEvent.entity_id.in_(entity_ids)
            )
        query = query.filter(or_(*scope_filters))
    return query


def _flow_ledger_counts(target, *, driver_id=None, scoped_log_ids=frozenset()):
    try:
        flow_query = _scoped_flow_event_query(target, driver_id=driver_id, scoped_log_ids=scoped_log_ids)
        event_count = flow_query.count()
        active_exceptions = flow_query.filter(
            FlowEvent.event_type == "MISMATCH_DETECTED",
        ).count()
        manifest_query = FlowManifest.query.filter(FlowManifest.current_status.notin_(["reconciled", "approved", "closed"]))
        if driver_id:
            manifest_query = manifest_query.filter_by(driver_id=driver_id)
        open_manifests = manifest_query.count()
        manifest_line_query = ManifestLine.query
        if driver_id:
            manifest_line_query = manifest_line_query.join(FlowManifest, ManifestLine.manifest_id == FlowManifest.id).filter(FlowManifest.driver_id == driver_id)
        manifest_line_count = manifest_line_query.count()
    except SQLAlchemyError:
        db.session.rollback()
        return {"event_count": 0, "active_exceptions": 0, "open_manifests": 0, "manifest_line_count": 0, "ledger_ready": False}
    return {
        "event_count": event_count,
        "active_exceptions": active_exceptions,
        "open_manifests": open_manifests,
        "manifest_line_count": manifest_line_count,
        "ledger_ready": True,
    }


def _flow_object_cards(queue_summary, floor_summary, ledger_counts):
    route_only_note = "Route-only data. Attach manifest or enter paper data to build expected flow."
    manifest_note = f"{ledger_counts['manifest_line_count']} expected line(s)." if ledger_counts["open_manifests"] else route_only_note
    return [
        {
            "key": "wip",
            "label": "WIP Lot",
            "status": "open" if queue_summary["open_count"] else "none",
            "count": queue_summary["open_count"],
            "headline": f"{queue_summary['open_count']} open",
            "detail": "Production source queue.",
        },
        {
            "key": "staging",
            "label": "Staging Node",
            "status": "waiting" if queue_summary["waiting_count"] else "none",
            "count": queue_summary["waiting_count"],
            "headline": f"{queue_summary['waiting_count']} waiting",
            "detail": "Staged or waiting work.",
        },
        {
            "key": "load_build",
            "label": "Load Build / Trailer",
            "status": "active" if queue_summary["active_count"] else "none",
            "count": queue_summary["active_count"],
            "headline": f"{queue_summary['active_count']} active",
            "detail": "Trailer/load-build moves.",
        },
        {
            "key": "manifested",
            "label": "Manifest",
            "status": "open" if ledger_counts["open_manifests"] else "needs_review",
            "count": ledger_counts["open_manifests"],
            "headline": f"{ledger_counts['open_manifests']} open" if ledger_counts["open_manifests"] else "Route-only data",
            "detail": manifest_note,
        },
        {
            "key": "in_transit",
            "label": "In Transit Load",
            "status": "active" if floor_summary["active_stop_count"] else "none",
            "count": floor_summary["active_stop_count"],
            "headline": f"{floor_summary['active_stop_count']} active",
            "detail": "Current route movement.",
        },
        {
            "key": "receiving",
            "label": "Receiving Node",
            "status": "completed" if floor_summary["completed_stop_count"] else "none",
            "count": floor_summary["completed_stop_count"],
            "headline": f"{floor_summary['completed_stop_count']} done",
            "detail": "Received or closed steps.",
        },
        {
            "key": "exceptions",
            "label": "Exception / Hold / Scrap",
            "status": "blocked" if queue_summary["blocked_count"] + ledger_counts["active_exceptions"] else "none",
            "count": queue_summary["blocked_count"] + ledger_counts["active_exceptions"],
            "headline": f"{queue_summary['blocked_count'] + ledger_counts['active_exceptions']} open issues",
            "detail": "Structured exception signals.",
        },
    ]


def _flow_object_key_for_event(event_type):
    event_type = (event_type or "").upper()
    if event_type in {"WIP_STARTED"}:
        return "object:wip"
    if event_type in {"WIP_COMPLETED", "STAGED"}:
        return "object:staging"
    if event_type in {"ASSIGNED_TO_TRAILER", "LOADED_TO_CONTAINER", "REMOVED_FROM_CONTAINER"}:
        return "object:load_build"
    if event_type in {"DOCUMENT_UPLOADED", "PROOF_ATTACHED", "MANIFEST_CREATED", "MANIFEST_INITIALIZED", "MANIFEST_ATTACHED"}:
        return "object:manifested"
    if event_type in {"DEPARTED_ORIGIN", "IN_TRANSIT"}:
        return "object:in_transit"
    if event_type in {"ARRIVED_DESTINATION", "UNLOADED", "RECEIVED", "RECONCILED"}:
        return "object:receiving"
    if event_type in {
        "QA_HOLD_PLACED",
        "SCRAP_MARKED",
        "DAMAGE_REPORTED",
        "FORKLIFT_ISSUE_REPORTED",
        "DELAY_REPORTED",
        "MISMATCH_DETECTED",
        "EXPECTED_BUT_NOT_SCANNED",
        "SCANNED_BUT_NOT_EXPECTED",
    }:
        return "object:exceptions"
    return None


def _flow_source_for_event(event_type):
    event_type = (event_type or "").upper()
    if event_type in {"WIP_COMPLETED", "STAGED"}:
        return "object:wip"
    if event_type in {"ASSIGNED_TO_TRAILER", "LOADED_TO_CONTAINER", "REMOVED_FROM_CONTAINER"}:
        return "object:staging"
    if event_type in {"DOCUMENT_UPLOADED", "PROOF_ATTACHED", "MANIFEST_CREATED", "MANIFEST_INITIALIZED", "MANIFEST_ATTACHED"}:
        return "object:load_build"
    if event_type in {"DEPARTED_ORIGIN", "IN_TRANSIT"}:
        return "object:manifested"
    if event_type in {"ARRIVED_DESTINATION"}:
        return "object:in_transit"
    if event_type in {"UNLOADED", "RECEIVED", "RECONCILED"}:
        return "object:receiving"
    if event_type in {
        "QA_HOLD_PLACED",
        "SCRAP_MARKED",
        "DAMAGE_REPORTED",
        "FORKLIFT_ISSUE_REPORTED",
        "DELAY_REPORTED",
        "MISMATCH_DETECTED",
        "EXPECTED_BUT_NOT_SCANNED",
        "SCANNED_BUT_NOT_EXPECTED",
    }:
        return "object:receiving"
    return None


def _event_node_key(value):
    key = _location_key(value or "")
    return f"node:{key}" if key else None


def _event_entity_key(event):
    if event.entity_type and event.entity_id:
        return f"{event.entity_type}:{event.entity_id}"
    return None


def _flow_map_edges(target, *, driver_id=None, scoped_log_ids=frozenset()):
    """Return FlowMapEdge projection rows derived only from FlowEvent ledger rows."""
    try:
        events = (
            _scoped_flow_event_query(target, driver_id=driver_id, scoped_log_ids=scoped_log_ids)
            .order_by(FlowEvent.occurred_at.asc(), FlowEvent.id.asc())
            .all()
        )
    except SQLAlchemyError:
        db.session.rollback()
        return []

    edges = []
    last_by_scope = {}
    latest_edge_id = None
    for event in events:
        payload = event.payload_json or {}
        scope = event.correlation_id or event.route_id or f"{event.entity_type}:{event.entity_id}"
        previous = last_by_scope.get(scope)
        previous_target = previous["target_key"] if previous else None

        source_key = payload.get("source_node_key") or payload.get("source_key") or _flow_source_for_event(event.event_type) or previous_target
        target_key = payload.get("target_node_key") or payload.get("target_key") or _flow_object_key_for_event(event.event_type)
        if not source_key and event.origin_node_id:
            source_key = _event_node_key(event.origin_node_id)
        if not target_key and event.destination_node_id:
            target_key = _event_node_key(event.destination_node_id)
        if source_key == target_key and previous_target:
            source_key = previous_target
        if not source_key or not target_key or source_key == target_key:
            last_by_scope[scope] = {"event_id": event.id, "target_key": target_key or source_key}
            continue

        is_exception = event.event_type in {
            "MISMATCH_DETECTED",
            "QA_HOLD_PLACED",
            "SCRAP_MARKED",
            "DAMAGE_REPORTED",
            "FORKLIFT_ISSUE_REPORTED",
            "DELAY_REPORTED",
            "EXPECTED_BUT_NOT_SCANNED",
            "SCANNED_BUT_NOT_EXPECTED",
        }
        status = "exception" if is_exception else _flow_projection_status(event.event_type)
        edge = {
            "id": f"flow-edge-{event.id}",
            "event_id": event.id,
            "previous_event_id": payload.get("previous_event_id") or (previous["event_id"] if previous else None),
            "source_key": source_key,
            "target_key": target_key,
            "origin_node_key": _event_node_key(event.origin_node_id),
            "destination_node_key": _event_node_key(event.destination_node_id),
            "entity_key": _event_entity_key(event),
            "entity_type": event.entity_type,
            "entity_id": event.entity_id,
            "route_id": event.route_id,
            "manifest_id": event.manifest_id,
            "container_id": event.container_id,
            "stop_id": event.stop_id,
            "event_type": event.event_type,
            "status": status,
            "truth_level": "ledger",
            "occurred_at": event.occurred_at.isoformat() if event.occurred_at else "",
            "source": event.source,
            "actor_role": event.actor_role,
            "proof_label": "document" if event.document_id else ("photo" if event.photo_id else "none"),
            "is_live": False,
            "is_exception": is_exception,
            "label": (event.event_type or "FLOW_EVENT").replace("_", " ").title(),
        }
        edges.append(edge)
        latest_edge_id = edge["id"]
        last_by_scope[scope] = {"event_id": event.id, "target_key": target_key}

    for edge in edges:
        edge["is_live"] = edge["id"] == latest_edge_id and edge["status"] not in {"completed", "reconciled", "closed"}
    return edges


def _flow_projection_status(event_type):
    event_type = (event_type or "").upper()
    if event_type in {"RECONCILED", "RECEIVED", "UNLOADED"}:
        return "completed"
    if event_type in {"ARRIVED_DESTINATION", "STAGED"}:
        return "waiting"
    if event_type in {"DEPARTED_ORIGIN", "IN_TRANSIT", "ASSIGNED_TO_TRAILER", "LOADED_TO_CONTAINER"}:
        return "active"
    return "open"


def _timing_by_node(target):
    rows = plant_forecast_rows(target)
    timing = {}
    for row in rows:
        key = _location_key(row.get("plant") or row.get("plant_id"))
        timing[key] = {
            "estimate_minutes": row.get("estimate_minutes"),
            "estimate_label": row.get("estimate_label"),
            "today_count": row.get("today_count"),
            "confidence": row.get("confidence"),
            "basis": row.get("basis"),
        }
    return timing


def _move_item(req, *, now, has_issue=False):
    log = getattr(req, "linked_driver_log", None)
    cargo = cargo_state_for_request(req, log=log)
    next_action = next_action_for_request(req, has_open_issue=has_issue, cargo=cargo)
    origin = _location_label(req.origin_location_text) or NOT_TRACKED
    destination = _location_label(req.destination_location_text) or NOT_TRACKED
    status = (req.status or "open").lower()
    return {
        "item_id": f"move_request-{req.id}",
        "item_type": "move_request",
        "label": req.display_number,
        "plant_location": f"{origin} -> {destination}",
        "stage": _status_label(status),
        "trailer": None,
        "carrier_unit_count": None,
        "rack_count": None,
        "actual_prefix": None,
        "tool_number": None,
        "max_cycle": None,
        "capacity": None,
        "description": _clean(req.raw_text) or SAFE_EMPTY,
        "age_minutes": _age_minutes(req.requested_at, now=now),
        "status": status,
        "status_label": _status_label(status),
        "next_action": next_action,
        "linked_request_id": req.id,
        "linked_route_stop_id": req.linked_driver_log_id,
        "linked_document_id": req.linked_document_id,
        "linked_transfer_id": req.linked_plant_transfer_id,
        "origin_label": origin,
        "destination_label": destination,
        "related_path_key": f"{_location_key(origin)}--{_location_key(destination)}",
        "related_node_key": _location_key(destination),
        "cargo_text": _clean(req.cargo_text) or SAFE_EMPTY,
        "part_number": _clean(req.part_number),
        "quantity_text": _quantity_text(req),
        "priority": (req.priority or "normal").lower(),
        "is_hot_part": (req.priority or "").lower() in {"hot", "safety"},
        "is_hold_signal": _is_hold_signal(req.request_type, req.raw_text, req.cargo_text, req.notes, req.blocked_reason),
        "assigned_driver": _clean(req.assigned_display) or "Unassigned",
        "document_summary": f"Document #{req.linked_document_id}" if req.linked_document_id else DOCUMENT_MISSING,
        "source_label": FRIENDLY_SOURCE["MoveRequest"],
        "view_url": _safe_url("manager.edit_move_request", request_id=req.id),
    }


def _route_item(log, *, now, issue_stop_ids=frozenset(), damaged_stop_ids=frozenset(), sequence_number=None):
    status = "completed" if log.depart_time else "waiting"
    has_issue = log.id in issue_stop_ids or log.id in damaged_stop_ids
    if has_issue and not log.depart_time:
        status = "needs_review"
    cargo = cargo_state_for_log(log, has_open_damage=log.id in damaged_stop_ids)
    wait_minutes = wait_minutes_for_log(log, now=None) if not log.depart_time else (log.dock_wait_minutes or 0)
    display_label = f"Stop {sequence_number}" if sequence_number else f"Stop {log.id}"
    return {
        "item_id": f"route_stop-{log.id}",
        "item_type": "route_stop",
        "label": display_label,
        "display_label": display_label,
        "sequence_number": sequence_number,
        "source_label": FRIENDLY_SOURCE["DriverLog"],
        "plant_location": _location_label(log.plant_name) or SAFE_EMPTY,
        "related_node_key": _location_key(_location_label(log.plant_name) or ""),
        "related_path_key": None,
        "stage": "Completed" if log.depart_time else "Waiting",
        "trailer": None,
        "carrier_unit_count": None,
        "rack_count": None,
        "actual_prefix": None,
        "tool_number": None,
        "max_cycle": None,
        "capacity": None,
        "description": cargo["label"],
        "age_minutes": wait_minutes if not log.depart_time else None,
        "status": status,
        "status_label": _status_label(status),
        "next_action": "Review issue" if has_issue else ("No action needed" if log.depart_time else "Record departure"),
        "linked_request_id": None,
        "linked_route_stop_id": log.id,
        "linked_document_id": None,
        "linked_transfer_id": None,
        "arrival_at": log.arrive_time or "",
        "departure_at": log.depart_time or "",
        "arrived_with": log.load_size or NOT_TRACKED,
        "departed_with": log.depart_load_size or NOT_TRACKED,
        "part_number": _clean(log.part_number),
        "is_hot_part": bool(log.hot_parts),
        "is_hold_signal": _is_hold_signal(log.load_size, log.depart_load_size, log.secondary_load, log.downtime_reason, log.plant_name),
        "view_url": _safe_url("manager.view_driver_log", log_id=log.id),
    }


def _transfer_item(transfer):
    origin = _location_label(transfer.ship_from) or NOT_TRACKED
    destination = _location_label(transfer.ship_to) or NOT_TRACKED
    transfer_number = transfer.transfer_number or transfer.id
    line_count = len(getattr(transfer, "lines", []) or [])
    return {
        "item_id": f"plant_transfer-{transfer.id}",
        "item_type": "plant_transfer",
        "label": f"Plant Transfer {transfer_number}",
        "plant_location": f"{origin} -> {destination}",
        "stage": "Proof",
        "trailer": _clean(transfer.trailer_number) or None,
        "carrier_unit_count": None,
        "rack_count": None,
        "actual_prefix": None,
        "tool_number": None,
        "max_cycle": None,
        "capacity": None,
        "description": f"{line_count} line{'s' if line_count != 1 else ''}" if line_count else "Transfer proof recorded",
        "age_minutes": None,
        "status": "completed",
        "status_label": "Completed",
        "next_action": "No action needed",
        "linked_request_id": None,
        "linked_route_stop_id": None,
        "linked_document_id": None,
        "linked_transfer_id": transfer.id,
        "origin_label": origin,
        "destination_label": destination,
        "related_path_key": f"{_location_key(origin)}--{_location_key(destination)}",
        "related_node_key": _location_key(destination),
        "source_label": FRIENDLY_SOURCE["PlantTransfer"],
        "view_url": _safe_url("manager.view_plant_transfer", transfer_id=transfer.id),
    }


def _damage_item(report, *, now):
    issue = classify_issue(category="damage", severity="critical")
    return {
        "item_id": f"damage-{report.id}",
        "item_type": "issue",
        "label": f"Damage Report #{report.id}",
        "plant_location": _location_label(report.plant_name) or SAFE_EMPTY,
        "related_node_key": _location_key(_location_label(report.plant_name) or ""),
        "related_path_key": None,
        "stage": issue["category_label"],
        "trailer": _clean(report.trailer_number) or None,
        "carrier_unit_count": None,
        "rack_count": None,
        "actual_prefix": None,
        "tool_number": None,
        "max_cycle": None,
        "capacity": None,
        "description": _clean(report.description) or "Damage report recorded.",
        "age_minutes": _age_minutes(report.created_at, now=now),
        "status": "blocked",
        "status_label": issue["level_label"],
        "next_action": "Review issue",
        "linked_request_id": None,
        "linked_route_stop_id": report.driver_log_id,
        "linked_document_id": None,
        "linked_transfer_id": report.plant_transfer_id,
        "source_label": FRIENDLY_SOURCE["DamageReport"],
        "view_url": _safe_url("manager.view_damage_report", report_id=report.id),
    }


def _exception_view_url(event):
    if event.target_type == "plant_transfer" and event.target_id:
        return _safe_url("manager.view_plant_transfer", transfer_id=event.target_id)
    if event.target_type == "move_request" and event.target_id:
        return _safe_url("manager.edit_move_request", request_id=event.target_id)
    stop_id = event.stop_id or event.driver_log_id
    if stop_id:
        return _safe_url("manager.view_driver_log", log_id=stop_id)
    return None


def _exception_item(event, *, now):
    issue = classify_issue(category=event.event_type, severity=event.severity, label=event.summary)
    return {
        "item_id": f"issue-{event.id}",
        "item_type": "issue",
        "label": event.summary,
        "plant_location": _location_label(event.plant_name) or SAFE_EMPTY,
        "related_node_key": _location_key(_location_label(event.plant_name) or ""),
        "related_path_key": None,
        "stage": issue["category_label"],
        "trailer": None,
        "carrier_unit_count": None,
        "rack_count": None,
        "actual_prefix": None,
        "tool_number": None,
        "max_cycle": None,
        "capacity": None,
        "description": _clean(event.details) or _clean(event.summary) or "Issue recorded.",
        "age_minutes": _age_minutes(event.created_at, now=now),
        "status": issue["level"],
        "status_label": issue["level_label"],
        "next_action": "Review issue",
        "linked_request_id": event.target_id if event.target_type == "move_request" else None,
        "linked_route_stop_id": event.stop_id or event.driver_log_id,
        "linked_document_id": None,
        "linked_transfer_id": event.target_id if event.target_type == "plant_transfer" else None,
        "source_label": FRIENDLY_SOURCE["IssueEvent"],
        "view_url": _exception_view_url(event),
    }


def _redact_read_only_context(*, flow_nodes, flow_lanes, flow_items, route_overlay, transport_token, proof_markers, issue_markers):
    for item in flow_items:
        item_type = item.get("item_type")
        if item_type == "move_request":
            item.update({
                "label": "Move request",
                "description": "Dispatch details hidden",
                "cargo_text": SAFE_EMPTY,
                "part_number": "",
                "quantity_text": "",
                "assigned_driver": "Restricted",
                "document_summary": DOCUMENT_MISSING,
            })
        elif item_type == "route_stop":
            item.update({
                "arrived_with": NOT_TRACKED,
                "departed_with": NOT_TRACKED,
                "part_number": "",
            })
        item.update({
            "linked_request_id": None,
            "linked_route_stop_id": None,
            "linked_document_id": None,
            "linked_transfer_id": None,
            "view_url": None,
        })

    for lane in flow_lanes:
        lane["linked_request_ids"] = []
        lane["linked_driver_log_ids"] = []
        lane["linked_transfer_ids"] = []
        lane["view_url"] = None

    for node in flow_nodes:
        node["view_url"] = None
        node["active_moves_url"] = None
        profile = node.get("production_profile") or {}
        profile["material_lines"] = []
        if profile.get("console_left"):
            profile["console_left"][0]["value"] = "Restricted"
        for row_key in ("console_left", "console_right"):
            rows = profile.get(row_key) or []
            for row in rows:
                if "driver" in str(row.get("label", "")).lower() or "material" in str(row.get("label", "")).lower():
                    row["value"] = "Restricted"

    if route_overlay:
        route_overlay.update({
            "driver_name": None,
            "driver_id": None,
            "route_label": "Route proof overlay",
        })
        for marker in route_overlay.get("stop_markers") or []:
            marker.pop("internal_stop_id", None)
            marker["arrived_with"] = NOT_TRACKED
            marker["departed_with"] = NOT_TRACKED
    if transport_token:
        transport_token["label"] = "Route shuttle"
        transport_token["cargo"] = NOT_TRACKED
    for marker in proof_markers:
        marker["label"] = "Proof attached"
    for marker in issue_markers:
        marker["label"] = "Issue"


def build_production_flow_context(
    date=None,
    driver_id=None,
    selected_plant=None,
    selected_move_request_id=None,
    selected_stop_id=None,
    mode="widescreen",
    can_edit=False,
    can_assign=False,
    can_review=False,
    can_export=False,
):
    """Build a production-flow context from real MoveDefense records only."""
    target = _target_date(date)
    mode = (mode or "widescreen").strip().lower()
    if mode == "production":
        mode = "widescreen"
    if mode not in {"mobile", "widescreen", "plant_floor", "admin"}:
        mode = "widescreen"
    now = datetime.utcnow()
    requests = _move_requests(target, driver_id=driver_id, selected_move_request_id=selected_move_request_id)
    logs = _driver_logs(target, driver_id=driver_id, selected_stop_id=selected_stop_id)
    scoped_log_ids = frozenset(log.id for log in logs if getattr(log, "id", None))
    transfers = _plant_transfers(target, driver_id=driver_id)
    damage_reports = _damage_reports(target, driver_id=driver_id)
    issue_events = _issue_events(target, driver_id=driver_id)
    timing_by_node = _timing_by_node(target)
    ledger_counts = _flow_ledger_counts(target, driver_id=driver_id, scoped_log_ids=scoped_log_ids)
    redact_read_only = bool(mode == "plant_floor" and not any((can_edit, can_assign, can_review, can_export)))

    nodes = {}
    lanes = {}
    items = []
    _seed_configured_plant_flow(nodes, lanes)
    issue_stop_ids = {event.stop_id or event.driver_log_id for event in issue_events if event.stop_id or event.driver_log_id}
    damaged_stop_ids = {report.driver_log_id for report in damage_reports if report.driver_log_id}

    queue_summary = {
        "open_count": 0,
        "active_count": 0,
        "waiting_count": 0,
        "blocked_count": 0,
        "completed_count": 0,
        "unassigned_count": 0,
        "needs_attention_count": 0,
        "document_needed_count": 0,
        "hot_count": 0,
        "flow_event_count": ledger_counts["event_count"],
        "open_manifest_count": ledger_counts["open_manifests"],
        "ledger_exception_count": ledger_counts["active_exceptions"],
    }

    for req in requests:
        status = (req.status or "open").lower()
        has_issue = status in BLOCKED_STATUSES or bool(_clean(req.blocked_reason))
        is_hot_request = (req.priority or "").lower() in {"hot", "safety"}
        is_hold_request = _is_hold_signal(req.request_type, req.raw_text, req.cargo_text, req.notes, req.blocked_reason)
        item = _move_item(req, now=now, has_issue=has_issue)
        items.append(item)

        bucket = _status_bucket(status)
        if bucket == "blocked":
            queue_summary["blocked_count"] += 1
        elif bucket == "waiting":
            queue_summary["waiting_count"] += 1
        elif bucket == "active":
            queue_summary["active_count"] += 1
        elif bucket == "completed":
            queue_summary["completed_count"] += 1
        else:
            queue_summary["open_count"] += 1
        if status not in {"completed", "cancelled"} and not (req.assigned_driver_id or _clean(req.assigned_driver_text)):
            queue_summary["unassigned_count"] += 1
        if has_issue:
            queue_summary["needs_attention_count"] += 1
        if status not in {"completed", "cancelled"} and not (req.linked_document_id or req.linked_plant_transfer_id):
            queue_summary["document_needed_count"] += 1
        if is_hot_request:
            queue_summary["hot_count"] += 1

        hot_focus_label = req.destination_location_text or req.origin_location_text
        for label in (req.origin_location_text, req.destination_location_text):
            node = _node(nodes, label)
            if not node:
                continue
            _bump_status(node, status, has_issue=has_issue)
            if is_hot_request and _location_key(label) == _location_key(hot_focus_label):
                node["hot_count"] = node.get("hot_count", 0) + 1
            if is_hold_request:
                node["hold_count"] = node.get("hold_count", 0) + 1
            _add_source(node["meta"], "MoveRequest")

        lane = _lane(lanes, req.origin_location_text, req.destination_location_text)
        if lane:
            _bump_status(lane, status)
            if is_hot_request:
                lane["hot_count"] += 1
            if is_hold_request:
                lane["hold_count"] += 1
            lane["linked_request_ids"].append(req.id)
            age = _age_minutes(req.requested_at, now=now)
            if age is not None:
                lane["oldest_age_minutes"] = age if lane["oldest_age_minutes"] is None else max(lane["oldest_age_minutes"], age)

    sequence_by_log_id = {}
    sorted_logs_by_driver = {}
    for log in logs:
        sorted_logs_by_driver.setdefault(log.driver_id, []).append(log)
    for driver_logs in sorted_logs_by_driver.values():
        driver_logs.sort(key=lambda log: (log.created_at or datetime.min, log.id))
        for idx, log in enumerate(driver_logs, start=1):
            sequence_by_log_id[log.id] = idx

    for log in logs:
        item = _route_item(
            log,
            now=now,
            issue_stop_ids=issue_stop_ids,
            damaged_stop_ids=damaged_stop_ids,
            sequence_number=sequence_by_log_id.get(log.id),
        )
        items.append(item)
        node = _node(nodes, log.plant_name)
        if not node:
            continue
        _bump_status(node, "completed" if log.depart_time else "waiting", has_issue=log.id in issue_stop_ids or log.id in damaged_stop_ids)
        if getattr(log, "hot_parts", False):
            node["hot_count"] = node.get("hot_count", 0) + 1
        if _is_hold_signal(log.load_size, log.depart_load_size, log.secondary_load, log.downtime_reason, log.plant_name):
            node["hold_count"] = node.get("hold_count", 0) + 1
        _add_source(node["meta"], "DriverLog")

    for driver_logs in sorted_logs_by_driver.values():
        for prev_log, current_log in zip(driver_logs, driver_logs[1:]):
            lane = _lane(lanes, prev_log.plant_name, current_log.plant_name)
            if not lane:
                continue
            status = "completed" if current_log.depart_time else "waiting"
            has_issue = current_log.id in issue_stop_ids or current_log.id in damaged_stop_ids
            _bump_status(lane, "blocked" if has_issue else status)
            if getattr(prev_log, "hot_parts", False) or getattr(current_log, "hot_parts", False):
                lane["hot_count"] += 1
            if _is_hold_signal(prev_log.load_size, prev_log.depart_load_size, current_log.load_size, current_log.depart_load_size, current_log.downtime_reason, current_log.plant_name):
                lane["hold_count"] += 1
            lane["linked_driver_log_ids"].extend([prev_log.id, current_log.id])

    for transfer in transfers:
        item = _transfer_item(transfer)
        items.append(item)
        for label in (transfer.ship_from, transfer.ship_to):
            node = _node(nodes, label)
            if node:
                _bump_status(node, "completed")
                _add_source(node["meta"], "PlantTransfer")
        lane = _lane(lanes, transfer.ship_from, transfer.ship_to)
        if lane:
            _bump_status(lane, "completed")
            if _is_hold_signal(transfer.ship_from, transfer.ship_to):
                lane["hold_count"] += 1
            lane["linked_transfer_ids"].append(transfer.id)

    for report in damage_reports:
        item = _damage_item(report, now=now)
        items.append(item)
        node = _node(nodes, report.plant_name)
        if node:
            node["issue_count"] += 1
            node["blocked_count"] += 1
            _add_source(node["meta"], "DamageReport")

    for event in issue_events:
        item = _exception_item(event, now=now)
        items.append(item)
        node = _node(nodes, event.plant_name)
        if node:
            node["issue_count"] += 1
            node["blocked_count"] += 1
            _add_source(node["meta"], "IssueEvent")

    for key, node in nodes.items():
        node["meta"]["timing"] = timing_by_node.get(key)
        node["worst_status"] = _worst_status(
            blocked_count=node["blocked_count"],
            waiting_count=node["waiting_count"],
            active_count=node["active_count"],
            open_count=node["open_count"],
            completed_count=node["completed_count"],
        )
        node["next_action"] = _node_next_action(node)

    overlay_driver_id = driver_id
    if not overlay_driver_id and sorted_logs_by_driver and len(sorted_logs_by_driver) == 1:
        overlay_driver_id = next(iter(sorted_logs_by_driver))

    route_overlay = None
    overlay_pair_keys = set()
    if overlay_driver_id and sorted_logs_by_driver.get(overlay_driver_id):
        overlay_logs = sorted_logs_by_driver[overlay_driver_id]
        path_node_keys = []
        stop_markers = []
        for log in overlay_logs:
            location_label = _location_label(log.plant_name) or SAFE_EMPTY
            node_key = _location_key(location_label) if location_label != SAFE_EMPTY else None
            if node_key and (not path_node_keys or path_node_keys[-1] != node_key):
                path_node_keys.append(node_key)
            has_issue = log.id in issue_stop_ids or log.id in damaged_stop_ids
            wait_minutes = wait_minutes_for_log(log, now=None) if not log.depart_time else (log.dock_wait_minutes or 0)
            stop_markers.append({
                "display_label": f"Stop {sequence_by_log_id.get(log.id)}",
                "sequence_number": sequence_by_log_id.get(log.id),
                "location_key": node_key,
                "location_label": location_label,
                "arrival_at": log.arrive_time or "",
                "departure_at": log.depart_time or "",
                "wait_minutes": wait_minutes,
                "arrived_with": log.load_size or NOT_TRACKED,
                "departed_with": log.depart_load_size or NOT_TRACKED,
                "is_hot_part": bool(log.hot_parts),
                "is_hold_signal": _is_hold_signal(log.load_size, log.depart_load_size, log.secondary_load, log.downtime_reason, log.plant_name),
                "proof_status": "attached" if log.depart_time else "pending",
                "issue_status": "needs_review" if has_issue else "ok",
                "next_action": "Review issue" if has_issue else ("No action needed" if log.depart_time else "Record departure"),
                "internal_stop_id": log.id,
            })
        for a, b in zip(path_node_keys, path_node_keys[1:]):
            overlay_pair_keys.add((a, b))
        driver_name = None
        if overlay_driver_id:
            user = User.query.get(overlay_driver_id)
            if user:
                driver_name = user.display_name
        if all(log.depart_time for log in overlay_logs):
            overlay_status = "completed"
        elif any(log.depart_time for log in overlay_logs):
            overlay_status = "in_progress"
        else:
            overlay_status = "in_progress"
        route_overlay = {
            "driver_name": driver_name,
            "driver_id": overlay_driver_id,
            "route_label": f"Route proof overlay: {driver_name}" if driver_name else "Route proof overlay",
            "date": target,
            "status": overlay_status,
            "path_node_keys": path_node_keys,
            "stop_markers": stop_markers,
        }

    for lane in lanes.values():
        lane["linked_request_ids"] = sorted(set(lane["linked_request_ids"]))
        lane["linked_driver_log_ids"] = sorted(set(lane["linked_driver_log_ids"]))
        lane["linked_transfer_ids"] = sorted(set(lane["linked_transfer_ids"]))
        lane["worst_status"] = _worst_status(
            blocked_count=lane["blocked_count"],
            waiting_count=lane["waiting_count"],
            active_count=lane["active_count"],
            open_count=lane["open_count"],
            completed_count=lane["completed_count"],
        )
        lane["replay_status"] = _replay_status(
            hot_count=lane.get("hot_count", 0),
            hold_count=lane.get("hold_count", 0),
            blocked_count=lane["blocked_count"],
            waiting_count=lane["waiting_count"],
            active_count=lane["active_count"],
            open_count=lane["open_count"],
            completed_count=lane["completed_count"],
        )
        if lane.get("is_configured_flow"):
            lane["lane_type"] = "plant_flow"
            lane["default_visible"] = True
        else:
            lane["lane_type"] = _lane_type(lane["worst_status"])
            lane["default_visible"] = False
        lane["proof_needed_count"] = sum(
            1 for item in items
            if item.get("item_type") == "move_request"
            and item.get("origin_label") == lane["origin_label"]
            and item.get("destination_label") == lane["destination_label"]
            and not item.get("linked_document_id") and not item.get("linked_transfer_id")
            and item.get("status") not in {"completed", "cancelled"}
        )
        lane["route_overlay_active"] = (lane["origin_key"], lane["destination_key"]) in overlay_pair_keys

    for node in nodes.values():
        node["proof_needed_count"] = sum(
            1 for item in items
            if item.get("item_type") == "move_request"
            and (item.get("origin_label") == node["label"] or item.get("destination_label") == node["label"])
            and not item.get("linked_document_id") and not item.get("linked_transfer_id")
            and item.get("status") not in {"completed", "cancelled"}
        )
        node["source_labels"] = list(node["meta"].get("source_labels", []))

    proof_markers = []
    for item in items:
        if item.get("linked_document_id") or item.get("linked_transfer_id"):
            kind = "transfer" if item.get("linked_transfer_id") else "document"
            proof_markers.append({
                "marker_id": f"proof-{item['item_id']}",
                "kind": kind,
                "label": item.get("display_label") or item.get("label"),
                "location_key": _location_key(item.get("plant_location") or "") or None,
                "linked_item_id": item["item_id"],
                "attached": True,
                "next_action": item.get("next_action") or "No action needed",
            })

    issue_markers = []
    for item in items:
        if item.get("status") in {"blocked", "needs_review", "critical", "high"}:
            issue_markers.append({
                "marker_id": f"issue-{item['item_id']}",
                "label": item.get("display_label") or item.get("label"),
                "status": item["status"],
                "location_key": _location_key(item.get("plant_location") or "") or None,
                "linked_item_id": item["item_id"],
                "next_action": item.get("next_action") or "Review issue",
            })

    flow_nodes = sorted(
        nodes.values(),
        key=lambda n: (-(n["blocked_count"] + n["waiting_count"] + n["active_count"] + n["open_count"]), n["label"]),
    )
    flow_lanes = sorted(
        lanes.values(),
        key=lambda l: (
            0 if l.get("default_visible") else 1,
            l.get("flow_sequence", 999),
            -(l["blocked_count"] + l["waiting_count"] + l["active_count"] + l["open_count"] + l["completed_count"]),
            l["origin_label"],
            l["destination_label"],
        ),
    )
    items.sort(key=lambda item: (item["status"] not in {"blocked", "needs_review", "critical", "high"}, item["age_minutes"] is None, -(item["age_minutes"] or 0), item["label"]))
    selected_node_key = _location_key(selected_plant) if selected_plant else None
    _apply_map_layout(flow_nodes, flow_lanes, items, selected_node_key=selected_node_key)
    _apply_production_profiles(flow_nodes, items)

    node_by_key = {node["key"]: node for node in flow_nodes}
    if route_overlay and route_overlay.get("path_node_keys"):
        segments = []
        marker_by_node_key = {marker.get("location_key"): marker for marker in route_overlay.get("stop_markers", []) if marker.get("location_key")}
        for index, (origin_key, destination_key) in enumerate(zip(route_overlay["path_node_keys"], route_overlay["path_node_keys"][1:])):
            origin_layout = node_by_key.get(origin_key, {}).get("layout")
            destination_layout = node_by_key.get(destination_key, {}).get("layout")
            if not origin_layout or not destination_layout:
                continue
            destination_marker = marker_by_node_key.get(destination_key, {})
            segment_status = _replay_status(
                hot_count=1 if destination_marker.get("is_hot_part") else 0,
                hold_count=1 if destination_marker.get("is_hold_signal") else 0,
                blocked_count=1 if destination_marker.get("issue_status") != "ok" else 0,
                waiting_count=1 if not destination_marker.get("departure_at") else 0,
                completed_count=1 if destination_marker.get("departure_at") else 0,
            )
            segments.append({
                "origin_key": origin_key,
                "destination_key": destination_key,
                "path_d": _route_proof_curve(origin_layout, destination_layout, index),
                "flow_sequence": index,
                "replay_status": segment_status,
            })
        route_overlay["path_segments"] = segments
    transport_token = None
    if route_overlay and route_overlay.get("stop_markers"):
        markers = route_overlay["stop_markers"]
        active_marker = next((marker for marker in markers if not marker.get("departure_at")), markers[-1])
        layout = node_by_key.get(active_marker.get("location_key"), {}).get("layout") or {}
        cargo_text = active_marker.get("departed_with") or active_marker.get("arrived_with") or ""
        loaded = bool(cargo_text and cargo_text.lower() not in {"empty", "none", "not tracked yet"})
        transport_token = {
            "label": route_overlay.get("driver_name") or "Route shuttle",
            "badge": "FULL" if loaded else "MT",
            "cargo": cargo_text or NOT_TRACKED,
            "status": "Docked" if active_marker.get("location_key") else "En route",
            "dock": active_marker.get("location_label") or NOT_TRACKED,
            "x": round(_clamp_layout((layout.get("x") or 50) + 5, 10, 88), 2),
            "y": round(_clamp_layout((layout.get("y") or 50) + 6, 9, 88), 2),
        }
        route_overlay["transport_token"] = transport_token

    if redact_read_only:
        _redact_read_only_context(
            flow_nodes=flow_nodes,
            flow_lanes=flow_lanes,
            flow_items=items,
            route_overlay=route_overlay,
            transport_token=transport_token,
            proof_markers=proof_markers,
            issue_markers=issue_markers,
        )

    console_node = None
    if flow_nodes:
        console_node = next((node for node in flow_nodes if node.get("issue_count") or node.get("blocked_count")), None)
        if not console_node:
            console_node = next((node for node in flow_nodes if node.get("waiting_count") or node.get("active_count") or node.get("open_count")), None)
        if not console_node:
            console_node = flow_nodes[0]

    floor_summary = {
        "active_stop_count": len([log for log in logs if not log.depart_time]),
        "completed_stop_count": len([log for log in logs if log.depart_time]),
        "active_driver_count": len({log.driver_id for log in logs if not log.depart_time}),
        "transfer_count": len(transfers),
        "issue_count": len(damage_reports) + len(issue_events),
        "node_count": len(flow_nodes),
        "lane_count": len(flow_lanes),
        "production_snapshot_available": False,
        "carrier_unit_snapshot": None,
        "rack_capacity_snapshot": None,
        "data_scope_note": DATA_SCOPE_EMPTY,
    }
    no_flow_signals = not bool(flow_nodes or flow_lanes or items)
    flow_edges = _flow_map_edges(target, driver_id=driver_id, scoped_log_ids=scoped_log_ids)

    return {
        "mode": mode,
        "date": target,
        "flow_nodes": flow_nodes,
        "flow_lanes": flow_lanes,
        "flow_items": items,
        "flow_edges": flow_edges,
        "route_overlay": route_overlay,
        "transport_token": transport_token,
        "console_node": console_node,
        "proof_markers": proof_markers,
        "issue_markers": issue_markers,
        "queue_summary": queue_summary,
        "flow_objects": _flow_object_cards(queue_summary, floor_summary, ledger_counts),
        "flow_lanes_target": [
            {"key": "wip", "label": "WIP / Production", "count": queue_summary["open_count"]},
            {"key": "staging", "label": "Staging", "count": queue_summary["waiting_count"]},
            {"key": "load_build", "label": "Load Build", "count": queue_summary["active_count"]},
            {"key": "manifested", "label": "Manifested", "count": queue_summary["open_manifest_count"]},
            {"key": "in_transit", "label": "In Transit", "count": floor_summary["active_stop_count"]},
            {"key": "receiving", "label": "Receiving", "count": floor_summary["completed_stop_count"]},
            {"key": "exceptions", "label": "Exceptions / Holds / Scrap", "count": queue_summary["blocked_count"] + queue_summary["ledger_exception_count"]},
        ],
        "ledger_summary": {
            "ready": ledger_counts["ledger_ready"],
            "event_count": queue_summary["flow_event_count"],
            "open_manifest_count": queue_summary["open_manifest_count"],
            "manifest_line_count": ledger_counts["manifest_line_count"],
            "active_exception_count": queue_summary["blocked_count"] + queue_summary["ledger_exception_count"],
            "truth_statement": "The visual map is the product. The event ledger is the truth. Status is only a projection.",
        },
        "floor_summary": floor_summary,
        "selected_context": {
            "selected_plant": selected_plant,
            "selected_move_request_id": selected_move_request_id,
            "selected_stop_id": selected_stop_id,
            "selected_node_key": selected_node_key,
        },
        "permissions": {
            "can_view": True,
            "can_edit": bool(can_edit),
            "can_assign": bool(can_assign),
            "can_review": bool(can_review),
            "can_export": bool(can_export),
        },
        "empty_states": {
            "no_flow_signals": no_flow_signals,
            "flow_empty_message": "Configured plant flow only for this date.",
            "no_flow_nodes": not bool(flow_nodes),
            "no_flow_lanes": not bool(flow_lanes),
            "no_flow_items": not bool(items),
            "no_move_requests": not bool(requests),
            "no_route_activity": not bool(logs),
            "no_transfer_data": not bool(transfers),
            "no_production_snapshot": True,
            "carrier_unit_snapshot": CARRIER_SNAPSHOT_EMPTY,
            "rack_capacity": RACK_SNAPSHOT_EMPTY,
            "data_scope": DATA_SCOPE_EMPTY,
            "needs_attention_empty": "No production-flow issues found for this date.",
            "route_proof_only": DATA_SCOPE_ROUTE_ONLY,
        },
    }
