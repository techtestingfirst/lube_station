import json

import frappe

from lube_station.lube_station.adapters.utils import idempotency_key, redact, verify_signature


def _secret_for(gateway: str) -> str | None:
    return (frappe.conf.get("webhook_secrets") or {}).get(gateway)


def _mark_paid(invoice: str):
    inv = frappe.get_doc("Hosting Invoice", invoice)
    if inv.status != "Paid":
        inv.status = "Paid"
        inv.save(ignore_permissions=True)
    try:
        from lube_station.lube_billing.doctype.hosting_invoice.hosting_invoice import _fulfill_order

        _fulfill_order(inv)
    except Exception:
        _unsuspend_services(inv)


def _unsuspend_services(inv):
    try:
        from lube_station.lube_provisioning.doctype.service.service import on_invoice_paid

        on_invoice_paid(inv.name)
    except Exception:
        return


@frappe.whitelist(methods=["POST"], allow_guest=True)
def handle_webhook(gateway: str, payload: dict | str, signature: str | None = None, headers: dict | None = None) -> dict:
    if isinstance(payload, str):
        payload = json.loads(payload)
    secret = _secret_for(gateway)
    if secret and signature:
        if not verify_signature(secret, json.dumps(payload).encode(), signature):
            frappe.throw("Bad webhook signature", frappe.PermissionError)
    txn_id = str(payload.get("gateway_reference") or payload.get("id") or "")
    event_id = str(payload.get("event_id") or payload.get("event") or "")
    invoice = payload.get("invoice")
    if not invoice:
        frappe.throw("Webhook missing invoice")
    key = idempotency_key(gateway, txn_id, event_id)
    existing = frappe.db.get_value("Payment Transaction", {"gateway": gateway, "gateway_txn_id": txn_id, "event_id": event_id}, "name") if txn_id else None
    if existing:
        return {"transaction": existing, "reused": True, "key": key}
    status = "Success" if payload.get("status") in ("paid", "succeeded", "success", "completed", True) else "Failed"
    txn = frappe.get_doc(
        {
            "doctype": "Payment Transaction",
            "invoice": invoice,
            "gateway": gateway,
            "gateway_txn_id": txn_id,
            "event_id": event_id,
            "amount": payload.get("amount") or 0,
            "status": status,
            "raw_response": json.dumps(redact(payload)),
        }
    ).insert(ignore_permissions=True)
    if status == "Success":
        _mark_paid(invoice)
    else:
        try:
            from lube_station.lube_billing.doctype.hosting_invoice.hosting_invoice import notify_payment_failed

            notify_payment_failed(invoice, f"{gateway} webhook {event_id or txn_id}")
        except Exception:
            pass
    return {"transaction": txn.name, "reused": False, "key": key}
