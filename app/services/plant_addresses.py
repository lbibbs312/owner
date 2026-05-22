"""Hardcoded plant address lookup.

This dict is read-only data injected into every template via a Flask
context_processor (see ``register_context_processors`` below). It will be
replaced by the multi-tenant Facility table in PR-7 — at that point this file
goes away and the context processor sources its data from the database scoped
to the current tenant. Until then, this is the single source of truth for
plant addresses across the app.
"""
PLANT_LABELS = {
    "P1": "Plant 1",
    "P2": "Plant 2",
    "P3": "Plant 3",
    "HQ": "Headquarters",
    "DC": "Distribution Center",
    "Other": "Other",
}


def plant_label(value):
    """Return the display name for a plant code, falling back to the code itself."""
    value = (value or "").strip()
    return PLANT_LABELS.get(value, value)


PLANT_ADDRESSES = {
    "P1": "123 Example St, City, ST 00000",
    "P2": "456 Example Ave, City, ST 00000",
    "P3": "789 Example Blvd, City, ST 00000",
    "HQ": "1 Headquarters Way, City, ST 00000",
    "DC": "Distribution Center address",
    "Other": "Unspecified location",
}


def register_context_processors(app):
    @app.context_processor
    def inject_plant_addresses():
        return dict(PLANT_ADDRESSES=PLANT_ADDRESSES, PLANT_LABELS=PLANT_LABELS)
