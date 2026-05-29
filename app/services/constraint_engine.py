"""Hard-constraint and soft-lock checker for production-flow assignments.

Validates a proposed state transition (load assignment, manifest lock,
departure) against equipment-type rules and quality holds before the caller
commits the corresponding FlowEvent.

Return shape is always ``(ok: bool, code: str | None, message: str | None)``
so callers can render a structured exception block in the UI and emit an
exception FlowEvent without re-formatting prose.
"""

from app.models.node import Node
from app.models.voyager import Voyager
from app.models.flow import FlowContainer, ContainerItem
from app.models import states


OK = (True, None, None)


def _container_part_profiles(container):
    skus = set()
    for item in getattr(container, "items", []) or []:
        if item.part_sku:
            skus.add(item.part_sku)
    for child in getattr(container, "child_containers", []) or []:
        skus.update(_container_part_profiles(child))
    return skus


def _required_equipment_for_skus(skus):
    """Lookup restricted-part transport rules from PartRouteProfile if present.

    PartRouteProfile (app/models/part.py) carries any per-SKU equipment
    restriction. Falls back to no restriction when the table is empty.
    """
    try:
        from app.models.part import PartRouteProfile
    except Exception:
        return None
    if not skus:
        return None
    profiles = PartRouteProfile.query.filter(PartRouteProfile.part_sku.in_(skus)).all()
    required = set()
    for profile in profiles:
        meta = profile.metadata_json or {}
        required_type = meta.get("required_equipment_type")
        if required_type:
            required.add(required_type)
    return required or None


def validate_load_assignment(container, voyager):
    if container is None or voyager is None:
        return False, "missing_entity", "Container and voyager are both required."

    if states.is_soft_locked(container.current_status):
        return (
            False,
            "container_soft_locked",
            f"Container {container.identifier} is on {states.STATE_LABELS.get(container.current_status, container.current_status)}. Supervisor bypass required.",
        )

    skus = _container_part_profiles(container)
    required = _required_equipment_for_skus(skus)
    if required and voyager.equipment_type not in required:
        required_label = ", ".join(sorted(required))
        return (
            False,
            "equipment_mismatch",
            f"Asset Mismatch: this part profile requires {required_label} layout, got {voyager.equipment_type}.",
        )

    return OK


def validate_node_dock(node, voyager):
    if node is None or voyager is None:
        return False, "missing_entity", "Node and voyager are both required."
    if not node.allows(voyager.equipment_type):
        allowed = ", ".join(node.allowed_equipment_types or []) or "(none configured)"
        return (
            False,
            "node_equipment_disallowed",
            f"Node {node.label} only accepts {allowed}. {voyager.equipment_type} blocked.",
        )
    return OK


def validate_manifest_lock(manifest):
    if manifest is None:
        return False, "missing_entity", "Manifest is required."
    for line in manifest.lines or []:
        container = line.container
        if container is None:
            continue
        if states.is_soft_locked(container.current_status):
            return (
                False,
                "manifest_contains_soft_lock",
                f"Manifest blocked: container {container.identifier} is on {states.STATE_LABELS.get(container.current_status, container.current_status)}.",
            )
    return OK


def validate_departure(manifest, voyager):
    ok, code, msg = validate_manifest_lock(manifest)
    if not ok:
        return ok, code, msg
    if voyager and states.is_soft_locked(voyager.current_status):
        return (
            False,
            "voyager_soft_locked",
            f"Voyager {voyager.equipment_id} is on {voyager.current_status}. Cannot depart.",
        )
    return OK


def find_node(node_key):
    if not node_key:
        return None
    return Node.query.filter_by(key=node_key).first()


def find_voyager(equipment_id):
    if not equipment_id:
        return None
    return Voyager.query.filter_by(equipment_id=equipment_id).first()
