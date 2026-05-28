import re


_QUANTITY_RE = re.compile(r"\b(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>skids?|pallets?|crates?|racks?|boxes?|coils?|trailers?|packs?)\b", re.IGNORECASE)
_PART_RE = re.compile(r"\b(?P<part>[A-Z]{1,4}\d{2,}[A-Z0-9-]*)\b", re.IGNORECASE)
_EQUIPMENT_RE = re.compile(r"\b(?P<equipment>[A-Z]{1,4}\d{1,})\b", re.IGNORECASE)
MISSING_QUANTITY_WARNING = "Quantity not found. Confirm amount from document or driver."


def _clean(value):
    return re.sub(r"\s+", " ", str(value or "").strip(" .,;:-"))


def _number(value):
    if value is None:
        return None
    parsed = float(value)
    return int(parsed) if parsed.is_integer() else parsed


def _due_phrase(text):
    match = re.search(
        r"\b(?:(?:tonight|today|tomorrow)\s+)?at\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?\b",
        text,
        re.IGNORECASE,
    )
    if not match:
        return None
    return _clean(match.group(0)).lower()


def _suggest_quantity(suggestions, text):
    match = _QUANTITY_RE.search(text)
    if not match:
        return
    value = _number(match.group("value"))
    unit = match.group("unit").lower()
    suggestions["quantity_value"] = value
    suggestions["quantity_unit"] = unit
    suggestions["quantity_text"] = f"{value} {unit}"


def _suggest_part(suggestions, text):
    match = _PART_RE.search(text)
    if match:
        suggestions["part_number"] = match.group("part").upper()


def _parse_has_for(suggestions, text):
    match = re.search(
        r"^(?P<origin>.+?)\s+has\s+(?P<cargo>.+?)\s+for\s+(?:the\s+)?(?P<destination>.+?)(?:\s+please(?:\s+(?P<trailing>.*))?)?$",
        text,
        re.IGNORECASE,
    )
    if not match:
        return False

    cargo = _clean(match.group("cargo"))
    suggestions.update(
        {
            "request_type": "move",
            "origin_location_text": _clean(match.group("origin")),
            "destination_location_text": _clean(match.group("destination")),
        }
    )
    qty = _QUANTITY_RE.fullmatch(cargo)
    if qty:
        value = _number(qty.group("value"))
        unit = qty.group("unit").lower()
        suggestions["quantity_value"] = value
        suggestions["quantity_unit"] = unit
        suggestions["quantity_text"] = f"{value} {unit}"
    elif cargo:
        suggestions["cargo_text"] = cargo
    return True


def _parse_route_to(suggestions, text):
    match = re.search(
        r"\b(?P<origin>[A-Za-z0-9][A-Za-z0-9 /\-]*?)\s+(?:to|->)\s+(?P<destination>[A-Za-z0-9][A-Za-z0-9 /\-]*?)(?=\s+(?:hot|urgent|asap|\d+\s|please\b)|$)",
        text,
        re.IGNORECASE,
    )
    if not match:
        return False
    suggestions["request_type"] = "move"
    suggestions["origin_location_text"] = _clean(match.group("origin"))
    suggestions["destination_location_text"] = _clean(match.group("destination"))
    return True


def parse_move_request_text(raw_text):
    """Return field suggestions only; callers must explicitly save changes."""
    text = _clean(str(raw_text or "").replace("\u2019", "'").replace("\u2018", "'"))
    suggestions = {"priority": "normal"}
    warnings = []

    if not text:
        return {
            "suggestions": {},
            "confidence": "low",
            "warnings": ["No original request text was provided."],
            "unparsed_text": "",
        }

    lower = text.lower()
    confidence = "low"

    due = _due_phrase(text)
    if due:
        suggestions["due_time_text"] = due
    if re.search(r"\bhot\b", text, re.IGNORECASE):
        suggestions["priority"] = "hot"
    elif re.search(r"\bsafety|safe\b", text, re.IGNORECASE):
        suggestions["priority"] = "safety"
    elif re.search(r"\burgent|asap|immediately|shutdown\b", text, re.IGNORECASE):
        suggestions["priority"] = "high"

    if re.search(r"can't find|cannot find|can not find|no trailer|missing trailer|blocked|stuck", lower):
        suggestions["request_type"] = "blocker"
        if re.search(r"trailer", lower):
            suggestions["blocked_reason"] = "cannot find trailer"
            suggestions["notes"] = "cannot find trailer"
        else:
            suggestions["notes"] = text
        if suggestions["priority"] == "normal":
            suggestions["priority"] = "high"
        return {
            "suggestions": suggestions,
            "confidence": "high",
            "warnings": warnings,
            "unparsed_text": "",
        }

    if re.search(r"a/?c| ac ", lower) and re.search(r"doesn'?t work|does not work|not working|broken", lower):
        suggestions["request_type"] = "equipment_issue"
        equipment = _EQUIPMENT_RE.search(text)
        if equipment:
            suggestions["equipment_text"] = equipment.group("equipment").upper()
        suggestions["notes"] = "AC does not work"
        return {
            "suggestions": suggestions,
            "confidence": "high",
            "warnings": warnings,
            "unparsed_text": "",
        }
    if re.search(r"maintenance|broken|damage|doesn'?t work|does not work|not working", lower):
        suggestions["request_type"] = "equipment_issue"
        equipment = _EQUIPMENT_RE.search(text)
        if equipment:
            suggestions["equipment_text"] = equipment.group("equipment").upper()
        suggestions["notes"] = text
        confidence = "medium"

    working = re.sub(re.escape(due), "", text, flags=re.IGNORECASE).strip() if due else text
    parsed_route = _parse_has_for(suggestions, working) or _parse_route_to(suggestions, working)
    if parsed_route:
        confidence = "high"

    _suggest_quantity(suggestions, text)
    _suggest_part(suggestions, text)

    if suggestions.get("request_type") == "move" and "quantity_text" not in suggestions:
        suggestions["quantity_text"] = None
        warnings.append(MISSING_QUANTITY_WARNING)
    if suggestions.get("request_type") == "move" and not suggestions.get("destination_location_text"):
        warnings.append("Destination was not confidently parsed.")
    if "request_type" not in suggestions:
        suggestions["request_type"] = "note"
        warnings.append("Could not identify a move, blocker, or equipment issue.")

    return {
        "suggestions": suggestions,
        "confidence": confidence,
        "warnings": warnings,
        "unparsed_text": text if confidence == "low" else "",
    }
