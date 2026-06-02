"""Hardcoded plant address lookup.

This dict is read-only data injected into every template via a Flask
context_processor (see ``register_context_processors`` below). It will be
replaced by the multi-tenant Facility table in PR-7 — at that point this file
goes away and the context processor sources its data from the database scoped
to the current tenant. Until then, this is the single source of truth for
plant addresses across the app.
"""
PLANT_LABELS = {
    "RE": "Raleigh East",
    "RW": "Raleigh West",
    "PC": "Paint Central",
    "PW": "Paint West",
    "KP": "Kraft Plater",
    "PPL": "PPL",
    "DC": "52nd Street DC",
    "Helios": "Helios",
    "BP": "Barden Plant",
    "52L": "52nd Street DC",
    "Trim DC": "Trim DC",
    "52DC": "52nd Street DC",
    "ALN": "Airlane North",
    "AWE": "Airlane West",
    "CORP": "Corporate",
    "R&D": "R&D",
    "GLA": "GLA",
    "KM": "Kraft Main",
    "KS": "Kraft South",
    "MONROE": "Monroe",
    "Ryder Rentals": "Ryder Rentals",
    "Other": "Other",
    "Lab": "Quality Hold",
    "Quality Hold": "Quality Hold",
    "PPM": "PPM Monroe",
}

UNKNOWN_PLANT_LABEL = "Unknown plant / needs confirmation"
UNKNOWN_LOAD_LABEL = "Unknown destination load / needs confirmation"
AMBIGUOUS_PLANT_TOKENS = {"PE", "Paint East"}
_AMBIGUOUS_PLANT_KEYS = {" ".join(token.strip().lower().split()) for token in AMBIGUOUS_PLANT_TOKENS}


def _norm(value):
    return " ".join((value or "").strip().lower().split())


def is_ambiguous_plant(value):
    """Return true for legacy/non-canonical plant names that must not be invented."""
    return _norm(value) in _AMBIGUOUS_PLANT_KEYS


def plant_label(value):
    """Return the display name for a plant code, falling back to the code itself."""
    value = (value or "").strip()
    if is_ambiguous_plant(value):
        return UNKNOWN_PLANT_LABEL
    return PLANT_LABELS.get(value, value)


PLANT_ADDRESSES = {
    "RE": "3505 Kraft Ave SE",
    "RW": "3500 Raleigh Dr SE",
    "PC": "4315 52nd st se",
    "PW": "4245 52nd st",
    "KP": "5711 North Kraft SE",
    "PPL": "5357 52nd St SE",
    "DC": "5357 52nd st se",
    "Helios": "5333 33rd st se",
    "BP": "4080 Barden Dr SE",
    "52L": "4365 52nd St SE",
    "Trim DC": "5357 52nd St SE",
    "52DC": "4365 52nd St SE",
    "ALN": "4260 Airlane Dr SE",
    "AWE": "4261 Airlane Dr SE",
    "CORP": "5460 Cascade Rd SE",
    "R&D": "4975 Broadmoor Ave SE",
    "GLA": "17113 Applewhite Road",
    "KM": "5801 Kraft Ave SE",
    "KS": "5675 Kraft Ave SE",
    "MONROE": "1648 Monroe Ave NW",
    "Ryder Rentals": "Ryder Rentals",
    "Other": "Unspecified location",
    "Lab": "Corporate Lab (placeholder)",
    "Quality Hold": "Quality hold area",
    "PPM": "PPM MONROE(1648 monroe ave)",
}


def register_context_processors(app):
    @app.context_processor
    def inject_plant_addresses():
        return dict(PLANT_ADDRESSES=PLANT_ADDRESSES, PLANT_LABELS=PLANT_LABELS)
