"""Server-side Razorpay reconciliation.

The Razorpay modal handler sometimes never calls back (UPI redirect flows,
closed modal after paying in the UPI app). This endpoint polls Razorpay for
payments against our order ids and completes the invoice when money landed.
"""

import json

import frappe


def _order_ids_for(invoice: str) -> list:
    order_ids = []
    rows = frappe.get_all(
        "Integration Request",
        {"integration_request_service": "Razorpay"},
        ["data"],
        order_by="modified desc",
        limit=20,
    )
    for row in rows:
        try:
            logged = json.loads(row.data or "{}")
        except Exception:
            continue
        if logged.get("reference_docname") == invoice and str(logged.get("order_id") or "").startswith("order_"):
            if logged["order_id"] not in order_ids:
                order_ids.append(logged["order_id"])
    return order_ids


@frappe.whitelist(methods=["POST"])
def verify_razorpay_payment(invoice: str) -> dict:
    from lube_station.lube_station.portal.guards import assert_owns

    inv = frappe.get_doc("Hosting Invoice", invoice)
    if "System Manager" not in frappe.get_roles() and frappe.session.user != "Administrator":
        assert_owns(inv.customer)
    if inv.status == "Paid":
        return {"status": "paid", "invoice": invoice}
    order_ids = _order_ids_for(invoice)
    if not order_ids:
        return {"status": "pending", "reason": "no Razorpay order found for this invoice"}
    try:
        import razorpay
    except ImportError:
        frappe.throw("Razorpay library not installed")
    if not frappe.db.exists("Razorpay Settings", "Razorpay Settings"):
        frappe.throw("Razorpay not configured: set API Key/Secret in Razorpay Settings first")
    settings = frappe.get_doc("Razorpay Settings", "Razorpay Settings")
    client = razorpay.Client(
        auth=(settings.api_key, settings.get_password(fieldname="api_secret", raise_exception=False))
    )
    for order_id in order_ids:
        try:
            items = client.order.payments(order_id).get("items", [])
        except Exception:
            continue
        for payment in items:
            if payment.get("status") in ("captured", "authorized"):
                frappe.flags.data = {
                    "razorpay_payment_id": payment.get("id"),
                    "razorpay_order_id": order_id,
                }
                inv.reload()
                inv.on_payment_authorized("Completed")
                return {
                    "status": "paid",
                    "invoice": invoice,
                    "gateway_payment_id": payment.get("id"),
                }
    return {"status": "pending", "reason": "no captured payment found yet"}
