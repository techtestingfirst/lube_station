"""Live Cashfree adapter tests. Transport is faked; no network happens."""

import base64
import hashlib
import hmac
import json

import frappe
from frappe.tests import IntegrationTestCase

from lube_station.lube_station.adapters.payments.cashfree import CashfreeAdapter, verify_signature


class FakeResp:
    def __init__(self, body, status_code=200):
        self._body = body
        self.status_code = status_code

    def json(self):
        return self._body


class FakeTransport:
    def __init__(self, bodies):
        self.bodies = list(bodies)
        self.calls = []

    def __call__(self, method, url, headers, body, timeout):
        self.calls.append(
            {"method": method, "url": url, "key": headers.get("x-client-id"), "body": json.loads(body or "{}")}
        )
        item = self.bodies.pop(0) if len(self.bodies) > 1 else self.bodies[0]
        if isinstance(item, Exception):
            raise item
        return item if isinstance(item, FakeResp) else FakeResp(item)


def _keys():
    frappe.db.set_single_value("Lube Station Settings", "cashfree_app_id", "testid")
    frappe.db.set_single_value("Lube Station Settings", "cashfree_secret_key", "testsecret")
    frappe.db.set_single_value("Lube Station Settings", "cashfree_sandbox", 1)


def _clearkeys():
    frappe.db.set_single_value("Lube Station Settings", "cashfree_app_id", "")
    frappe.db.set_single_value("Lube Station Settings", "cashfree_secret_key", "")


def _invoice(amount=900):
    cust = frappe.db.get_value("Hosting Customer", {"user": "Administrator"}, "name")
    if not cust:
        cust = frappe.get_doc({"doctype": "Hosting Customer", "user": "Administrator", "status": "Active"}).insert().name
    return frappe.get_doc(
        {
            "doctype": "Hosting Invoice",
            "customer": cust,
            "invoice_items": [{"description": "cf", "amount": amount}],
            "status": "Unpaid",
        }
    ).insert(ignore_permissions=True)


class TestCashfreeLiveAdapter(IntegrationTestCase):
    def test_signature_vector(self):
        raw, ts, secret = '{"a":1}', "1700000000000", "s3cr3t"
        good = base64.b64encode(hmac.new(secret.encode(), f"{ts}{raw}".encode(), hashlib.sha256).digest()).decode()
        self.assertTrue(verify_signature(secret, ts, raw, good))
        self.assertFalse(verify_signature(secret, ts, raw, "bad"))

    def test_create_and_verify(self):
        _keys()
        inv = _invoice(900)
        try:
            t = FakeTransport([{"order_id": inv.name, "payment_session_id": "sess_1", "order_status": "ACTIVE"}])
            out = CashfreeAdapter().create_payment(inv.name, transport=t)
            self.assertEqual(out["payment_session_id"], "sess_1")
            self.assertIn("sandbox.cashfree.com", t.calls[0]["url"])
            body = t.calls[0]["body"]
            self.assertEqual(body["order_amount"], 900)
            self.assertEqual(body["order_currency"], "INR")

            t = FakeTransport([{"order_id": inv.name, "order_status": "PAID"}])
            self.assertTrue(
                CashfreeAdapter().verify_payment({"order_id": inv.name}, transport=t)["verified"]
            )

            t = FakeTransport([{"order_id": inv.name, "order_status": "ACTIVE"}])
            self.assertRaises(
                frappe.ValidationError, CashfreeAdapter().verify_payment, {"order_id": inv.name}, t
            )
        finally:
            _clearkeys()
            frappe.delete_doc("Hosting Invoice", inv.name, ignore_permissions=True, force=True)

    def test_webhook_and_refund(self):
        _keys()
        raw = json.dumps({"type": "PAYMENT_SUCCESS_WEBHOOK", "data": {"order": {"order_id": "INV-1", "order_status": "PAID"}}}, separators=(",", ":"))
        ts = "1700000000000"
        sig = base64.b64encode(hmac.new(b"testsecret", f"{ts}{raw}".encode(), hashlib.sha256).digest()).decode()
        out = CashfreeAdapter().handle_webhook(
            {"type": "PAYMENT_SUCCESS_WEBHOOK", "data": {"order": {"order_id": "INV-1", "order_status": "PAID"}}, "_raw_body": raw},
            {"x-webhook-signature": sig, "x-webhook-timestamp": ts},
        )
        self.assertTrue(out["verified"])
        self.assertEqual(out["order_status"], "PAID")
        self.assertRaises(
            frappe.ValidationError,
            CashfreeAdapter().handle_webhook,
            {"_raw_body": raw, "type": "x"},
            {"x-webhook-signature": "bad", "x-webhook-timestamp": ts},
        )

        inv = _invoice(150)
        try:
            txn = frappe.get_doc(
                {
                    "doctype": "Payment Transaction",
                    "invoice": inv.name,
                    "gateway": "Cashfree Payments",
                    "gateway_txn_id": inv.name,
                    "amount": 150,
                    "status": "Success",
                }
            ).insert(ignore_permissions=True)
            try:
                t = FakeTransport([{"refund_id": "rf_1", "refund_status": "SUCCESS"}])
                out = CashfreeAdapter().refund_payment(txn.name, 150, transport=t)
                self.assertEqual(out["refund_id"], "rf_1")
                self.assertIn(f"/orders/{inv.name}/refunds", t.calls[0]["url"])
            finally:
                frappe.delete_doc("Payment Transaction", txn.name, ignore_permissions=True, force=True)
        finally:
            _clearkeys()
            frappe.delete_doc("Hosting Invoice", inv.name, ignore_permissions=True, force=True)
