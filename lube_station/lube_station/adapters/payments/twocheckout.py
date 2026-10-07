"""Live 2Checkout/Verifone adapter (REST 6.0 + JSON-RPC, hash auth).

Sandbox by default (single production host; test orders flagged per call).
Auth follows the documented scheme: HMAC-SHA256 of
len(code)+code+len(date)+date with the secret key, sent as
X-Avangate-Authentication. Backoffice APIs retrieve and update sales but
cannot create them, so create_payment points at panel buy-links; verify
reads order status; refunds go through JSON-RPC issueRefund; INS envelopes
parse without crypto (no verified formula published — flagged unverified).
"""

import hashlib
import hmac
import time

import frappe

from lube_station.lube_station.settings import get_setting

from .base import PaymentGatewayAdapter

HOST = "https://api.2checkout.com"
REST = f"{HOST}/rest/6.0"
RPC = f"{HOST}/rpc/6.0/"
TIMEOUT = 20
RETRIES = 3
ALGO = "sha256"


def _http(method, url, headers, body, timeout):
    import requests

    return requests.request(method, url, headers=headers, data=body, timeout=timeout)


def auth_header(merchant_code: str, secret_key: str, when: str | None = None):
    import datetime

    when = when or datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    raw = f"{len(merchant_code)}{merchant_code}{len(when)}{when}"
    digest = hmac.new(secret_key.encode(), raw.encode(), hashlib.sha256).hexdigest()
    return {"code": merchant_code, "date": when, "hash": digest, "algo": ALGO}


class TwoCheckoutAdapter(PaymentGatewayAdapter):
    adapter_name = "2Checkout / Verifone"

    def _creds(self):
        code = (get_setting("twocheckout_merchant_code") or "").strip()
        secret = (get_setting("twocheckout_secret_key") or "").strip()
        if not code or not secret:
            frappe.throw("2Checkout not configured: set merchant code/secret in Lube Station Settings")
        return code, secret

    def _headers(self):
        code, secret = self._creds()
        parts = auth_header(code, secret)
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Avangate-Authentication": f"code=\"{parts['code']}\" date=\"{parts['date']}\" hash=\"{parts['hash']}\" algo=\"{parts['algo']}\"",
        }

    def _call(self, method, path, payload=None, params=None, transport=None):
        import json
        import urllib.parse

        transport = transport or _http
        url = f"{REST}{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        last_error = None
        for attempt in range(1, RETRIES + 1):
            try:
                resp = transport(method, url, self._headers(), json.dumps(payload or {}), TIMEOUT)
                return self._result(method, path, resp)
            except frappe.ValidationError:
                raise
            except Exception as e:
                last_error = e
                time.sleep(min(2**attempt, 8))
        frappe.throw(f"2Checkout {method} {path} failed after {RETRIES} attempts: {last_error}")

    def _result(self, method, path, resp):
        if getattr(resp, "status_code", 200) >= 500:
            raise ConnectionError(f"HTTP {resp.status_code}")
        try:
            out = resp.json() if hasattr(resp, "json") else {}
        except Exception:
            frappe.throw(f"2Checkout {method} {path} returned non-JSON response")
        if getattr(resp, "status_code", 200) >= 300:
            detail = out.get("message", out) if isinstance(out, dict) else out
            frappe.throw(f"2Checkout {path} rejected: {detail}", frappe.ValidationError)
        return out if isinstance(out, (dict, list)) else {}

    def _rpc(self, rpc_method, rpc_params, transport=None):
        import json

        transport = transport or _http
        body = json.dumps({"jsonrpc": "2.0", "method": rpc_method, "params": rpc_params, "id": 1})
        last_error = None
        for attempt in range(1, RETRIES + 1):
            try:
                resp = transport("POST", RPC, {"Content-Type": "application/json", "Accept": "application/json"}, body, TIMEOUT)
                out = resp.json() if hasattr(resp, "json") else {}
                if isinstance(out, dict) and out.get("error"):
                    frappe.throw(f"2Checkout {rpc_method} rejected: {out['error']}", frappe.ValidationError)
                return (out or {}).get("result")
            except frappe.ValidationError:
                raise
            except Exception as e:
                last_error = e
                time.sleep(min(2**attempt, 8))
        frappe.throw(f"2Checkout {rpc_method} failed after {RETRIES} attempts: {last_error}")

    def _session(self, transport=None):
        code, secret = self._creds()
        import datetime

        when = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        parts = auth_header(code, secret, when)
        return self._rpc("login", [code, when, parts["hash"], ALGO], transport)

    # -- payments ---------------------------------------------------------
    def create_payment(self, invoice):
        frappe.throw("2Checkout sales start from panel buy-links; verify them here after payment")

    def verify_payment(self, payload, transport=None):
        ref = (payload or {}).get("order_reference") or (payload or {}).get("id") or ""
        out = self._call("GET", f"/orders/{ref}/", transport=transport)
        status = str(out.get("Status") or out.get("status") or "").upper()
        approve = str(out.get("ApproveStatus") or out.get("approve_status") or "").upper()
        if status != "COMPLETE" or approve not in ("", "OK"):
            frappe.throw(f"2Checkout order not complete: {status}/{approve}", frappe.ValidationError)
        return {"verified": True, "gateway_reference": out.get("RefNo", ref)}

    def handle_webhook(self, payload, headers, transport=None):
        payload = payload or {}
        return {
            "event_id": payload.get("sale_id") or payload.get("invoice_id"),
            "type": payload.get("message_type"),
            "verified": False,
        }

    def refund_payment(self, transaction, amount=None, comment="seller refund", transport=None):
        txn = frappe.get_doc("Payment Transaction", transaction) if isinstance(transaction, str) else transaction
        session = self._session(transport)
        out = self._rpc("issueRefund", [session, txn.gateway_txn_id, comment], transport)
        return {"refunded": transaction, "amount": amount, "detail": out}

    def create_payment_method(self, customer, token):
        frappe.throw("2Checkout tokenization is not mapped yet")

    def charge_saved_method(self, payment_method, invoice):
        frappe.throw("2Checkout auto-charge is not mapped yet")
