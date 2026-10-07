"""Live GoCardless adapter (REST, Bearer token + version header).

Sandbox by default. Credentials from Lube Station Settings (access token +
webhook secret Password fields). Shapes per GoCardless docs: minor-unit
amounts, mandate-linked payments, refunds per payment, HMAC-SHA256 webhook
verification over the raw body. Currency explicit non-INR (fail-closed like
PayPal/Mollie). No live traffic without keys.
"""

import hashlib
import hmac
import time

import frappe

from lube_station.lube_station.settings import get_setting

from .base import PaymentGatewayAdapter

SANDBOX = "https://api-sandbox.gocardless.com"
LIVE = "https://api.gocardless.com"
VERSION = "2015-07-06"
TIMEOUT = 20
RETRIES = 3


def _http(method, url, headers, body, timeout):
    import requests

    return requests.request(method, url, headers=headers, data=body, timeout=timeout)


def verify_signature(secret: str, raw_body: str, signature: str) -> bool:
    digest = hmac.new(secret.encode(), (raw_body or "").encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(digest, signature or "")


class GoCardlessAdapter(PaymentGatewayAdapter):
    adapter_name = "GoCardless"

    def _creds(self):
        token = (get_setting("gocardless_access_token") or "").strip()
        if not token:
            frappe.throw("GoCardless not configured: set the access token in Lube Station Settings")
        base = SANDBOX if bool(int(get_setting("gocardless_sandbox") or 0)) else LIVE
        return token, base

    def _call(self, method, path, payload=None, transport=None):
        import json

        token, base = self._creds()
        transport = transport or _http
        last_error = None
        for attempt in range(1, RETRIES + 1):
            try:
                resp = transport(
                    method,
                    f"{base}{path}",
                    {
                        "Authorization": f"Bearer {token}",
                        "GoCardless-Version": VERSION,
                        "Content-Type": "application/json",
                    },
                    json.dumps(payload or {}),
                    TIMEOUT,
                )
                return self._result(method, path, resp)
            except frappe.ValidationError:
                raise
            except Exception as e:
                last_error = e
                time.sleep(min(2**attempt, 8))
        frappe.throw(f"GoCardless {method} {path} failed after {RETRIES} attempts: {last_error}")

    def _result(self, method, path, resp):
        if getattr(resp, "status_code", 200) >= 500:
            raise ConnectionError(f"HTTP {resp.status_code}")
        try:
            out = resp.json() if hasattr(resp, "json") else {}
        except Exception:
            frappe.throw(f"GoCardless {method} {path} returned non-JSON response")
        if getattr(resp, "status_code", 200) >= 300:
            detail = out.get("message", "unknown") if isinstance(out, dict) else "unknown"
            frappe.throw(f"GoCardless {path} rejected: {detail}", frappe.ValidationError)
        return out if isinstance(out, dict) else {}

    def _currency(self, currency):
        currency = (currency or "").upper()
        if currency == "INR":
            frappe.throw("GoCardless does not support INR", frappe.ValidationError)
        if not currency:
            frappe.throw("GoCardless needs an explicit non-INR currency", frappe.ValidationError)
        return currency

    # -- payments ---------------------------------------------------------
    def create_payment(self, invoice, currency=None, transport=None):
        inv = frappe.get_doc("Hosting Invoice", invoice) if isinstance(invoice, str) else invoice
        currency = self._currency(currency)
        customer = frappe.get_doc("Hosting Customer", inv.customer)
        email = frappe.db.get_value("User", customer.user, "email") or customer.user
        out = self._call(
            "POST",
            "/customers",
            {"customers": {"email": email, "metadata": {"customer": inv.customer}}},
            transport,
        )
        customer_id = out.get("customers", {}).get("id", "")
        return {
            "gateway": "GoCardless",
            "invoice": inv.name,
            "customer_id": customer_id,
            "hint": "Collect a mandate for this customer, then charge it",
        }

    def verify_payment(self, payload, transport=None):
        pid = (payload or {}).get("id") or (payload or {}).get("payment_id") or ""
        out = self._call("GET", f"/payments/{pid}", transport=transport)
        payment = out.get("payments", {})
        if payment.get("status") not in ("confirmed", "paid_out"):
            frappe.throw(f"GoCardless payment not collected: {payment.get('status')}", frappe.ValidationError)
        return {"verified": True, "gateway_reference": payment.get("id", pid)}

    def handle_webhook(self, payload, headers, transport=None):
        secret = (get_setting("gocardless_webhook_secret") or "").strip()
        raw = (payload or {}).get("_raw_body")
        if raw is None:
            import json

            raw = json.dumps(payload or {}, separators=(",", ":"))
        signature = (headers or {}).get("Webhook-Signature", "")
        if secret and not verify_signature(secret, raw, signature):
            frappe.throw("GoCardless webhook signature mismatch", frappe.ValidationError)
        events = (payload or {}).get("events") or []
        first = events[0] if events else {}
        return {
            "event_id": first.get("id"),
            "type": f"{first.get('resource_type')}.{first.get('action')}",
            "verified": bool(secret),
        }

    def refund_payment(self, transaction, amount=None, transport=None):
        txn = frappe.get_doc("Payment Transaction", transaction) if isinstance(transaction, str) else transaction
        data = {"refunds": {"links": {"payment": txn.gateway_txn_id}}}
        if amount is not None:
            data["refunds"]["amount"] = int(round(float(amount) * 100))
        out = self._call("POST", "/refunds", data, transport)
        return {"refunded": transaction, "amount": amount, "refund_id": out.get("refunds", {}).get("id")}

    def create_payment_method(self, customer, token):
        out = self._call("GET", f"/mandates/{token}")
        mandate = out.get("mandates", {})
        if mandate.get("status") not in ("pending", "active"):
            frappe.throw(f"GoCardless mandate unusable: {mandate.get('status')}", frappe.ValidationError)
        return {"customer": customer, "token": token, "provider_token": mandate.get("id", token)}

    def charge_saved_method(self, payment_method, invoice, currency=None, transport=None):
        method = frappe.get_doc("Saved Payment Method", payment_method)
        inv = frappe.get_doc("Hosting Invoice", invoice) if isinstance(invoice, str) else invoice
        currency = self._currency(currency)
        token = method.get_password("token")
        out = self._call(
            "POST",
            "/payments",
            {
                "payments": {
                    "amount": int(round(float(inv.total_due) * 100)),
                    "currency": currency,
                    "description": f"Invoice {inv.name}",
                    "metadata": {"invoice": inv.name},
                    "links": {"mandate": token},
                }
            },
            transport,
        )
        payment = out.get("payments", {})
        if payment.get("status") not in ("pending_submission", "submitted", "confirmed", "paid_out"):
            frappe.throw(f"GoCardless charge failed: {payment.get('status')}", frappe.ValidationError)
        return {"charged": payment.get("id"), "invoice": inv.name}
