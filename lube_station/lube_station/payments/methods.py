import frappe


def _gateway_supports_recurring(gateway: str) -> bool:
    return bool(frappe.db.get_value("Payment Gateway Adapter", gateway, "supports_recurring"))


@frappe.whitelist(methods=["POST"])
def charge_saved_method(payment_method: str, invoice: str) -> dict:
    from lube_station.lube_station.portal.guards import assert_owns

    method = frappe.get_doc("Saved Payment Method", payment_method)
    inv = frappe.get_doc("Hosting Invoice", invoice)
    if "System Manager" not in frappe.get_roles() and frappe.session.user != "Administrator":
        assert_owns(inv.customer)
        assert_owns(method.customer)
    if method.customer != inv.customer:
        frappe.throw("Payment method does not belong to invoice customer", frappe.PermissionError)
    if inv.status == "Paid":
        frappe.throw("Invoice already paid")
    if not _gateway_supports_recurring(method.gateway):
        frappe.throw(f"{method.gateway} lacks recurring support, falling back to dunning")
    from lube_station.lube_station.adapters.registry import get_payment_adapter

    adapter = get_payment_adapter(method.gateway)
    result = adapter.charge_saved_method(method.name, inv.name)
    txn = frappe.get_doc(
        {"doctype": "Payment Transaction", "invoice": inv.name, "gateway": method.gateway, "gateway_txn_id": str(result.get("charged") or method.name), "amount": inv.total_due, "status": "Success", "raw_response": "{}"}
    ).insert(ignore_permissions=True)
    inv.status = "Paid"
    inv.save(ignore_permissions=True)
    return {"transaction": txn.name, "invoice": inv.name}


@frappe.whitelist(methods=["POST"])
def auto_charge_invoice(invoice: str) -> dict:
    inv = frappe.get_doc("Hosting Invoice", invoice)
    method = frappe.db.get_value("Saved Payment Method", {"customer": inv.customer, "default_method": 1}, "name")
    if not method:
        return {"action": "dunning", "reason": "no saved method"}
    try:
        out = charge_saved_method(method, invoice)
        out["action"] = "charged"
        return out
    except Exception as e:
        return {"action": "dunning", "reason": str(e)}
