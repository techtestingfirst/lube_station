"""Live PayU India adapter (hosted payment + postservice verify/refund).

Sandbox by default. Credentials from Lube Station Settings (merchant key +
salt Password). Hash formulas per PayU docs: payment
sha512(key|txnid|amount|productinfo|firstname|email|udf1..udf10|SALT),
commands sha512(key|command|var1|salt), returns verified against the reverse
hash. Nothing fires without keys (manual gate).
"""

import hashlib
import time

import frappe

from lube_station.lube_station.settings import get_setting

from .base import PaymentGatewayAdapter

TEST_PAY_URL = "https://test.payu.in/_payment"
LIVE_PAY_URL = "https://secure.payu.in/_payment"
TEST_SVC_URL = "https://test.payu.in/merchant/postservice?form=2"
LIVE_SVC_URL = "https://info.payu.in/merchant/postservice.php?form=2"
TIMEOUT = 20
RETRIES = 3


def _sha512(text: str) -> str:
    return hashlib.sha512(text.encode()).hexdigest()


def _command_hash(key: str, command: str, var1: str, salt: str) -> str:
    return _sha512("|".join([key, command, var1, salt]))


def _payment_hash(key, txnid, amount, productinfo, firstname, email, salt) -> str:
    parts = [key, txnid, f"{float(amount):.2f}", productinfo, firstname, email]
    parts += [""] * 10
    parts.append(salt)
    return _sha512("|".join(parts))


def _return_hash(payload: dict, salt: str, key: str) -> str:
    status = payload.get("status", "")
    udfs = [payload.get(f"udf{i}", "") or "" for i in range(10, 0, -1)]
    parts = [salt, status] + udfs + [
        payload.get("email", ""),
        payload.get("firstname", ""),
        payload.get("productinfo", ""),
        f"{float(payload.get('amount', 0)):.2f}",
        payload.get("txnid", ""),
        key,
    ]
    if payload.get("additionalCharges"):
        parts = [payload["additionalCharges"]] + parts
    return _sha512("|".join(parts))


def _http_post(url, headers, body, timeout):
    import requests

    return requests.post(url, headers=headers, data=body, timeout=timeout)


class PayUIndiaAdapter(PaymentGatewayAdapter):
    adapter_name = "PayU India"

    def _creds(self):
        key = (get_setting("payu_merchant_key") or "").strip()
        salt = (get_setting("payu_merchant_salt") or "").strip()
        if not key or not salt:
            frappe.throw("PayU not configured: set merchant key/salt in Lube Station Settings")
        sandbox = bool(int(get_setting("payu_sandbox") or 0))
        pay_url = TEST_PAY_URL if sandbox else LIVE_PAY_URL
        svc_url = TEST_SVC_URL if sandbox else LIVE_SVC_URL
        return key, salt, pay_url, svc_url

    def _svc(self, command: str, var1: str, extra: dict | None = None, transport=None):
        import urllib.parse

        key, salt, _, svc_url = self._creds()
        transport = transport or _http_post
        form = {"key": key, "command": command, "var1": var1, "hash": _command_hash(key, command, var1, salt)}
        form.update(extra or {})
        last_error = None
        for attempt in range(1, RETRIES + 1):
            try:
                resp = transport(
                    svc_url,
                    {"Content-Type": "application/x-www-form-urlencoded"},
                    urllib.parse.urlencode(form),
                    TIMEOUT,
                )
                return self._result(command, resp)
            except frappe.ValidationError:
                raise
            except Exception as e:
                last_error = e
                time.sleep(min(2**attempt, 8))
        frappe.throw(f"PayU {command} failed after {RETRIES} attempts: {last_error}")

    def _result(self, command, resp):
        if getattr(resp, "status_code", 200) >= 500:
            raise ConnectionError(f"HTTP {resp.status_code}")
        try:
            out = resp.json() if hasattr(resp, "json") else {}
        except Exception:
            frappe.throw(f"PayU {command} returned non-JSON response")
        if str(out.get("status", "")).lower() not in ("0", "success", "ok"):
            if "error" in str(out.get("status", "")).lower() or out.get("error_code"):
                frappe.throw(f"PayU {command} rejected: {out.get('msg', out)}", frappe.ValidationError)
        return out

    # -- payments ---------------------------------------------------------
    def create_payment(self, invoice, transport=None):
        key, salt, pay_url, _ = self._creds()
        inv = frappe.get_doc("Hosting Invoice", invoice) if isinstance(invoice, str) else invoice
        customer = frappe.get_doc("Hosting Customer", inv.customer)
        email = frappe.db.get_value("User", customer.user, "email") or customer.user
        name = frappe.db.get_value("User", customer.user, "full_name") or email
        txnid = inv.name
        site = frappe.utils.get_url()
        params = {
            "key": key,
            "txnid": txnid,
            "amount": f"{float(inv.total_due):.2f}",
            "productinfo": f"Hosting Invoice {inv.name}",
            "firstname": name,
            "email": email,
            "phone": "",
            "surl": f"{site}/api/method/lube_station.lube_station.payments.methods.payu_return",
            "furl": f"{site}/api/method/lube_station.lube_station.payments.methods.payu_return",
        }
        params["hash"] = _payment_hash(key, txnid, inv.total_due, params["productinfo"], name, email, salt)
        return {"gateway": "PayU India", "invoice": inv.name, "post_url": pay_url, "params": params}

    def verify_payment(self, payload, transport=None):
        txnid = (payload or {}).get("txnid") or (payload or {}).get("id") or ""
        out = self._svc("verify_payment", txnid, transport=transport)
        details = out.get("transaction_details") or {}
        txn = details.get(txnid) if isinstance(details, dict) else None
        status = (txn or {}).get("status", "")
        if status.lower() not in ("success", "complete"):
            frappe.throw(f"PayU payment not captured: {status}", frappe.ValidationError)
        return {"verified": True, "gateway_reference": (txn or {}).get("mihpayid", txnid)}

    def handle_webhook(self, payload, headers, transport=None):
        payload = payload or {}
        key, salt, _, _ = self._creds()
        if payload.get("hash", "") != _return_hash(payload, salt, key):
            frappe.throw("PayU return hash mismatch", frappe.ValidationError)
        return {"event_id": payload.get("mihpayid") or payload.get("txnid"), "type": payload.get("status"), "verified": True}

    def refund_payment(self, transaction, amount=None, transport=None):
        import secrets

        txn = frappe.get_doc("Payment Transaction", transaction) if isinstance(transaction, str) else transaction
        out = self._svc(
            "cancel_refund_transaction",
            txn.gateway_txn_id,
            {"var2": f"rf{secrets.token_hex(6)}", "var3": f"{float(amount if amount is not None else txn.amount):.2f}"},
            transport,
        )
        return {"refunded": transaction, "amount": amount, "detail": out}

    def create_payment_method(self, customer, token):
        frappe.throw("PayU tokenization is not mapped yet")

    def charge_saved_method(self, payment_method, invoice):
        frappe.throw("PayU auto-charge is not mapped yet")
