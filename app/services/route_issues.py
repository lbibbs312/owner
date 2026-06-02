"""Centralized route/stop issue derivation.

The board and route surfaces must never render a bare "RISK" pill. Every
red/amber state has to come from an explicit, data-backed reason. This module
turns the raw semantic flags already produced by
:func:`app.services.route_map._detail_flags` (plus stop state such as wait time,
damage, and unconfirmed drops) into structured *issue objects* that the UI
renders directly.

Issue object shape (item 2 of the spec)::

    {
        "code": "unconfirmed_drop",          # stable machine code
        "label": "UNCONFIRMED DROP",         # shown on the pill
        "severity": "risk",                  # ok | info | attention | risk
        "reason": "A load left the truck ...",  # shown to driver/manager
        "action": "Confirm delivered here",  # what to do next
        "evidence": {...},                   # fields used to derive it
        "resolved": False,                   # unresolved by default
    }

Severity drives colour: ``risk`` -> red, ``attention`` -> amber, ``info`` ->
blue, and ``ok`` -> green.
A pill is only green when there are **no** issues.
"""

# severity ranks for picking the worst issue. ok < info < attention < risk
_SEVERITY_RANK = {"ok": 0, "info": 1, "attention": 2, "risk": 3}

# code -> (label, severity, reason, action)
ISSUE_CATALOG = {
    "damage": (
        "DAMAGE", "risk",
        "Damage was reported against this load.",
        "Add damage report / photo",
    ),
    "missing_proof": (
        "MISSING PROOF", "risk",
        "A drop or delivery has no photo, scan, or driver confirmation attached.",
        "Add proof photo",
    ),
    "destination_mismatch": (
        "DEST MISMATCH", "risk",
        "The load destination does not match where it was dropped.",
        "Confirm destination",
    ),
    "unconfirmed_drop": (
        "UNCONFIRMED DROP", "risk",
        "A load left the truck here, but the drop is not confirmed with proof.",
        "Confirm delivered here",
    ),
    "count_short": (
        "COUNT SHORT", "risk",
        "The scanned or unracked count is short of what was staged.",
        "Recount / scan",
    ),
    "hold": (
        "HOLD", "attention",
        "This stop is on hold and is waiting on a decision.",
        "Review hold",
    ),
    "needs_departure": (
        "NEEDS DEPARTURE", "attention",
        "Arrived at the stop but the departure has not been recorded.",
        "Record departure",
    ),
    "review_requested": (
        "IN REVIEW", "attention",
        "Sent to a manager for review; awaiting their decision.",
        "Awaiting manager",
    ),
}

# raw flag string (from route_map._detail_flags / RISK_FLAGS) -> issue code.
# Flags with no mapping here (No pickup, Scrap, Maintenance, Fuel, Meeting) are
# legitimate states, not issues, and never create a red/amber pill.
FLAG_TO_CODE = {
    "Damage": "damage",
    "Missing proof": "missing_proof",
    "Mismatch": "destination_mismatch",
    "Needs review": "unconfirmed_drop",
    "Shortage": "count_short",
    "Hold": "hold",
    "Delay": "needs_departure",
}

# Driver-facing pill text must stay explicit. The issue drawer carries the
# longer reason/evidence, but the row itself should never show mystery tokens
# such as "DROP?", "PROOF", or "ROUTE?".
SHORT_LABEL = {
    "damage": "DAMAGE",
    "missing_proof": "MISSING PROOF",
    "destination_mismatch": "DEST MISMATCH",
    "unconfirmed_drop": "UNCONFIRMED DROP",
    "count_short": "COUNT SHORT",
    "hold": "HOLD",
    "needs_departure": "NEEDS DEPARTURE",
    "review_requested": "IN REVIEW",
}


def issue(code, *, reason=None, action=None, evidence=None, resolved=False):
    """Build one structured issue object from a catalog ``code``."""
    label, severity, default_reason, default_action = ISSUE_CATALOG[code]
    return {
        "code": code,
        "label": label,
        "severity": severity,
        "reason": reason or default_reason,
        "action": action or default_action,
        "evidence": dict(evidence or {}),
        "resolved": bool(resolved),
    }


def derive_issues(
    flags=(),
    *,
    has_damage=False,
    departed=True,
    wait_minutes=None,
    wait_threshold=30,
    unconfirmed_drop=False,
    destination_mismatch=False,
    missing_proof=False,
    needs_departure=False,
    review_requested=False,
    evidence=None,
    extra_codes=(),
):
    """Return an ordered, de-duplicated list of structured issue objects.

    ``flags`` are the raw strings already attached to a stop/narrative. The
    keyword signals (``has_damage``, ``unconfirmed_drop``, ...) let callers add
    issues derived from real route data (cargo reconciliation, scans, proof)
    that are not encoded as a flag string.
    """
    evidence = dict(evidence or {})
    codes = []

    if has_damage:
        codes.append("damage")
    if missing_proof:
        codes.append("missing_proof")
    if destination_mismatch:
        codes.append("destination_mismatch")
    if unconfirmed_drop:
        codes.append("unconfirmed_drop")
    if needs_departure:
        codes.append("needs_departure")
    if review_requested:
        codes.append("review_requested")

    for flag in flags or ():
        code = FLAG_TO_CODE.get(flag)
        if code:
            codes.append(code)

    # A stop that is still open and has been waiting too long needs a departure.
    if (
        not departed
        and wait_minutes is not None
        and wait_minutes >= wait_threshold
    ):
        codes.append("needs_departure")

    codes.extend(code for code in extra_codes if code in ISSUE_CATALOG)

    ordered = []
    for code in codes:
        if code not in ordered:
            ordered.append(code)
    return [issue(code, evidence=evidence) for code in ordered]


def primary_issue(issues):
    """Return the single worst (highest-severity) issue, or ``None``."""
    if not issues:
        return None
    return max(issues, key=lambda item: _SEVERITY_RANK.get(item.get("severity"), 0))


def overall_severity(issues):
    """Return ``risk`` / ``attention`` / ``info`` / ``ok`` for issues."""
    worst = primary_issue(issues)
    return worst["severity"] if worst else "ok"


def status_pill(issues, *, ok_label, ok_tone="recorded"):
    """Resolve the pill ``(label, tone)`` for a row.

    ``tone`` maps to the template's status classes:
    ``needs_review`` (red) for risk, ``hold`` (amber) for attention, and the
    caller-supplied ``ok_tone`` (e.g. RECORDED/CLOSED/OPEN/EMPTY) when clean.
    """
    worst = primary_issue(issues)
    if worst is None:
        return ok_label, ok_tone
    return worst["label"], ("risk" if worst["severity"] == "risk" else "attention")


def board_badge(
    issues,
    *,
    ok_label,
    ok_pill_tone="recorded",
    ok_row_tone="completed",
    ok_short=None,
    ok_severity="ok",
):
    """Resolve the pill + row badge. ``short`` is the compact pill text; the full
    ``label`` and reason live in the issue drawer. An issue is never green."""
    if any(i.get("code") == "review_requested" for i in issues):
        return {"label": "IN REVIEW", "short": "IN REVIEW", "pill_tone": "review", "row_tone": "hot", "severity": "attention"}
    worst = primary_issue(issues)
    if worst is None:
        return {"label": ok_label, "short": ok_short or ok_label, "pill_tone": ok_pill_tone, "row_tone": ok_row_tone, "severity": ok_severity}
    short = SHORT_LABEL.get(worst["code"], worst["label"])
    if worst["severity"] == "risk":
        return {"label": worst["label"], "short": short, "pill_tone": "risk", "row_tone": "blocked", "severity": "risk"}
    return {"label": worst["label"], "short": short, "pill_tone": "attention", "row_tone": "hot", "severity": "attention"}
