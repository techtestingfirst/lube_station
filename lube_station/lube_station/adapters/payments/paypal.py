"""Live PayPal adapter (REST v2 over HTTPS, OAuth2 client credentials).

Sandbox by default via the paypal_sandbox flag. Credentials reuse the PayPal
Settings row (api_username = REST client ID, api_password Password = secret).
Invoices here are INR-based and PayPal receiving is non-INR, so every money
method requires an explicit non-INR currency and rejects INR (same rule as
the Express Checkout link builder). No live traffic without keys.
"""

import time

import frappe

from .base import PaymentGatewayAdapter

SANDBOX = "https://api-m.sandbox.paypal.com"
LIVE = "https://api-m.paypal.com"
TIMEOUT = 20
RETRIES = 3


def _http(method, url, headers, body, timeout):
    import requests

    return requests.request(method, url, headers=headers, data=body, timeout=timeout)


class PayPalCheckoutAdapter(PaymentGatewayAdapter):
    adapter_name = "PayPal Checkout"

    # -- connection -----------------------------------------------------
    def _settings(self):
        if not frappe.db.exists("PayPal Settings", "PayPal Settings"):
            frappe.throw("PayPal not configured: create PayPal Settings first")
        settings = frappe.get_doc("PayPal Settings", "PayPal Settings")
        client_id = (settings.get("api_username") or "").strip()
        secret = settings.get_password(fieldname="api_password", raise_exception=False)
        if not client_id or not secret:
            frappe.throw("PayPal not configured: set REST client ID/secret first")
        base = SANDBOX if settings.get("paypal_sandbox") else LIVE
        return settings, base, client_id, secret

    def _token(self, transport=None):
        import base64
        import urllib.parse

        _, base, client_id, secret = self._settings()
        if getattr(self, "_bearer_base", None) == base and getattr(self, "_bearer", None):
            return base, self._bearer
        transport = transport or _http
        creds = base64.b64encode(f"{client_id}:{secret}".encode()).decode()
        last_error = None
        for attempt in range(1, RETRIES + 1):
            try:
                resp = transport(
                    "POST",
                    f"{base}/v1/oauth2/token",
                    {"Authorization": f"Basic {creds}", "Content-Type": "application/x-www-form-urlencoded"},
                    urllib.parse.urlencode({"grant_type": "client_credentials"}),
                    TIMEOUT,
                )
                out = resp.json() if hasattr(resp, "json") else {}
                if not out.get("access_token"):
                    frappe.throw(f"PayPal auth rejected: {out.get('error_description', 'unknown')}", frappe.ValidationError)
                self._bearer_base = base
                self._bearer = out["access_token"]
                return base, out["access_token"]
            except frappe.ValidationError:
                raise
            except Exception as e:
                last_error = e
                time.sleep(min(2**attempt, 8))
        frappe.throw(f"PayPal auth failed after {RETRIES} attempts: {last_error}")

    def _call(self, method, path, payload=None, transport=None):
        import json

        base, token = self._token(transport)
        transport = transport or _http
        last_error = None
        for attempt in range(1, RETRIES + 1):
            try:
                resp = transport(
                    method,
                    f"{base}{path}",
                    {"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                    json.dumps(payload or {}),
                    TIMEOUT,
                )
                out = resp.json() if hasattr(resp, "json") else {}
                if getattr(resp, "status_code", 200) >= 300:
                    detail = (out.get("details") or [{}])[0].get("description", out.get("message", "unknown"))
                    frappe.throw(f"PayPal {path} rejected: {detail}", frappe.ValidationError)
                return out
            except frappe.ValidationError:
                raise
            except Exception as e:
                last_error = e
                time.sleep(min(2**attempt, 8))
        frappe.throw(f"PayPal {path} failed after {RETRIES} attempts: {last_error}")

    def _currency(self, currency):
        currency = (currency or "").upper()
        if currency == "INR":
            frappe.throw("PayPal does not support INR", frappe.ValidationError)
        if not currency:
            frappe.throw("PayPal needs an explicit non-INR currency", frappe.ValidationError)
        return currency

    # -- payments ---------------------------------------------------------
    def create_payment(self, invoice, currency=None, transport=None):
        inv = frappe.get_doc("Hosting Invoice", invoice) if isinstance(invoice, str) else invoice
        currency = self._currency(currency)
        out = self._call(
            "POST",
            "/v2/checkout/orders",
            {
                "intent": "CAPTURE",
                "purchase_units": [
                    {
                        "description": f"Hosting Invoice {inv.name}",
                        "custom_id": inv.name,
                        "amount": {"currency_code": currency, "value": f"{float(inv.total_due):.2f}"},
                    }
                ],
            },
            transport,
        )
        approve = next((l.get("href") for l in out.get("links", []) if l.get("rel") == "approve"), "")
        return {"gateway": "PayPal Checkout", "invoice": inv.name, "order_id": out.get("id"), "approve_url": approve}

    def verify_payment(self, payload, transport=None):
        order_id = (payload or {}).get("id") or (payload or {}).get("order_id")
        out = self._call("GET", f"/v2/checkout/orders/{order_id}", transport=transport)
        if out.get("status") != "COMPLETED":
            frappe.throw(f"PayPal order not completed: {out.get('status')}", frappe.ValidationError)
        return {"verified": True, "gateway_reference": out.get("id")}

    def handle_webhook(self, payload, headers, transport=None):
        payload = payload or {}
        secret_note = "unverified"
        webhook_id = (headers or {}).get("Webhook-Id", "")
        if webhook_id:
            out = self._call(
                "POST",
                "/v1/notifications/verify-webhook-signature",
                {
                    "transmission_id": (headers or {}).get("Transmission-Id", ""),
                    "transmission_time": (headers or {}).get("Transmission-Time", ""),
                    "cert_url": (headers or {}).get("Cert-Url", ""),
                    "auth_algo": (headers or {}).get("Auth-Algo", ""),
                    "transmission_sig": (headers or {}).get("Transmission-Sig", ""),
                    "webhook_id": webhook_id,
                    "webhook_event": payload,
                },
                transport,
            )
            secret_note = out.get("verification_status", "unverified")
            if secret_note != "SUCCESS":
                frappe.throw(f"PayPal webhook rejected: {secret_note}", frappe.ValidationError)
        return {
            "event_id": payload.get("id"),
            "type": payload.get("event_type"),
            "verified": secret_note == "SUCCESS",
        }

    def refund_payment(self, transaction, amount=None, currency=None, transport=None):
        txn = frappe.get_doc("Payment Transaction", transaction) if isinstance(transaction, str) else transaction
        capture_id = txn.gateway_txn_id
        try:
            order = self._call("GET", f"/v2/checkout/orders/{capture_id}", transport=transport)
            units = order.get("purchase_units", [])
            captures = (units[0].get("payments") or {}).get("captures", []) if units else []
            if captures:
                capture_id = captures[0]["id"]
        except frappe.ValidationError:
            pass  # not an order id: treat the reference as a capture id directly
        data = {}
        if amount is not None:
            data = {"amount": {"currency_code": self._currency(currency), "value": f"{float(amount):.2f}"}}
        out = self._call("POST", f"/v2/payments/captures/{capture_id}/refund", data, transport)
        return {"refunded": transaction, "amount": amount, "refund_id": out.get("id")}

    def create_payment_method(self, customer, token):
        return {"customer": customer, "token": token, "provider_token": token}

    def charge_saved_method(self, payment_method, invoice, currency=None, transport=None):
        method = frappe.get_doc("Saved Payment Method", payment_method)
        inv = frappe.get_doc("Hosting Invoice", invoice) if isinstance(invoice, str) else invoice
        currency = self._currency(currency)
        out = self._call(
            "POST",
            "/v2/checkout/orders",
            {
                "intent": "CAPTURE",
                "purchase_units": [
                    {
                        "description": f"Invoice {inv.name}",
                        "custom_id": inv.name,
                        "amount": {"currency_code": currency, "value": f"{float(inv.total_due):.2f}"},
                    }
                ],
                "payment_source": {"token": {"id": method.token, "type": "PAYMENT_METHOD_TOKEN"}},
            },
            transport,
        )
        return {"charged": out.get("id"), "invoice": inv.name}
