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
