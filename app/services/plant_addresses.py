"""Hardcoded plant address lookup.

This dict is read-only data injected into every template via a Flask
context_processor (see ``register_context_processors`` below). It will be
replaced by the multi-tenant Facility table in PR-7 — at that point this file
goes away and the context processor sources its data from the database scoped
to the current tenant. Until then, this is the single source of truth for
plant addresses across the app.
"""
PLANT_ADDRESSES = {
    "RE": "3505 Kraft Ave SE",
    "RW": "3500 Raleigh Dr SE",
    "PC": "4315 52nd st se",
    "PE": "4245 52nd St SE",
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
    "Other": "Unspecified location",
    "Lab": "Corporate Lab (placeholder)",
    "PPM": "PPM MONROE(1648 monroe ave)",
}


def register_context_processors(app):
    @app.context_processor
    def inject_plant_addresses():
        return dict(PLANT_ADDRESSES=PLANT_ADDRESSES)
