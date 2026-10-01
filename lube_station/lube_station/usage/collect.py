import frappe
from frappe.utils import today


def _limits(service: str) -> dict:
    svc = frappe.get_doc("Service", service)
    cfg = frappe.db.get_value("VPS Configuration", {"hosting_plan": svc.hosting_plan}, ["storage_gb", "bandwidth_gb"])
    if cfg:
        return {"disk": cfg[0] or 0, "bandwidth": cfg[1] or 0}
    return {"disk": 0, "bandwidth": 0}


def _pull(service: str) -> dict:
    return {"disk": 0, "bandwidth": 0}


@frappe.whitelist(methods=["POST"])
def collect_usage(service: str, snap_date: str | None = None, disk: float | None = None, bandwidth: float | None = None) -> dict:
    snap_date = snap_date or today()
    if frappe.db.exists("Usage Snapshot", {"service_ref": service, "snap_date": snap_date}):
        doc = frappe.get_doc("Usage Snapshot", {"service_ref": service, "snap_date": snap_date})
        return {"snapshot": doc.name, "reused": True}
    pulled = _pull(service)
    doc = frappe.get_doc({"doctype": "Usage Snapshot", "service_ref": service, "snap_date": snap_date, "disk_used": disk if disk is not None else pulled["disk"], "bandwidth_used": bandwidth if bandwidth is not None else pulled["bandwidth"]}).insert(ignore_permissions=True)
    overage = check_overage(service, doc.name)
    if overage["overage"]:
        create_overage_invoice(service, doc.name)
    return {"snapshot": doc.name, "reused": False, **overage}


def check_overage(service: str, snapshot: str) -> dict:
    snap = frappe.get_doc("Usage Snapshot", snapshot)
    limits = _limits(service)
    disk_over = max((snap.disk_used or 0) - (limits["disk"] or 0), 0) if limits["disk"] else 0
    bw_over = max((snap.bandwidth_used or 0) - (limits["bandwidth"] or 0), 0) if limits["bandwidth"] else 0
    return {"overage": bool(disk_over or bw_over), "disk_over": disk_over, "bw_over": bw_over}


def create_overage_invoice(service: str, snapshot: str) -> dict:
    snap = frappe.get_doc("Usage Snapshot", snapshot)
    overage = check_overage(service, snapshot)
    if not overage["overage"]:
        return {"invoice": None}
    key = f"overage:{service}:{snap.snap_date}"
    if frappe.db.exists("Hosting Invoice", {"idempotency_key": key}):
        doc = frappe.get_doc("Hosting Invoice", {"idempotency_key": key})
        return {"invoice": doc.name, "reused": True}
    svc = frappe.get_doc("Service", service)
    amount = round(overage["disk_over"] * 1 + overage["bw_over"] * 1, 2)
    doc = frappe.get_doc({"doctype": "Hosting Invoice", "customer": svc.customer, "order_ref": svc.order_ref, "invoice_items": [{"description": f"Overage {snap.snap_date} disk {overage['disk_over']} bw {overage['bw_over']}", "service_ref": service, "amount": amount}], "status": "Unpaid", "idempotency_key": key}).insert(ignore_permissions=True)
    return {"invoice": doc.name, "reused": False}


def daily():
    for svc in frappe.get_all("Service", {"status": "Active"}, ["name"]):
        try:
            collect_usage(svc.name)
        except Exception:
            continue
