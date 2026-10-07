"""Live Stripe adapter over the ``stripe`` SDK + Stripe Settings.

Sandbox by default: secret key comes from the Stripe Settings row
(secret_key Password field). Webhook signature is verified when the Settings
row carries a webhook secret, otherwise the envelope is parsed and flagged
unverified. No live traffic happens without configured keys (manual gate).
"""

import frappe

from .base import PaymentGatewayAdapter


def _settings():
    rows = frappe.get_all("Stripe Settings", ["name"])
    settings = None
    for row in rows:
        doc = frappe.get_doc("Stripe Settings", row.name)
        if doc.get("publishable_key"):
            settings = doc
            break
    if settings is None:
        frappe.throw("Stripe not configured: create Stripe Settings with Publishable/Secret keys first")
    if not settings.get_password(fieldname="secret_key", raise_exception=False):
        frappe.throw("Stripe not configured: set the Secret key first")
    return settings


def _paise(amount) -> int:
    return int(round(float(amount or 0) * 100))


class StripeAdapter(PaymentGatewayAdapter):
    adapter_name = "Stripe"

    def _client(self):
        try:
            import stripe
        except ImportError:
            frappe.throw("Stripe library not installed")
        settings = _settings()
        stripe.api_key = settings.get_password(fieldname="secret_key", raise_exception=False)
        return stripe, settings

    def create_payment(self, invoice):
        stripe, _ = self._client()
        inv = frappe.get_doc("Hosting Invoice", invoice) if isinstance(invoice, str) else invoice
        intent = stripe.PaymentIntent.create(
            {
                "amount": _paise(inv.total_due),
                "currency": "inr",
                "description": f"Hosting Invoice {inv.name}",
                "metadata": {"invoice": inv.name},
            }
        )
        return {"gateway": "Stripe", "invoice": inv.name, "payment_intent": intent.get("id")}

    def verify_payment(self, payload):
        stripe, _ = self._client()
        intent = stripe.PaymentIntent.retrieve(payload.get("id") or payload.get("payment_intent"))
        if intent.get("status") != "succeeded":
            frappe.throw(f"Stripe payment not captured: {intent.get('status')}", frappe.ValidationError)
        return {"verified": True, "gateway_reference": intent.get("id")}

    def handle_webhook(self, payload, headers):
        stripe, settings = self._client()
        secret = (settings.get("webhook_secret") or "") if hasattr(settings, "get") else ""
        raw = (payload or {}).get("_raw_body")
        signature = (headers or {}).get("Stripe-Signature", "")
        if raw and secret:
            event = stripe.Webhook.construct_event(raw, signature, secret)
            return {"event_id": event.get("id"), "type": event.get("type"), "verified": True}
        return {
            "event_id": (payload or {}).get("id"),
            "type": (payload or {}).get("type"),
            "verified": False,
        }

    def refund_payment(self, transaction, amount=None):
        stripe, _ = self._client()
        txn = frappe.get_doc("Payment Transaction", transaction) if isinstance(transaction, str) else transaction
        data = {"payment_intent": txn.gateway_txn_id}
        if amount is not None:
            data["amount"] = _paise(amount)
        out = stripe.Refund.create(data)
        return {"refunded": transaction, "amount": amount, "refund_id": out.get("id")}

    def create_payment_method(self, customer, token):
        stripe, _ = self._client()
        method = stripe.PaymentMethod.retrieve(token)
        return {
            "customer": customer,
            "token": token,
            "provider_token": method.get("id", token),
            "redacted": {"token": "***"},
        }

    def charge_saved_method(self, payment_method, invoice):
        stripe, _ = self._client()
        method = frappe.get_doc("Saved Payment Method", payment_method)
        inv = frappe.get_doc("Hosting Invoice", invoice) if isinstance(invoice, str) else invoice
        params = {
            "amount": _paise(inv.total_due),
            "currency": "inr",
            "payment_method": method.get_password("token"),
            "off_session": True,
            "confirm": True,
            "description": f"Invoice {inv.name}",
            "metadata": {"invoice": inv.name},
        }
        if method.get("provider_customer"):
            params["customer"] = method.get("provider_customer")
        intent = stripe.PaymentIntent.create(params)
        if intent.get("status") not in ("succeeded", "requires_capture"):
            frappe.throw(f"Stripe charge failed: {intent.get('status')}", frappe.ValidationError)
        return {"charged": intent.get("id"), "invoice": inv.name}
