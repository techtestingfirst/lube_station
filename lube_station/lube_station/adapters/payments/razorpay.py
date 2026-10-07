"""Live Razorpay adapter over the ``razorpay`` SDK + Razorpay Settings.

Sandbox by default: nothing here invents endpoints. Every call goes through
the SDK resources (order/payment/refund/customer/token/utility) against the
keys in Razorpay Settings. No live traffic happens without those keys, which
only a human configures (manual gate).
"""

import frappe

from lube_station.lube_station.adapters.utils import redact

from .base import PaymentGatewayAdapter


def _settings():
    if not frappe.db.exists("DocType", "Razorpay Settings") or not frappe.db.exists(
        "Razorpay Settings", "Razorpay Settings"
    ):
        frappe.throw("Razorpay not configured: create Razorpay Settings with API keys first")
    settings = frappe.get_doc("Razorpay Settings", "Razorpay Settings")
    if not settings.api_key:
        frappe.throw("Razorpay not configured: set API Key/Secret in Razorpay Settings first")
    return settings


def _paise(amount) -> int:
    return int(round(float(amount or 0) * 100))


class RazorpayAdapter(PaymentGatewayAdapter):
    adapter_name = "Razorpay"

    def _client(self):
        try:
            import razorpay
        except ImportError:
            frappe.throw("Razorpay library not installed")
        settings = _settings()
        client = razorpay.Client(
            auth=(settings.api_key, settings.get_password(fieldname="api_secret", raise_exception=False))
        )
        return client, settings

    def create_payment(self, invoice):
        client, _ = self._client()
        inv = frappe.get_doc("Hosting Invoice", invoice) if isinstance(invoice, str) else invoice
        order = client.order.create(
            {"amount": _paise(inv.total_due), "currency": "INR", "receipt": inv.name[:40]}
        )
        return {"gateway": "Razorpay", "invoice": inv.name, "order_id": order.get("id")}

    def verify_payment(self, payload):
        client, _ = self._client()
        data = {
            "razorpay_order_id": payload.get("razorpay_order_id") or payload.get("order_id"),
            "razorpay_payment_id": payload.get("razorpay_payment_id") or payload.get("id"),
            "razorpay_signature": payload.get("razorpay_signature") or payload.get("signature"),
        }
        client.utility.verify_payment_signature(data)
        return {"verified": True, "gateway_reference": data["razorpay_payment_id"]}

    def handle_webhook(self, payload, headers):
        client, settings = self._client()
        secret = settings.get_password(fieldname="webhook_secret", raise_exception=False)
        body = payload.get("_raw_body") if isinstance(payload, dict) else None
        if body is None:
            import json

            body = json.dumps(payload or {})
        signature = (headers or {}).get("X-Razorpay-Signature", "")
        if secret:
            client.utility.verify_webhook_signature(body, signature, secret)
        return {
            "event_id": (payload or {}).get("id"),
            "type": (payload or {}).get("event"),
        }

    def refund_payment(self, transaction, amount=None):
        client, _ = self._client()
        txn = frappe.get_doc("Payment Transaction", transaction) if isinstance(transaction, str) else transaction
        data = {"payment_id": txn.gateway_txn_id}
        if amount is not None:
            data["amount"] = _paise(amount)
        out = client.refund.create(data)
        return {"refunded": transaction, "amount": amount, "refund_id": out.get("id")}

    def create_payment_method(self, customer, token):
        # Token validity is proven at charge time (charge_saved_method);
        # persisting the reference here keeps this call side-effect free.
        return {
            "customer": customer,
            "token": token,
            "provider_token": token,
            "redacted": redact({"token": token}),
        }

    def charge_saved_method(self, payment_method, invoice):
        client, _ = self._client()
        method = frappe.get_doc("Saved Payment Method", payment_method)
        inv = frappe.get_doc("Hosting Invoice", invoice) if isinstance(invoice, str) else invoice
        user_email = frappe.db.get_value("User", method.owner, "email") or method.owner
        order = client.order.create(
            {"amount": _paise(inv.total_due), "currency": "INR", "receipt": inv.name[:40]}
        )
        charged = client.payment.createRecurring(
            {
                "email": user_email,
                "contact": "",
                "amount": _paise(inv.total_due),
                "currency": "INR",
                "order_id": order.get("id"),
                "customer_id": "",
                "token": method.get_password("token"),
                "recurring": "1",
                "description": f"Invoice {inv.name}",
            }
        )
        return {"charged": charged.get("id"), "invoice": inv.name, "order_id": order.get("id")}
