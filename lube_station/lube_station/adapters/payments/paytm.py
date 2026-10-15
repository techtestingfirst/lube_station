"""Live PayTM adapter over the Frappe Payments app + paytmchecksum.

Sandbox by default: Paytm Settings carries merchant_id, merchant_key
(Password) and the staging flag. Checkout goes through the Payments-app
paytm_checkout page (get_payment_url writes the Integration Request and
returns its URL). Checksum verification is local via paytmchecksum; capture
confirmation arrives on the Payments-app verify_transaction callback, which
finalizes through Integration Request -> Hosting Invoice.on_payment_authorized.
No live traffic happens without configured keys (manual gate).
"""

import frappe

from .base import PaymentGatewayAdapter


def _settings():
    if not frappe.db.exists("DocType", "Paytm Settings") or not frappe.db.exists(
        "Paytm Settings", "Paytm Settings"
    ):
        frappe.throw("PayTM not configured: create Paytm Settings with Merchant ID/Key first")
    settings = frappe.get_doc("Paytm Settings", "Paytm Settings")
    if not settings.get("merchant_id"):
        frappe.throw("PayTM not configured: set Merchant ID/Key in Paytm Settings first")
    if not settings.get_password(fieldname="merchant_key", raise_exception=False):
        frappe.throw("PayTM not configured: set Merchant Key first")
    return settings


def _site_path(url: str) -> str:
    from lube_station.lube_station.payments.links import _site_path as site_path

    return site_path(url)


class PaytmAdapter(PaymentGatewayAdapter):
    adapter_name = "PayTM"

    def create_payment(self, invoice):
        settings = _settings()
        settings.validate_transaction_currency("INR")
        inv = frappe.get_doc("Hosting Invoice", invoice) if isinstance(invoice, str) else invoice
        if inv.status == "Paid":
            frappe.throw("Invoice already paid")
        customer = frappe.get_doc("Hosting Customer", inv.customer)
        user_email = frappe.db.get_value("User", customer.user, "email") or customer.user
        payer_name = frappe.db.get_value("User", customer.user, "full_name") or user_email
        url = settings.get_payment_url(
            amount=inv.total_due,
            title=f"Hosting Invoice {inv.name}",
            description=f"Payment for {inv.name}",
            reference_doctype="Hosting Invoice",
            reference_docname=inv.name,
            payer_email=user_email,
            payer_name=payer_name,
            order_id=inv.name,
            currency="INR",
            payment_gateway="Paytm",
        )
        return {"gateway": "PayTM", "invoice": inv.name, "url": _site_path(url), "amount": inv.total_due}

    def verify_payment(self, payload):
        try:
            from paytmchecksum import verifySignature
        except ImportError:
            frappe.throw("paytmchecksum library not installed")
        settings = _settings()
        data = dict(payload or {})
        order_id = data.get("ORDERID") or data.get("ORDER_ID") or data.get("order_id") or ""
        checksum = data.pop("CHECKSUMHASH", None) or data.pop("CHECKSUM", None)
        if not order_id or not checksum:
            frappe.throw("PayTM payload needs ORDERID and CHECKSUMHASH", frappe.ValidationError)
        merchant_key = settings.get_password(fieldname="merchant_key", raise_exception=False)
        try:
            verified = bool(verifySignature(data, merchant_key, checksum))
        except Exception:
            verified = False
        return {"verified": verified, "gateway_reference": order_id}

    def handle_webhook(self, payload, headers):
        data = dict(payload or {})
        order_id = data.get("ORDERID") or data.get("ORDER_ID") or ""
        if not order_id:
            frappe.throw("PayTM callback missing ORDERID", frappe.ValidationError)
        invoice = frappe.db.get_value("Integration Request", order_id, "reference_docname") or ""
        if invoice:
            ref_doctype = frappe.db.get_value("Integration Request", order_id, "reference_doctype")
            if ref_doctype and ref_doctype != "Hosting Invoice":
                invoice = ""
        result = self.verify_payment(dict(payload or {}))
        ok = bool(result.get("verified")) and str(data.get("RESPCODE")) == "01"
        return {
            "event_id": str(data.get("TXNID") or order_id),
            "type": "payments.confirmed" if ok else "payments.failed",
            "invoice": invoice,
            "verified": bool(result.get("verified")),
        }

    def refund_payment(self, transaction, amount=None):
        return {"refunded": transaction, "amount": amount, "manual": True}

    def create_payment_method(self, customer, token):
        frappe.throw("PayTM supports no tokenization in the checkout flow")

    def charge_saved_method(self, payment_method, invoice):
        frappe.throw("PayTM supports no auto-charge")
