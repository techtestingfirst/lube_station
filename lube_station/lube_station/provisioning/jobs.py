import frappe


def _adapter_for(control_panel: str | None):
    from lube_station.lube_station.adapters.registry import get_provisioning_adapter

    mapping = {"cPanel": "cPanel / WHM", "WHM": "cPanel / WHM", "Plesk": "Plesk", "DirectAdmin": "DirectAdmin"}
    name = mapping.get(control_panel or "", "cPanel / WHM")
    try:
        return get_provisioning_adapter(name)
    except Exception:
        from lube_station.lube_station.adapters.provisioning.cpanel import CpanelWhmAdapter

        return CpanelWhmAdapter()


def _once(key: str):
    if frappe.cache().get_value(f"prov:{key}"):
        return True
    if frappe.db.exists("Provider API Log", {"idempotency_key": key}):
        return True
    return False


def _log(key: str, action: str):
    frappe.cache().set_value(f"prov:{key}", 1, expires_in_sec=86400)
    provider = frappe.db.get_value("Infrastructure Provider", {"status": "Active"}, "name")
    if frappe.db.exists("DocType", "Provider API Log") and provider:
        frappe.get_doc({"doctype": "Provider API Log", "provider": provider, "action": action, "status": "Success", "idempotency_key": key}).insert(ignore_permissions=True)


def _run(service: str, action: str, arg: str | None = None, key: str | None = None):
    key = key or f"{action}:{service}:{arg or ''}"
    if _once(key):
        return {"reused": True, "key": key}
    _log(key, action)
    return {"reused": False, "key": key}


def run_create(service: str, key: str | None = None):
    return _run(service, "create", key=key)


def run_suspend(service: str, key: str | None = None):
    return _run(service, "suspend", key=key)


def run_unsuspend(service: str, key: str | None = None):
    return _run(service, "unsuspend", key=key)


def run_terminate(service: str, key: str | None = None):
    return _run(service, "terminate", key=key)


def run_change_password(service: str, password: str | None = None, key: str | None = None):
    return _run(service, "change_password", key=key)


def run_change_package(service: str, new_plan: str | None = None, key: str | None = None):
    return _run(service, "change_package", arg=new_plan, key=key)
