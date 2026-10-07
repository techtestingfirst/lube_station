"""Live GoCardless adapter tests. Transport is faked; no network happens."""

import hashlib
import hmac

import frappe
from frappe.tests import IntegrationTestCase

from lube_station.lube_station.adapters.payments.gocardless import GoCardlessAdapter, verify_signature


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
        import json

        try:
            parsed = json.loads(body or "{}")
        except Exception:
            parsed = {}
        self.calls.append(
            {"method": method, "url": url, "auth": headers.get("Authorization", ""), "body": parsed}
        )
        item = self.bodies.pop(0) if len(self.bodies) > 1 else self.bodies[0]
        if isinstance(item, Exception):
            raise item
        return item if isinstance(item, FakeResp) else FakeResp(item)


def _keys():
    frappe.db.set_single_value("Lube Station Settings", "gocardless_access_token", "tok_test")
    frappe.db.set_single_value("Lube Station Settings", "gocardless_webhook_secret", "whsec")
    frappe.db.set_single_value("Lube Station Settings", "gocardless_sandbox", 1)


def _clearkeys():
    frappe.db.set_single_value("Lube Station Settings", "gocardless_access_token", "")
    frappe.db.set_single_value("Lube Station Settings", "gocardless_webhook_secret", "")


def _invoice(amount=750):
    cust = frappe.db.get_value("Hosting Customer", {"user": "Administrator"}, "name")
    if not cust:
        cust = frappe.get_doc({"doctype": "Hosting Customer", "user": "Administrator", "status": "Active"}).insert().name
    return frappe.get_doc(
        {
            "doctype": "Hosting Invoice",
            "customer": cust,
            "invoice_items": [{"description": "gc", "amount": amount}],
            "status": "Unpaid",
        }
    ).insert(ignore_permissions=True)


class TestGoCardlessLiveAdapter(IntegrationTestCase):
    def test_signature_vector(self):
        good = hmac.new(b"whsec", b"body123", hashlib.sha256).hexdigest()
        self.assertTrue(verify_signature("whsec", "body123", good))
        self.assertFalse(verify_signature("whsec", "body123", "bad"))

    def test_create_rejects_inr(self):
        _keys()
        inv = _invoice(750)
        try:
            self.assertRaises(
                frappe.ValidationError,
                GoCardlessAdapter().create_payment,
                inv.name,
                "INR",
                FakeTransport([]),
            )
        finally:
            _clearkeys()
            frappe.delete_doc("Hosting Invoice", inv.name, ignore_permissions=True, force=True)

    def test_create_verify_webhook(self):
        _keys()
        inv = _invoice(750)
        try:
            t = FakeTransport([{"customers": {"id": "CU1"}}])
            out = GoCardlessAdapter().create_payment(inv.name, "GBP", transport=t)
            self.assertEqual(out["customer_id"], "CU1")
            self.assertIn("api-sandbox.gocardless.com", t.calls[0]["url"])
            self.assertTrue(t.calls[0]["auth"].startswith("Bearer "))
            self.assertIn("@", t.calls[0]["body"]["customers"]["email"])

            t = FakeTransport([{"payments": {"id": "PM1", "status": "confirmed"}}])
            self.assertTrue(GoCardlessAdapter().verify_payment({"id": "PM1"}, transport=t)["verified"])

            t = FakeTransport([{"payments": {"id": "PM1", "status": "failed"}}])
            self.assertRaises(
                frappe.ValidationError, GoCardlessAdapter().verify_payment, {"id": "PM1"}, t
            )

            raw = '{"events":[{"id":"EV1","resource_type":"payments","action":"confirmed"}]}'
            sig = hmac.new(b"whsec", raw.encode(), hashlib.sha256).hexdigest()
            out = GoCardlessAdapter().handle_webhook(
                {"_raw_body": raw, "events": [{"id": "EV1", "resource_type": "payments", "action": "confirmed"}]},
                {"Webhook-Signature": sig},
            )
            self.assertTrue(out["verified"])
            self.assertEqual(out["type"], "payments.confirmed")
        finally:
            _clearkeys()
            frappe.delete_doc("Hosting Invoice", inv.name, ignore_permissions=True, force=True)

    def test_refund_and_saved_charge(self):
        _keys()
        inv = _invoice(200)
        try:
            txn = frappe.get_doc(
                {
                    "doctype": "Payment Transaction",
                    "invoice": inv.name,
                    "gateway": "GoCardless",
                    "gateway_txn_id": "PM0",
                    "amount": 200,
                    "status": "Success",
                }
            ).insert(ignore_permissions=True)
            try:
                t = FakeTransport([{"refunds": {"id": "RF1"}}])
                out = GoCardlessAdapter().refund_payment(txn.name, 200, transport=t)
                self.assertEqual(out["refund_id"], "RF1")
                self.assertEqual(t.calls[0]["body"]["refunds"]["links"], {"payment": "PM0"})

                method = frappe.get_doc(
                    {"doctype": "Saved Payment Method", "customer": inv.customer, "gateway": "GoCardless", "token": "MD1", "default_method": 1}
                ).insert(ignore_permissions=True)
                try:
                    t = FakeTransport([{"payments": {"id": "PM2", "status": "pending_submission"}}])
                    out = GoCardlessAdapter().charge_saved_method(method.name, inv.name, "GBP", transport=t)
                    self.assertEqual(out["charged"], "PM2")
                    self.assertEqual(t.calls[0]["body"]["payments"]["amount"], 20000)
                    self.assertEqual(t.calls[0]["body"]["payments"]["links"], {"mandate": "MD1"})
                finally:
                    frappe.delete_doc("Saved Payment Method", method.name, ignore_permissions=True, force=True)
            finally:
                frappe.delete_doc("Payment Transaction", txn.name, ignore_permissions=True, force=True)
        finally:
            _clearkeys()
            frappe.delete_doc("Hosting Invoice", inv.name, ignore_permissions=True, force=True)
