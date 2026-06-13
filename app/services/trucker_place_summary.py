"""Build a compact, driver-focused "Driver notes" summary for a destination.

Google does not hand us clean trucker fields (parking, docks, backing room),
so we synthesize MoveDefense note fields from whatever official data is
available, in priority order:

  1. Our own saved driver/company notes for the place (``known_place_notes``).
  2. Official Google Place Details fields (parkingOptions, opening hours,
     business status).
  3. Google reviews / reviewSummary  (only when ENABLE_GOOGLE_REVIEW_SUMMARY).
  4. Google generativeSummary        (only when ENABLE_GOOGLE_GENERATIVE_SUMMARY).

The service never hallucinates: a note is only filled when the source text
actually contains the trucker-relevant signal. When nothing is found the note
stays ``None`` and the UI shows "No note yet".
"""
from __future__ import annotations

import datetime
import re

NOTE_KEYS = (
    "parking_note",
    "dock_note",
    "entrance_note",
    "backing_note",
    "loading_speed_note",
    "unloading_speed_note",
    "overnight_parking_note",
    "hours_note",
)

_CONFIDENCE = {
    "known_place_notes": 95,
    "google_place_details": 60,
    "google_reviews": 40,
    "google_ai_summary": 35,
    "none": 0,
}

# Each (pattern, [note_keys]) — when the pattern is found in a sentence, that
# sentence becomes the note for every listed key that is still empty. Ordered
# most-specific first so "overnight parking" wins over plain "parking".
_TEXT_PATTERNS = [
    (re.compile(r"overnight parking|park overnight|parking overnight|stay overnight|park for the night", re.I),
     ["overnight_parking_note", "parking_note"]),
    (re.compile(r"room to maneuver|easy to back|plenty of room|lots of room|big yard|big lot", re.I),
     ["backing_note"]),
    (re.compile(r"\btight\b|blind ?side|hard to back|tough to back|difficult to back|back in", re.I),
     ["backing_note"]),
    (re.compile(r"loading dock|\bdocks?\b|dock high|receiving|shipping office|appointment|lumper|\bpallet", re.I),
     ["dock_note"]),
    (re.compile(r"guard shack|security gate|gated|guarded|\bgate\b|guard|check ?in", re.I),
     ["entrance_note"]),
    (re.compile(r"\bentrance\b|\bentry\b|driveway|hard to find|easy to find", re.I),
     ["entrance_note"]),
    (re.compile(r"fast unload|quick unload|unloaded (?:fast|quick(?:ly)?)|in and out|quick turn", re.I),
     ["unloading_speed_note"]),
    (re.compile(r"slow unload|slow to unload|long wait|waited (?:hours|forever)|took (?:hours|forever)|slow", re.I),
     ["unloading_speed_note"]),
    (re.compile(r"fast load|quick load|loaded (?:fast|quick(?:ly)?)", re.I),
     ["loading_speed_note"]),
    (re.compile(r"\bstaging\b|truck parking|trailer parking|plenty of parking|no parking|nowhere to park|hard to park|\bparking\b",
                re.I),
     ["parking_note"]),
]

_MAX_NOTE_LEN = 110


def _clean(value):
    return " ".join((value or "").strip().split())


def _shorten(text):
    text = _clean(text)
    if len(text) <= _MAX_NOTE_LEN:
        return text
    return text[: _MAX_NOTE_LEN - 1].rstrip() + "…"


def _sentences(text):
    return [piece for piece in re.split(r"(?<=[.!?])\s+|\n+", _clean(text)) if piece.strip()]


class TruckerPlaceSummaryService:
    """Synthesize MoveDefense driver-note fields from place data."""

    def __init__(self, *, enable_reviews=False, enable_generative=False):
        self.enable_reviews = bool(enable_reviews)
        self.enable_generative = bool(enable_generative)

    # -- public API -------------------------------------------------------
    def build(self, payload):
        payload = payload or {}
        notes = {key: None for key in NOTE_KEYS}

        used_known = self._apply_known(notes, payload.get("known_place_notes"))
        used_details = self._apply_place_details(notes, payload)
        used_reviews = False
        if self.enable_reviews:
            used_reviews = self._apply_text(notes, self._review_texts(payload))
        used_ai = False
        if self.enable_generative:
            used_ai = self._apply_text(notes, self._summary_texts(payload))

        if used_known:
            source = "known_place_notes"
        elif used_details:
            source = "google_place_details"
        elif used_reviews:
            source = "google_reviews"
        elif used_ai:
            source = "google_ai_summary"
        else:
            source = "none"

        result = dict(notes)
        result["confidence"] = _CONFIDENCE[source]
        result["source"] = source
        return result

    # -- driver-facing Maps summary (natural bullets, only-if-present) -----
    def driver_summary(self, payload, *, route=None, nearby_places=None):
        """Compose a compact, Maps-style driver summary. Lines are short natural
        sentences and only appear when the data actually exists — never a grid of
        'No note yet' placeholders."""
        payload = payload or {}
        notes = self.build(payload)
        lines = []

        distance_text = ""
        route_text = ""
        if route and route.get("ok"):
            distance_text = _clean(route.get("duration_text")) or _clean(route.get("distance_text"))
            route_text = _clean(route.get("route_text"))
            if distance_text:
                lines.append(f"{distance_text} away {route_text}".strip())

        hours_summary = self._hours_summary(payload) or _clean(notes.get("hours_note"))
        if hours_summary:
            lines.append(hours_summary)

        parking = notes.get("overnight_parking_note") or notes.get("parking_note")
        if parking:
            lines.append(_clean(parking))
        dock = notes.get("backing_note") or notes.get("dock_note")
        if dock:
            lines.append(_clean(dock))
        if notes.get("entrance_note"):
            lines.append(_clean(notes["entrance_note"]))
        load_unload = notes.get("loading_speed_note") or notes.get("unloading_speed_note")
        if load_unload:
            lines.append(_clean(load_unload))

        nearby = []
        for place in (nearby_places or [])[:3]:
            name = _clean(place.get("name"))
            if not name:
                continue
            nearby.append(
                {
                    "name": name,
                    "type": _clean(place.get("type")) or "fuel nearby",
                    "distance_text": _clean(place.get("distance_text")),
                    "hints": [h for h in (place.get("hints") or []) if _clean(h)],
                }
            )
        if nearby:
            top = nearby[0]
            fuel_line = f"Fuel nearby: {top['name']}"
            if top["distance_text"]:
                fuel_line = f"{fuel_line} ({top['distance_text']})"
            lines.append(fuel_line)

        source = notes.get("source", "none")
        has_route = bool(route and route.get("ok"))
        has_maps_summary = has_route or bool(nearby)
        if has_maps_summary and source == "none":
            source = "maps_summary"
        elif has_maps_summary and source != "none":
            source = "mixed"
        confidence = notes.get("confidence", 0)
        if has_route:
            confidence = max(confidence, 50)
        if nearby:
            confidence = max(confidence, 40)

        return {
            "destination_name": _clean(payload.get("place_name")),
            "destination_address": _clean(payload.get("formatted_address")),
            "distance_text": distance_text,
            "route_text": route_text,
            "hours_summary": hours_summary,
            "driver_summary_lines": lines,
            "nearby_driver_places": nearby,
            "source": source,
            "confidence": confidence,
        }

    def _hours_summary(self, payload):
        hours = payload.get("currentOpeningHours") or payload.get("regularOpeningHours")
        if not isinstance(hours, dict):
            status = (payload.get("businessStatus") or payload.get("business_status") or "").upper()
            if status == "CLOSED_PERMANENTLY":
                return "Permanently closed"
            if status == "CLOSED_TEMPORARILY":
                return "Temporarily closed"
            return ""
        open_now = hours.get("openNow")
        descriptions = hours.get("weekdayDescriptions") or []
        today_name = datetime.date.today().strftime("%A").lower()
        today_desc = next((d for d in descriptions if _clean(d).lower().startswith(today_name)), "")
        if open_now is True:
            close = self._closing_time(today_desc)
            return f"Open today until {close}" if close else "Open now"
        if open_now is False:
            return "Closed now"
        return ""

    @staticmethod
    def _closing_time(today_desc):
        if not today_desc or "24 hours" in today_desc.lower():
            return ""
        times = re.findall(r"\d{1,2}(?::\d{2})?\s*[AP]M", today_desc, re.I)
        return times[-1].upper() if times else ""

    # -- tier 1: our own saved notes --------------------------------------
    def _apply_known(self, notes, known):
        if not isinstance(known, dict):
            return False
        used = False
        for key in NOTE_KEYS:
            value = _clean(known.get(key))
            if value:
                notes[key] = _shorten(value)
                used = True
        return used

    # -- tier 2: official Place Details fields ----------------------------
    def _apply_place_details(self, notes, payload):
        used = False
        parking = self._parking_note(payload.get("parkingOptions"))
        if parking and not notes["parking_note"]:
            notes["parking_note"] = parking
            used = True
        hours = self._hours_note(
            payload.get("currentOpeningHours"),
            payload.get("regularOpeningHours"),
            payload.get("businessStatus") or payload.get("business_status"),
        )
        if hours and not notes["hours_note"]:
            notes["hours_note"] = hours
            used = True
        return used

    @staticmethod
    def _parking_note(parking_options):
        if not isinstance(parking_options, dict):
            return None
        has_free = any(
            parking_options.get(key)
            for key in ("freeParkingLot", "freeStreetParking", "freeGarageParking")
        )
        has_paid = any(
            parking_options.get(key)
            for key in ("paidParkingLot", "paidStreetParking", "paidGarageParking")
        )
        if has_free and has_paid:
            return "Free and paid parking on site"
        if has_free:
            return "Free parking lot on site"
        if has_paid:
            return "Paid parking on site"
        return None

    @staticmethod
    def _hours_note(current_hours, regular_hours, business_status):
        status = (business_status or "").upper()
        if status == "CLOSED_PERMANENTLY":
            return "Permanently closed"
        if status == "CLOSED_TEMPORARILY":
            return "Temporarily closed"
        for hours in (current_hours, regular_hours):
            if isinstance(hours, dict) and "openNow" in hours:
                return "Open now" if hours.get("openNow") else "Closed now"
        return None

    # -- tier 3/4: free text (reviews / AI summaries) ---------------------
    def _apply_text(self, notes, texts):
        used = False
        for text in texts:
            for pattern, keys in _TEXT_PATTERNS:
                for sentence in _sentences(text):
                    if pattern.search(sentence):
                        note = _shorten(sentence)
                        for key in keys:
                            if not notes[key]:
                                notes[key] = note
                                used = True
                        break
        return used

    @staticmethod
    def _review_texts(payload):
        texts = []
        for review in payload.get("reviews") or []:
            if isinstance(review, dict):
                text = review.get("text")
                if isinstance(text, dict):
                    text = text.get("text")
                texts.append(_clean(text))
            else:
                texts.append(_clean(review))
        texts.append(_summary_text(payload.get("reviewSummary")))
        return [text for text in texts if text]

    @staticmethod
    def _summary_texts(payload):
        return [text for text in [_summary_text(payload.get("generativeSummary"))] if text]


def _summary_text(value):
    if isinstance(value, dict):
        # Places API wraps summaries as {"text": {"text": "..."}} or {"overview": {...}}
        for key in ("text", "overview", "description"):
            inner = value.get(key)
            if isinstance(inner, dict):
                return _clean(inner.get("text"))
            if isinstance(inner, str):
                return _clean(inner)
        return ""
    return _clean(value)
