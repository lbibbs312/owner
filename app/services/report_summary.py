from collections import Counter


def damage_report_kind(report):
    plant = (getattr(report, "plant_name", "") or "").strip().lower()
    stage = (getattr(report, "stage", "") or "").strip().lower()
    move_reference = (getattr(report, "move_reference", "") or "").strip().lower()
    description = (getattr(report, "description", "") or "").strip().lower()
    if plant in {"other", "incident", "general"}:
        return "incident"
    if "incident" in {stage, move_reference} or "incident" in description:
        return "incident"
    return "damage"


def damage_report_counts(reports):
    return Counter(damage_report_kind(report) for report in reports or [])


def damage_report_count_label(reports):
    counts = damage_report_counts(reports)
    parts = []
    if counts.get("incident"):
        count = counts["incident"]
        parts.append(f"{count} incident report{'s' if count != 1 else ''}")
    if counts.get("damage"):
        count = counts["damage"]
        parts.append(f"{count} damage report{'s' if count != 1 else ''}")
    if not parts:
        return "No in-route damage/incidents reported"
    return ", ".join(parts) + " filed"


def damage_report_detail_label(report):
    return f"#{report.id} {damage_report_kind(report).title()} - {getattr(report, 'plant_name', '') or 'Unknown'}"
