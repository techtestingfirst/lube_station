"""Live PayU adapter tests. Transport is faked; no network happens."""

import frappe
from frappe.tests import IntegrationTestCase

from lube_station.lube_station.adapters.payments.payu import (
    PayUIndiaAdapter,
    _command_hash,
    _payment_hash,
    _return_hash,
)


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

    def __call__(self, url, headers, body, timeout):
        import urllib.parse

        self.calls.append({"url": url, "params": dict(urllib.parse.parse_qsl(body))})
        item = self.bodies.pop(0) if len(self.bodies) > 1 else self.bodies[0]
        if isinstance(item, Exception):
            raise item
        return item


def _keys():
    frappe.db.set_single_value("Lube Station Settings", "payu_merchant_key", "testkey")
    frappe.db.set_single_value("Lube Station Settings", "payu_merchant_salt", "testsalt")
    frappe.db.set_single_value("Lube Station Settings", "payu_sandbox", 1)


def _clearkeys():
    frappe.db.set_single_value("Lube Station Settings", "payu_merchant_key", "")
    frappe.db.set_single_value("Lube Station Settings", "payu_merchant_salt", "")


def _invoice(amount=700):
    cust = frappe.db.get_value("Hosting Customer", {"user": "Administrator"}, "name")
    if not cust:
        cust = frappe.get_doc({"doctype": "Hosting Customer", "user": "Administrator", "status": "Active"}).insert().name
    return frappe.get_doc(
        {
            "doctype": "Hosting Invoice",
            "customer": cust,
            "invoice_items": [{"description": "payu", "amount": amount}],
            "status": "Unpaid",
        }
    ).insert(ignore_permissions=True)


class TestPayULiveAdapter(IntegrationTestCase):
    def test_hash_vectors(self):
        self.assertEqual(len(_command_hash("k", "verify_payment", "t", "s")), 128)
        self.assertEqual(_command_hash("k", "c", "v", "s"), _command_hash("k", "c", "v", "s"))
        self.assertNotEqual(_command_hash("k", "c", "v", "s"), _command_hash("k", "c", "w", "s"))
        self.assertEqual(len(_payment_hash("k", "t", 100, "p", "n", "e@x", "s")), 128)
        payload = {"status": "success", "email": "e@x", "firstname": "n", "productinfo": "p",
                   "amount": "100.00", "txnid": "t"}
        self.assertEqual(_return_hash(payload, "s", "k"), _return_hash(payload, "s", "k"))
        payload["status"] = "failure"
        self.assertNotEqual(
            _return_hash({**payload, "status": "failure"}, "s", "k"),
            _return_hash({**payload, "status": "success"}, "s", "k"),
        )

    def test_create_verify_refund(self):
        _keys()
        inv = _invoice(700)
        try:
            out = PayUIndiaAdapter().create_payment(inv.name)
            self.assertIn("test.payu.in/_payment", out["post_url"])
            self.assertEqual(out["params"]["txnid"], inv.name)
            self.assertEqual(len(out["params"]["hash"]), 128)

            t = FakeTransport([FakeResp({"status": "1", "transaction_details": {inv.name: {"status": "success", "mihpayid": "m1"}}})])
            verified = PayUIndiaAdapter().verify_payment({"txnid": inv.name}, transport=t)
            self.assertEqual(verified["gateway_reference"], "m1")
            self.assertEqual(t.calls[0]["params"]["command"], "verify_payment")

            t = FakeTransport([FakeResp({"status": "1", "msg": "ok"})])
            txn = frappe.get_doc(
                {
                    "doctype": "Payment Transaction",
                    "invoice": inv.name,
                    "gateway": "PayU India",
                    "gateway_txn_id": "m1",
                    "amount": 700,
                    "status": "Success",
                }
            ).insert(ignore_permissions=True)
            try:
                t = FakeTransport([FakeResp({"status": "1", "msg": "ok"})])
                out = PayUIndiaAdapter().refund_payment(txn.name, 700, transport=t)
                self.assertEqual(t.calls[0]["params"]["var1"], "m1")
                self.assertEqual(t.calls[0]["params"]["command"], "cancel_refund_transaction")
            finally:
                frappe.delete_doc("Payment Transaction", txn.name, ignore_permissions=True, force=True)
        finally:
            _clearkeys()
            frappe.delete_doc("Hosting Invoice", inv.name, ignore_permissions=True, force=True)

    def test_return_handler(self):
        from lube_station.lube_station.payments.methods import payu_return

        _keys()
        inv = _invoice(50)
        try:
            payload = {"status": "success", "email": "e@x", "firstname": "n",
                       "productinfo": f"Hosting Invoice {inv.name}", "amount": "50.00", "txnid": inv.name}
            payload["hash"] = _return_hash(payload, "testsalt", "testkey")
            out = payu_return(**payload)
            self.assertEqual(out["status"], "success")
            self.assertEqual(frappe.db.get_value("Hosting Invoice", inv.name, "status"), "Paid")

            bad = dict(payload, hash="0" * 128)
            self.assertRaises(frappe.ValidationError, payu_return, **bad)
        finally:
            _clearkeys()
            frappe.delete_doc("Hosting Invoice", inv.name, ignore_permissions=True, force=True)
