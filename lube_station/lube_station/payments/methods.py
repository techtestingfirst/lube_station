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
    from lube_station.lube_billing.doctype.hosting_invoice.hosting_invoice import _fulfill_order

    try:
        _fulfill_order(inv)
    except Exception:
        pass
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
        try:
            from lube_station.lube_billing.doctype.hosting_invoice.hosting_invoice import notify_payment_failed

            notify_payment_failed(invoice, str(e))
        except Exception:
            pass
        return {"action": "dunning", "reason": str(e)}


@frappe.whitelist(methods=["POST"])
def approve_bank_transfer(invoice: str) -> dict:
    """Staff-only: approve a pending bank transfer and activate services."""
    roles = set(frappe.get_roles())
    if not (roles & {"System Manager", "Billing Admin"}) and frappe.session.user != "Administrator":
        frappe.throw("Only billing staff can approve transfers", frappe.PermissionError)
    name = frappe.db.get_value(
        "Payment Transaction",
        {"gateway": "Bank Transfer", "invoice": invoice, "status": "Pending"},
        "name",
    )
    if not name:
        frappe.throw("No pending bank transfer for this invoice")
    frappe.db.set_value("Payment Transaction", name, "status", "Success")
    from lube_station.lube_station.payments.webhooks import _mark_paid

    _mark_paid(invoice)
    return {"transaction": name, "invoice": invoice, "status": "Success"}


@frappe.whitelist(methods=["POST"], allow_guest=True)
def payu_return(**kwargs) -> dict:
    """PayU hosted return: verify hash, mark paid on success."""
    from lube_station.lube_station.adapters.payments.payu import PayUIndiaAdapter
    from lube_station.lube_station.payments.webhooks import _mark_paid

    out = PayUIndiaAdapter().handle_webhook(kwargs, {})
    if str(out.get("type", "")).lower() != "success":
        return {"status": out.get("type"), "verified": True}
    inv = frappe.db.get_value("Hosting Invoice", kwargs.get("txnid"), "name")
    if inv:
        _mark_paid(inv)
    return {"status": "success", "invoice": inv, "verified": True}


@frappe.whitelist(methods=["POST"], allow_guest=True)
def ccavenue_return(**kwargs) -> dict:
    """CCAvenue hosted return: decrypt, mark paid on success."""
    from lube_station.lube_station.adapters.payments.ccavenue import CCAvenueAdapter
    from lube_station.lube_station.payments.webhooks import _mark_paid

    out = CCAvenueAdapter().handle_webhook(kwargs, {})
    inv = frappe.db.get_value("Hosting Invoice", out.get("order_id") or kwargs.get("merchant_param1"), "name")
    if inv:
        _mark_paid(inv)
    return {"status": "success", "invoice": inv, "verified": True}
