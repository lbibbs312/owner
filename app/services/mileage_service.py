"""Mileage state rules shared by manager reports and future route services."""

DEFAULT_NORMAL_ROUTE_MILES_MAX = 1000


def calculate_mileage_record(pretrip, *, normal_max=DEFAULT_NORMAL_ROUTE_MILES_MAX):
    """Classify a route mileage record from one PreTrip/PostTrip pair.

    Rules:
    - Missing PostTrip end mileage is pending, not a correction.
    - Missing/zero beginning mileage, end before start, or out-of-range math is correction required.
    - Valid math returns OK and the calculated miles.
    """
    posttrip = getattr(pretrip, "posttrip", None)
    start_mileage = getattr(pretrip, "start_mileage", None)
    end_mileage = getattr(posttrip, "end_mileage", None) if posttrip else None
    calculated_miles = None

    if end_mileage is None:
        return {
            "start": start_mileage,
            "end": end_mileage,
            "calculated_miles": None,
            "status": "Pending",
            "detail": "Mileage pending PostTrip: PostTrip end mileage has not been recorded.",
            "blocks_approval": True,
            "blocker_label": "Mileage pending PostTrip",
            "action": "Complete PostTrip mileage before approving route.",
        }
    if start_mileage is None or start_mileage <= 0:
        return {
            "start": start_mileage,
            "end": end_mileage,
            "calculated_miles": None,
            "status": "Needs correction",
            "detail": "Beginning odometer is missing or zero; ending odometer cannot be used as route miles.",
            "blocks_approval": True,
            "blocker_label": "Mileage conflict / correction required",
            "action": "Correct route mileage before approving route.",
        }

    calculated_miles = end_mileage - start_mileage
    if calculated_miles < 0:
        return {
            "start": start_mileage,
            "end": end_mileage,
            "calculated_miles": calculated_miles,
            "status": "Needs correction",
            "detail": "Ending odometer is lower than beginning odometer.",
            "blocks_approval": True,
            "blocker_label": "Mileage conflict / correction required",
            "action": "Correct route mileage before approving route.",
        }
    if calculated_miles > normal_max:
        return {
            "start": start_mileage,
            "end": end_mileage,
            "calculated_miles": calculated_miles,
            "status": "Needs correction",
            "detail": f"{calculated_miles:,} miles is outside normal route range.",
            "blocks_approval": True,
            "blocker_label": "Mileage conflict / correction required",
            "action": "Correct route mileage before approving route.",
        }
    return {
        "start": start_mileage,
        "end": end_mileage,
        "calculated_miles": calculated_miles,
        "status": "OK",
        "detail": "Calculated from beginning and ending odometer.",
        "blocks_approval": False,
        "blocker_label": "",
        "action": "",
    }
