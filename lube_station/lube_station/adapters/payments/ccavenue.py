"""Live CCAvenue adapter (hosted form + encrypted response).

Sandbox by default (test credentials behave as sandbox; same endpoint).
Crypto per CCAvenue spec: AES-128-CBC, key = MD5(working key), fixed IV,
PKCS7, hex encoding. create_payment returns the form action + encRequest +
access code for the frontend to POST. Return posts decrypt to order status;
Success marks verified. Refunds happen in the merchant panel (Instant Refund
API shapes unverified — explicit); tokenization/auto-charge unsupported.
"""

import hashlib

import frappe

from lube_station.lube_station.settings import get_setting

from .base import PaymentGatewayAdapter

POST_URL = "https://secure.ccavenue.com/transaction/transaction.do?command=initiateTransaction"
IV = b"\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b\x0c\x0d\x0e\x0f"


def _cipher(working_key: str):
    try:
        from Crypto.Cipher import AES
    except ImportError:
        frappe.throw("pycryptodome library not installed")
    return AES.new(hashlib.md5(working_key.encode()).digest(), AES.MODE_CBC, IV)


def encrypt(working_key: str, plain: str) -> str:
    from binascii import hexlify

    data = plain.encode()
    pad = 16 - (len(data) % 16)
    return hexlify(_cipher(working_key).encrypt(data + bytes([pad]) * pad)).decode()


def decrypt(working_key: str, encoded: str) -> str:
    from binascii import unhexlify

    raw = _cipher(working_key).decrypt(unhexlify(encoded))
    return raw[: -raw[-1]].decode()


class CCAvenueAdapter(PaymentGatewayAdapter):
    adapter_name = "CCAvenue"

    def _creds(self):
        merchant_id = (get_setting("ccavenue_merchant_id") or "").strip()
        access_code = (get_setting("ccavenue_access_code") or "").strip()
        working_key = (get_setting("ccavenue_working_key") or "").strip()
        if not merchant_id or not access_code or not working_key:
            frappe.throw("CCAvenue not configured: set merchant ID/access code/working key in Lube Station Settings")
        return merchant_id, access_code, working_key

    # -- payments ---------------------------------------------------------
    def create_payment(self, invoice):
        merchant_id, access_code, working_key = self._creds()
        inv = frappe.get_doc("Hosting Invoice", invoice) if isinstance(invoice, str) else invoice
        customer = frappe.get_doc("Hosting Customer", inv.customer)
        email = frappe.db.get_value("User", customer.user, "email") or customer.user
        site = frappe.utils.get_url()
        fields = {
            "merchant_id": merchant_id,
            "order_id": inv.name,
            "amount": f"{float(inv.total_due):.2f}",
            "currency": "INR",
            "redirect_url": f"{site}/api/method/lube_station.lube_station.payments.methods.ccavenue_return",
            "cancel_url": f"{site}/store/invoices",
            "billing_email": email,
            "merchant_param1": inv.name,
        }
        body = "&".join(f"{k}={v}" for k, v in fields.items())
        return {
            "gateway": "CCAvenue",
            "invoice": inv.name,
            "post_url": POST_URL,
            "access_code": access_code,
            "enc_request": encrypt(working_key, body),
        }

    def verify_payment(self, payload, transport=None):
        data = dict(payload or {})
        if str(data.get("order_status", "")).lower() != "success":
            frappe.throw(f"CCAvenue payment not captured: {data.get('order_status')}", frappe.ValidationError)
        return {"verified": True, "gateway_reference": data.get("tracking_id") or data.get("order_id")}

    def handle_webhook(self, payload, headers, transport=None):
        _, _, working_key = self._creds()
        enc = (payload or {}).get("encResp", "")
        if not enc:
            frappe.throw("CCAvenue return has no response")
        try:
            pairs = dict(p.split("=", 1) for p in decrypt(working_key, enc).split("&") if "=" in p)
        except Exception:
            frappe.throw("CCAvenue response failed to decrypt", frappe.ValidationError)
        out = self.verify_payment(pairs)
        out["order_id"] = pairs.get("order_id", "")
        return out

    def refund_payment(self, transaction, amount=None):
        frappe.throw("CCAvenue refunds run in the merchant panel (Instant Refund API unmapped)")

    def create_payment_method(self, customer, token):
        frappe.throw("CCAvenue tokenization is not mapped yet")

    def charge_saved_method(self, payment_method, invoice):
        frappe.throw("CCAvenue auto-charge is not mapped yet")
