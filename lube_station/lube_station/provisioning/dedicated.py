import frappe
from frappe.utils import add_to_date, now_datetime


def _is_staff() -> bool:
    return "System Manager" in frappe.get_roles() or frappe.session.user == "Administrator"


def _require_staff() -> None:
    if not _is_staff():
        frappe.throw("Only staff can manage dedicated inventory", frappe.PermissionError)


def _assert_dedicated_access(inventory: str) -> None:
    """Staff bypass; customers only via their assigned service. Fail closed."""
    if _is_staff():
        return
    inv = frappe.get_doc("Dedicated Server Inventory", inventory)
    svc_name = inv.get("assigned_service")
    if not svc_name or not frappe.db.exists("Service", svc_name):
        frappe.throw("Cross-customer access denied", frappe.PermissionError)
    from lube_station.lube_station.portal.guards import assert_owns

    customer = frappe.db.get_value("Service", svc_name, "customer")
    if not customer:
        frappe.throw("Cross-customer access denied", frappe.PermissionError)
    assert_owns(customer)


def _audit(action: str, key: str, provider: str | None = None):
    if frappe.db.exists("DocType", "Provider API Log") and provider:
        from lube_station.lube_station.providers.base import audit

        audit(provider, f"dedicated:{action}", key)


@frappe.whitelist(methods=["POST"])
def reserve_inventory(configuration: str, lease_key: str, lease_minutes: int = 30) -> dict:
    _require_staff()
    cfg = frappe.get_doc("Dedicated Server Configuration", configuration)
    filters = {"status": "Available"}
    if cfg.location:
        filters["location"] = cfg.location
    candidates = frappe.get_all("Dedicated Server Inventory", filters=filters, fields=["name"])
    if not candidates:
        frappe.throw("No compatible inventory")
    inv = frappe.get_doc("Dedicated Server Inventory", candidates[0].name)
    inv.status = "Reserved"
    inv.lease_key = lease_key
    inv.lease_expiry = add_to_date(now_datetime(), minutes=lease_minutes)
    inv.save(ignore_permissions=True)
    _audit("reserve", lease_key, inv.provider)
    return {"inventory": inv.name}


@frappe.whitelist(methods=["POST"])
def assign_manual(inventory: str, service_ref: str) -> dict:
    _require_staff()
    inv = frappe.get_doc("Dedicated Server Inventory", inventory)
    if inv.status not in ("Available", "Reserved"):
        frappe.throw(f"Cannot assign from {inv.status}")
    inv.status = "Assigned"
    inv.assigned_service = service_ref
    inv.save(ignore_permissions=True)
    _audit("assign", f"assign:{inventory}:{service_ref}", inv.provider)
    return {"inventory": inv.name, "status": inv.status}


@frappe.whitelist(methods=["POST"])
def provision_step(inventory: str, step: str) -> dict:
    allowed = {"install_os", "rescue", "network", "rdns", "panel", "monitoring", "credentials"}
    if step not in allowed:
        frappe.throw("Unknown step")
    _assert_dedicated_access(inventory)
    inv = frappe.get_doc("Dedicated Server Inventory", inventory)
    if step == "credentials":
        return {"delivery": "portal-vault", "note": "No plain-email credentials"}
    _audit(step, f"{step}:{inventory}", inv.provider)
    return {"inventory": inventory, "step": step, "queued": True}


@frappe.whitelist(methods=["POST"])
def release_inventory(inventory: str, wipe_confirmed: bool = False) -> dict:
    _require_staff()
    inv = frappe.get_doc("Dedicated Server Inventory", inventory)
    if not wipe_confirmed:
        inv.status = "Wipe Pending"
        inv.save(ignore_permissions=True)
        return {"inventory": inv.name, "status": inv.status}
    inv.status = "Available"
    inv.assigned_service = ""
    inv.lease_key = ""
    inv.save(ignore_permissions=True)
    _audit("release", f"release:{inventory}", inv.provider)
    return {"inventory": inv.name, "status": inv.status}
