"""Live Mollie adapter (API v2, Bearer secret key).

Sandbox is key-driven (test_ vs live_ prefix, single endpoint). Shapes per
Mollie v2 docs: payment create returns a hosted checkout URL, webhooks carry
only the payment id (no signature — re-fetch to verify), refunds per
payment, recurring charges via customerId + optional mandateId. Currency is
explicit and non-INR (fail-closed like PayPal). No live traffic without keys.
"""

import time

import frappe

from lube_station.lube_station.settings import get_setting

from .base import PaymentGatewayAdapter

BASE = "https://api.mollie.com/v2"
TIMEOUT = 20
RETRIES = 3


def _http(method, url, headers, body, timeout):
    import requests

    return requests.request(method, url, headers=headers, data=body, timeout=timeout)


class MollieAdapter(PaymentGatewayAdapter):
    adapter_name = "Mollie"

    def _key(self):
        key = (get_setting("mollie_secret_key") or "").strip()
        if not key:
            frappe.throw("Mollie not configured: set the secret key in Lube Station Settings")
        return key

    def _call(self, method, path, payload=None, transport=None):
        import json

        key = self._key()
        transport = transport or _http
        last_error = None
        for attempt in range(1, RETRIES + 1):
            try:
                resp = transport(
                    method,
                    f"{BASE}{path}",
                    {"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                    json.dumps(payload or {}),
                    TIMEOUT,
                )
                return self._result(method, path, resp)
            except frappe.ValidationError:
                raise
            except Exception as e:
                last_error = e
                time.sleep(min(2**attempt, 8))
        frappe.throw(f"Mollie {method} {path} failed after {RETRIES} attempts: {last_error}")

    def _result(self, method, path, resp):
        if getattr(resp, "status_code", 200) >= 500:
            raise ConnectionError(f"HTTP {resp.status_code}")
        try:
            out = resp.json() if hasattr(resp, "json") else {}
        except Exception:
            frappe.throw(f"Mollie {method} {path} returned non-JSON response")
        if getattr(resp, "status_code", 200) >= 300:
            detail = (out.get("detail") or out.get("title") or "unknown") if isinstance(out, dict) else "unknown"
            frappe.throw(f"Mollie {path} rejected: {detail}", frappe.ValidationError)
        return out if isinstance(out, dict) else {}

    def _currency(self, currency):
        currency = (currency or "").upper()
        if currency == "INR":
            frappe.throw("Mollie does not support INR", frappe.ValidationError)
        if not currency:
            frappe.throw("Mollie needs an explicit non-INR currency", frappe.ValidationError)
        return currency

    # -- payments ---------------------------------------------------------
    def create_payment(self, invoice, currency=None, transport=None):
        inv = frappe.get_doc("Hosting Invoice", invoice) if isinstance(invoice, str) else invoice
        currency = self._currency(currency)
        site = frappe.utils.get_url()
        out = self._call(
            "POST",
            "/payments",
            {
                "amount": {"currency": currency, "value": f"{float(inv.total_due):.2f}"},
                "description": f"Hosting Invoice {inv.name}",
                "redirectUrl": f"{site}/store/invoices",
                "metadata": {"invoice": inv.name},
            },
            transport,
        )
        checkout = (out.get("_links") or {}).get("checkout") or {}
        return {"gateway": "Mollie", "invoice": inv.name, "payment_id": out.get("id"), "approve_url": checkout.get("href", "")}

    def verify_payment(self, payload, transport=None):
        pid = (payload or {}).get("id") or (payload or {}).get("payment_id") or ""
        out = self._call("GET", f"/payments/{pid}", transport=transport)
        if out.get("status") != "paid":
            frappe.throw(f"Mollie payment not paid: {out.get('status')}", frappe.ValidationError)
        return {"verified": True, "gateway_reference": out.get("id", pid)}

    def handle_webhook(self, payload, headers, transport=None):
        payload = payload or {}
        pid = payload.get("id") or ""
        out = self._call("GET", f"/payments/{pid}", transport=transport)
        paid = out.get("status") == "paid"
        return {"event_id": out.get("id", pid), "type": out.get("status"), "verified": paid}

    def refund_payment(self, transaction, amount=None, currency=None, transport=None):
        txn = frappe.get_doc("Payment Transaction", transaction) if isinstance(transaction, str) else transaction
        data = {"description": f"Refund for {txn.invoice}"}
        if amount is not None:
            data["amount"] = {"currency": self._currency(currency), "value": f"{float(amount):.2f}"}
        out = self._call("POST", f"/payments/{txn.gateway_txn_id}/refunds", data, transport)
        return {"refunded": transaction, "amount": amount, "refund_id": out.get("id")}

    def create_payment_method(self, customer, token):
        return {"customer": customer, "token": token, "provider_token": token}

    def charge_saved_method(self, payment_method, invoice, currency=None, transport=None):
        method = frappe.get_doc("Saved Payment Method", payment_method)
        inv = frappe.get_doc("Hosting Invoice", invoice) if isinstance(invoice, str) else invoice
        currency = self._currency(currency)
        data = {
            "amount": {"currency": currency, "value": f"{float(inv.total_due):.2f}"},
            "description": f"Invoice {inv.name}",
            "sequenceType": "recurring",
            "customerId": method.get_password("token"),
            "metadata": {"invoice": inv.name},
        }
        out = self._call("POST", "/payments", data, transport)
        if out.get("status") not in ("open", "pending", "authorized", "paid"):
            frappe.throw(f"Mollie charge failed: {out.get('status')}", frappe.ValidationError)
        return {"charged": out.get("id"), "invoice": inv.name}
