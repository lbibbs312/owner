"""Display-layer normalization for operational issues.

The app stores raw severities (``high`` / ``medium`` / ``followup`` / ``low``)
on :class:`~app.models.case.ExceptionEvent` and emits issue dicts from services
such as :func:`app.services.operations.build_exception_items` and
``management_readout``.  Those raw values are *not* changed by this module.

This is purely a render-time mapping to a small, consistent set of user-facing
levels and categories.  Most importantly it keeps **Critical** reserved for
genuinely critical situations (safety, damage, wrong delivery, stranded
equipment, route-blocking failure, customer-impacting miss, severe equipment
failure) so that routine short waits or blank fields never render as Critical.
"""

# User-facing escalation levels, ascending in urgency.
LEVELS = {
    "info": {"label": "Info", "rank": 0, "css": "issue-badge issue-info"},
    "watch": {"label": "Watch", "rank": 1, "css": "issue-badge issue-watch"},
    "action": {"label": "Action Needed", "rank": 2, "css": "issue-badge issue-action"},
    "high": {"label": "High", "rank": 3, "css": "issue-badge issue-high"},
    "critical": {"label": "Critical", "rank": 4, "css": "issue-badge issue-critical"},
}

# User-facing issue categories.
CATEGORIES = {
    "data_check": "Data Check",
    "workflow": "Workflow Issue",
    "delay": "Delay Issue",
    "equipment": "Equipment Issue",
    "request": "Request Issue",
    "document": "Document Issue",
    "cargo": "Cargo Issue",
    "safety": "Safety Issue",
}

DEFAULT_LEVEL = "info"
DEFAULT_CATEGORY = "workflow"
DEFAULT_WAIT_THRESHOLD = 120

# Categories that may never escalate to High/Critical at the display layer.
# A 1-minute wait or a blank field must never look like an emergency.
_LEVEL_CAP = {
    "data_check": "action",
    "delay": "action",
    "document": "action",
}

# Raw stored severity strings -> display level (fallback when category unknown).
_SEVERITY_FALLBACK = {
    "critical": "critical",
    "high": "high",
    "medium": "action",
    "warning": "watch",
    "followup": "watch",
    "low": "info",
    "info": "info",
}

# Known issue categories (as emitted across the app) -> (category, level).
# Keys are normalized (lowercased, whitespace-collapsed).
_CATEGORY_RULES = {
    # data completeness
    "missing time": ("data_check", "action"),
    "missing driver": ("data_check", "action"),
    "no driver initials": ("data_check", "watch"),
    "suspicious timing": ("data_check", "watch"),
    "impossible timing": ("data_check", "watch"),
    # documents
    "missing trailer": ("document", "action"),
    "missing document": ("document", "action"),
    "missing bol": ("document", "action"),
    "document issue": ("document", "action"),
    # workflow
    "missing departure": ("workflow", "action"),
    "route issue": ("workflow", "action"),
    "no pre-trip": ("workflow", "high"),
    "manager follow-up": ("workflow", "watch"),
    "blocked": ("workflow", "action"),
    "workflow issue": ("workflow", "action"),
    # delay
    "delayed dock time": ("delay", "action"),
    "timing status": ("delay", "watch"),
    "delay": ("delay", "watch"),
    "delay issue": ("delay", "watch"),
    # equipment
    "truck issue": ("equipment", "high"),
    "equipment issue": ("equipment", "high"),
    "stranded": ("equipment", "critical"),
    "stranded driver": ("equipment", "critical"),
    "stranded equipment": ("equipment", "critical"),
    "breakdown": ("equipment", "critical"),
    "severe equipment failure": ("equipment", "critical"),
    # request
    "open hot move": ("request", "high"),
    "hot move": ("request", "high"),
    "request issue": ("request", "action"),
    "customer-impacting miss": ("request", "critical"),
    # cargo
    "cargo mismatch": ("cargo", "action"),
    "cargo issue": ("cargo", "action"),
    "wrong delivery": ("cargo", "critical"),
    "wrong destination": ("cargo", "critical"),
    # safety / damage
    "damage flag": ("safety", "critical"),
    "damage": ("safety", "critical"),
    "damage report": ("safety", "critical"),
    "safety issue": ("safety", "critical"),
    "route-blocking failure": ("safety", "critical"),
}

# Substring fallbacks for free-text categories/labels (checked in order).
_KEYWORD_RULES = (
    ("damage", ("safety", "critical")),
    ("wrong deliver", ("cargo", "critical")),
    ("wrong destination", ("cargo", "critical")),
    ("misdeliver", ("cargo", "critical")),
    ("stranded", ("equipment", "critical")),
    ("breakdown", ("equipment", "critical")),
    ("route-blocking", ("safety", "critical")),
    ("safety", ("safety", "critical")),
    ("hot move", ("request", "high")),
    ("hot part", ("request", "high")),
    ("truck", ("equipment", "high")),
    ("maintenance", ("equipment", "high")),
    ("pre-trip", ("workflow", "high")),
    ("pretrip", ("workflow", "high")),
    ("departure", ("workflow", "action")),
    ("cargo", ("cargo", "action")),
    ("photo", ("document", "watch")),
    ("trailer", ("document", "action")),
    ("document", ("document", "action")),
    ("dock", ("delay", "action")),
    ("delay", ("delay", "watch")),
    ("timing", ("data_check", "watch")),
    ("missing", ("data_check", "action")),
    ("follow-up", ("workflow", "watch")),
    ("followup", ("workflow", "watch")),
)


def _norm(value):
    return " ".join(str(value or "").strip().lower().split())


def _rank(level):
    return LEVELS.get(level, LEVELS[DEFAULT_LEVEL])["rank"]


def _cap_level(category, level):
    cap = _LEVEL_CAP.get(category)
    if cap and _rank(level) > _rank(cap):
        return cap
    return level


def _lookup(category, label):
    key = _norm(category)
    if key and key in _CATEGORY_RULES:
        return _CATEGORY_RULES[key]
    haystack = f"{key} {_norm(label)}".strip()
    if not haystack:
        return None
    for needle, mapping in _KEYWORD_RULES:
        if needle in haystack:
            return mapping
    return None


def _build(category, level):
    category = category if category in CATEGORIES else DEFAULT_CATEGORY
    level = level if level in LEVELS else DEFAULT_LEVEL
    meta = LEVELS[level]
    return {
        "level": level,
        "level_label": meta["label"],
        "level_rank": meta["rank"],
        "level_class": meta["css"],
        "category": category,
        "category_label": CATEGORIES[category],
    }


def classify_wait(minutes, threshold=None):
    """Classify a dock/stop wait purely by elapsed minutes. Never Critical.

    Returns ``None`` when ``minutes`` is missing/non-numeric so callers can
    skip rendering a badge entirely.
    """
    if minutes is None:
        return None
    try:
        minutes = int(minutes)
    except (TypeError, ValueError):
        return None
    limit = max(120, int(threshold or DEFAULT_WAIT_THRESHOLD))
    if minutes >= 180:
        level = "high"
    elif minutes >= limit:
        level = "action"
    else:
        level = "info"
    return _build("delay", level)


def classify_issue(category=None, severity=None, *, label=None, minutes=None, wait_threshold=None):
    """Return a display classification for an operational issue.

    Resolution order:
      1. Known/keyword category mapping (authoritative for routing + level).
      2. Otherwise, if ``minutes`` is supplied, score as a timed wait.
      3. Otherwise, fall back to the raw ``severity`` string.

    Delay-category items with ``minutes`` are always scored by elapsed time.
    Routine categories (data check / delay / document) are capped below
    High/Critical so they can never render as an emergency.

    Returns a dict: ``{level, level_label, level_rank, level_class,
    category, category_label}``.
    """
    mapping = _lookup(category, label)
    if mapping:
        cat_key, level = mapping
    elif minutes is not None:
        return classify_wait(minutes, wait_threshold)
    else:
        cat_key = DEFAULT_CATEGORY
        level = _SEVERITY_FALLBACK.get(_norm(severity), DEFAULT_LEVEL)

    if cat_key == "delay" and minutes is not None:
        wait = classify_wait(minutes, wait_threshold)
        if wait:
            return wait

    return _build(cat_key, _cap_level(cat_key, level))


def severity_level(severity):
    """Map a raw stored severity string to a display level key."""
    return _SEVERITY_FALLBACK.get(_norm(severity), DEFAULT_LEVEL)
