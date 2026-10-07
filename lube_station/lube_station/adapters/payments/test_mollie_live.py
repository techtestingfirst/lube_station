"""Live Mollie adapter tests. Transport is faked; no network happens."""

import frappe
from frappe.tests import IntegrationTestCase

from lube_station.lube_station.adapters.payments.mollie import MollieAdapter


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
    frappe.db.set_single_value("Lube Station Settings", "mollie_secret_key", "test_xxx")


def _clearkeys():
    frappe.db.set_single_value("Lube Station Settings", "mollie_secret_key", "")


def _invoice(amount=1200):
    cust = frappe.db.get_value("Hosting Customer", {"user": "Administrator"}, "name")
    if not cust:
        cust = frappe.get_doc({"doctype": "Hosting Customer", "user": "Administrator", "status": "Active"}).insert().name
    return frappe.get_doc(
        {
            "doctype": "Hosting Invoice",
            "customer": cust,
            "invoice_items": [{"description": "mollie", "amount": amount}],
            "status": "Unpaid",
        }
    ).insert(ignore_permissions=True)


class TestMollieLiveAdapter(IntegrationTestCase):
    def test_create_rejects_inr(self):
        _keys()
        inv = _invoice(1200)
        try:
            self.assertRaises(
                frappe.ValidationError,
                MollieAdapter().create_payment,
                inv.name,
                "INR",
                FakeTransport([]),
            )
        finally:
            _clearkeys()
            frappe.delete_doc("Hosting Invoice", inv.name, ignore_permissions=True, force=True)

    def test_create_verify_webhook(self):
        _keys()
        inv = _invoice(1200)
        try:
            t = FakeTransport([{"id": "tr_1", "status": "open", "_links": {"checkout": {"href": "https://mollie/pay"}}}])
            out = MollieAdapter().create_payment(inv.name, "EUR", transport=t)
            self.assertEqual(out["approve_url"], "https://mollie/pay")
            self.assertEqual(t.calls[0]["body"]["amount"], {"currency": "EUR", "value": "1200.00"})
            self.assertTrue(t.calls[0]["auth"].startswith("Bearer "))

            t = FakeTransport([{"id": "tr_1", "status": "paid"}])
            self.assertTrue(MollieAdapter().verify_payment({"id": "tr_1"}, transport=t)["verified"])

            t = FakeTransport([{"id": "tr_1", "status": "paid"}])
            out = MollieAdapter().handle_webhook({"id": "tr_1"}, {}, transport=t)
            self.assertTrue(out["verified"])

            t = FakeTransport([{"id": "tr_1", "status": "failed"}])
            out = MollieAdapter().handle_webhook({"id": "tr_1"}, {}, transport=t)
            self.assertFalse(out["verified"])
        finally:
            _clearkeys()
            frappe.delete_doc("Hosting Invoice", inv.name, ignore_permissions=True, force=True)

    def test_refund_and_saved_charge(self):
        _keys()
        inv = _invoice(300)
        try:
            txn = frappe.get_doc(
                {
                    "doctype": "Payment Transaction",
                    "invoice": inv.name,
                    "gateway": "Mollie",
                    "gateway_txn_id": "tr_0",
                    "amount": 300,
                    "status": "Success",
                }
            ).insert(ignore_permissions=True)
            try:
                t = FakeTransport([{"id": "re_1", "status": "pending"}])
                out = MollieAdapter().refund_payment(txn.name, 300, "EUR", transport=t)
                self.assertEqual(out["refund_id"], "re_1")
                self.assertIn("/payments/tr_0/refunds", t.calls[0]["url"])

                method = frappe.get_doc(
                    {"doctype": "Saved Payment Method", "customer": inv.customer, "gateway": "Mollie", "token": "cst_1", "default_method": 1}
                ).insert(ignore_permissions=True)
                try:
                    t = FakeTransport([{"id": "tr_2", "status": "paid"}])
                    out = MollieAdapter().charge_saved_method(method.name, inv.name, "EUR", transport=t)
                    self.assertEqual(out["charged"], "tr_2")
                    self.assertEqual(t.calls[0]["body"]["sequenceType"], "recurring")
                    self.assertEqual(t.calls[0]["body"]["customerId"], "cst_1")
                finally:
                    frappe.delete_doc("Saved Payment Method", method.name, ignore_permissions=True, force=True)
            finally:
                frappe.delete_doc("Payment Transaction", txn.name, ignore_permissions=True, force=True)
        finally:
            _clearkeys()
            frappe.delete_doc("Hosting Invoice", inv.name, ignore_permissions=True, force=True)
