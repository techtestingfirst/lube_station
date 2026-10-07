"""Live Cashfree adapter (PG REST, app-id/secret headers).

Sandbox by default. Credentials from Lube Station Settings (app ID + secret
Password). Shapes per Cashfree PG docs: order create returns
payment_session_id, order status PAID means captured, refunds per order,
webhooks verified as base64(HMAC-SHA256(timestamp + raw body)). Token vault
charging is explicitly unmapped. No live traffic without keys.
"""

import base64
import hashlib
import hmac
import time

import frappe

from lube_station.lube_station.settings import get_setting

from .base import PaymentGatewayAdapter

SANDBOX = "https://sandbox.cashfree.com/pg"
LIVE = "https://api.cashfree.com/pg"
VERSION = "2023-08-01"
TIMEOUT = 20
RETRIES = 3


def _http(method, url, headers, body, timeout):
    import requests

    return requests.request(method, url, headers=headers, data=body, timeout=timeout)


def verify_signature(secret: str, timestamp: str, raw_body: str, signature: str) -> bool:
    digest = hmac.new(secret.encode(), f"{timestamp}{raw_body}".encode(), hashlib.sha256).digest()
    return hmac.compare_digest(base64.b64encode(digest).decode(), signature or "")


class CashfreeAdapter(PaymentGatewayAdapter):
    adapter_name = "Cashfree Payments"

    def _creds(self):
        app_id = (get_setting("cashfree_app_id") or "").strip()
        secret = (get_setting("cashfree_secret_key") or "").strip()
        if not app_id or not secret:
            frappe.throw("Cashfree not configured: set app ID/secret in Lube Station Settings")
        base = SANDBOX if bool(int(get_setting("cashfree_sandbox") or 0)) else LIVE
        return app_id, secret, base

    def _auth_headers(self):
        app_id, secret, _ = self._creds()
        return {
            "x-client-id": app_id,
            "x-client-secret": secret,
            "x-api-version": VERSION,
            "Content-Type": "application/json",
        }

    def _call(self, method, path, payload=None, transport=None):
        import json

        _, _, base = self._creds()
        transport = transport or _http
        last_error = None
        for attempt in range(1, RETRIES + 1):
            try:
                resp = transport(
                    method, f"{base}{path}", self._auth_headers(), json.dumps(payload or {}), TIMEOUT
                )
                return self._result(method, path, resp)
            except frappe.ValidationError:
                raise
            except Exception as e:
                last_error = e
                time.sleep(min(2**attempt, 8))
        frappe.throw(f"Cashfree {method} {path} failed after {RETRIES} attempts: {last_error}")

    def _result(self, method, path, resp):
        if getattr(resp, "status_code", 200) >= 500:
            raise ConnectionError(f"HTTP {resp.status_code}")
        try:
            out = resp.json() if hasattr(resp, "json") else {}
        except Exception:
            frappe.throw(f"Cashfree {method} {path} returned non-JSON response")
        if str(out.get("type", "")).lower().startswith("https://") or out.get("code"):
            frappe.throw(f"Cashfree {path} rejected: {out.get('message', out)}", frappe.ValidationError)
        return out if isinstance(out, dict) else {}

    # -- payments ---------------------------------------------------------
    def create_payment(self, invoice, currency="INR", transport=None):
        inv = frappe.get_doc("Hosting Invoice", invoice) if isinstance(invoice, str) else invoice
        customer = frappe.get_doc("Hosting Customer", inv.customer)
        email = frappe.db.get_value("User", customer.user, "email") or customer.user
        details = {"customer_id": inv.customer, "customer_email": email}
        phone = frappe.db.get_value("User", customer.user, "mobile_no")
        if phone:
            details["customer_phone"] = phone
        out = self._call(
            "POST",
            "/orders",
            {
                "order_id": inv.name,
                "order_amount": round(float(inv.total_due), 2),
                "order_currency": currency or "INR",
                "customer_details": details,
            },
            transport,
        )
        return {
            "gateway": "Cashfree Payments",
            "invoice": inv.name,
            "order_id": out.get("order_id", inv.name),
            "payment_session_id": out.get("payment_session_id"),
        }

    def verify_payment(self, payload, transport=None):
        order_id = (payload or {}).get("order_id") or (payload or {}).get("id") or ""
        out = self._call("GET", f"/orders/{order_id}", transport=transport)
        if str(out.get("order_status", "")).upper() != "PAID":
            frappe.throw(f"Cashfree order not paid: {out.get('order_status')}", frappe.ValidationError)
        return {"verified": True, "gateway_reference": out.get("order_id", order_id)}

    def handle_webhook(self, payload, headers, transport=None):
        import json

        _, secret, _ = self._creds()
        raw = (payload or {}).get("_raw_body")
        if raw is None:
            raw = json.dumps(payload or {}, separators=(",", ":"))
        signature = (headers or {}).get("x-webhook-signature", "")
        timestamp = (headers or {}).get("x-webhook-timestamp", "")
        if not verify_signature(secret, timestamp, raw, signature):
            frappe.throw("Cashfree webhook signature mismatch", frappe.ValidationError)
        data = (payload or {}).get("data") or {}
        order = data.get("order") or {}
        return {
            "event_id": (payload or {}).get("event_id") or data.get("order_id"),
            "type": (payload or {}).get("type"),
            "order_id": order.get("order_id") or data.get("order_id"),
            "order_status": order.get("order_status"),
            "verified": True,
        }

    def refund_payment(self, transaction, amount=None, transport=None):
        import secrets

        txn = frappe.get_doc("Payment Transaction", transaction) if isinstance(transaction, str) else transaction
        out = self._call(
            "POST",
            f"/orders/{txn.invoice}/refunds",
            {
                "refund_amount": round(float(amount if amount is not None else txn.amount), 2),
                "refund_id": f"rf{secrets.token_hex(6)}",
                "refund_note": f"Refund for {txn.invoice}",
            },
            transport,
        )
        return {"refunded": transaction, "amount": amount, "refund_id": out.get("refund_id")}

    def create_payment_method(self, customer, token):
        frappe.throw("Cashfree token vault is not mapped yet")

    def charge_saved_method(self, payment_method, invoice):
        frappe.throw("Cashfree auto-charge is not mapped yet")
