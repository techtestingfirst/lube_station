"""Live Braintree adapter over the Frappe Payments app + braintree SDK.

Sandbox by default: the Braintree Settings row carries merchant_id,
public_key, private_key (Password) and use_sandbox. Checkout goes through
the Payments-app braintree_checkout page (Drop-in nonce flow;
get_payment_url only builds the URL, no network). Verify, refund and
vaulted charges call the braintree SDK directly and need live credentials.
No live traffic happens without configured keys (manual gate).
"""

import frappe

from .base import PaymentGatewayAdapter


def _settings():
    if not frappe.db.exists("DocType", "Braintree Settings"):
        frappe.throw("Braintree not configured: create Braintree Settings with keys first")
    settings = None
    for row in frappe.get_all("Braintree Settings", ["name"]):
        doc = frappe.get_doc("Braintree Settings", row.name)
        if doc.get("merchant_id"):
            settings = doc
            break
    if settings is None:
        frappe.throw("Braintree not configured: set Merchant ID/keys in Braintree Settings first")
    if not settings.get_password(fieldname="private_key", raise_exception=False):
        frappe.throw("Braintree not configured: set the Private key first")
    return settings


def _site_path(url: str) -> str:
    from lube_station.lube_station.payments.links import _site_path as site_path

    return site_path(url)


def _client(settings):
    try:
        import braintree
    except ImportError:
        frappe.throw("braintree library not installed")
    settings.configure_braintree()
    return braintree


class BraintreeAdapter(PaymentGatewayAdapter):
    adapter_name = "Braintree"

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
            payment_gateway=f"Braintree-{settings.get('gateway_name')}",
        )
        return {"gateway": "Braintree", "invoice": inv.name, "url": _site_path(url), "amount": inv.total_due}

    def verify_payment(self, payload):
        braintree = _client(_settings())
        txn_id = (payload or {}).get("id") or (payload or {}).get("transaction_id") or ""
        if not txn_id:
            frappe.throw("Braintree payload needs a transaction id", frappe.ValidationError)
        txn = braintree.Transaction.find(txn_id)
        if getattr(txn, "status", "") not in ("authorized", "submitted_for_settlement", "settled", "settling"):
            frappe.throw(f"Braintree transaction not captured: {getattr(txn, 'status', '')}", frappe.ValidationError)
        return {"verified": True, "gateway_reference": txn.id}

    def handle_webhook(self, payload, headers):
        frappe.throw("Braintree confirms via the braintree_checkout page, not server webhooks")

    def refund_payment(self, transaction, amount=None):
        braintree = _client(_settings())
        txn = frappe.get_doc("Payment Transaction", transaction) if isinstance(transaction, str) else transaction
        if amount is not None:
            out = braintree.Transaction.refund(txn.gateway_txn_id, str(float(amount)))
        else:
            out = braintree.Transaction.refund(txn.gateway_txn_id)
        if not out.is_success:
            frappe.throw("Braintree refund failed", frappe.ValidationError)
        return {"refunded": transaction, "amount": amount, "refund_id": out.transaction.id}

    def create_payment_method(self, customer, token):
        # Token validity is proven at charge time (charge_saved_method);
        # persisting the reference here keeps this call side-effect free.
        return {"customer": customer, "token": token, "provider_token": token}

    def charge_saved_method(self, payment_method, invoice):
        braintree = _client(_settings())
        method = frappe.get_doc("Saved Payment Method", payment_method)
        inv = frappe.get_doc("Hosting Invoice", invoice) if isinstance(invoice, str) else invoice
        result = braintree.Transaction.sale(
            {
                "amount": f"{float(inv.total_due):.2f}",
                "payment_method_token": method.get_password("token"),
                "options": {"submit_for_settlement": True},
            }
        )
        if not result.is_success:
            frappe.throw("Braintree charge failed", frappe.ValidationError)
        return {"charged": result.transaction.id, "invoice": inv.name}
