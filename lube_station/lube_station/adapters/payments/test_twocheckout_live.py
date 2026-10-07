"""Live 2Checkout adapter tests. Transport is faked; no network happens."""

import frappe
from frappe.tests import IntegrationTestCase

from lube_station.lube_station.adapters.payments.twocheckout import TwoCheckoutAdapter, auth_header


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
        self.calls.append({"method": method, "url": url, "auth": headers.get("X-Avangate-Authentication", ""), "body": parsed})
        item = self.bodies.pop(0) if len(self.bodies) > 1 else self.bodies[0]
        if isinstance(item, Exception):
            raise item
        return item if isinstance(item, FakeResp) else FakeResp(item)


def _keys():
    frappe.db.set_single_value("Lube Station Settings", "twocheckout_merchant_code", "TESTCODE")
    frappe.db.set_single_value("Lube Station Settings", "twocheckout_secret_key", "testsecret")
    frappe.db.set_single_value("Lube Station Settings", "twocheckout_sandbox", 1)


def _clearkeys():
    frappe.db.set_single_value("Lube Station Settings", "twocheckout_merchant_code", "")
    frappe.db.set_single_value("Lube Station Settings", "twocheckout_secret_key", "")


class TestTwoCheckoutLiveAdapter(IntegrationTestCase):
    def test_auth_header_shape(self):
        parts = auth_header("TESTCODE", "s", "2020-06-18 08:05:46")
        self.assertEqual(parts["code"], "TESTCODE")
        self.assertEqual(parts["algo"], "sha256")
        self.assertEqual(len(parts["hash"]), 64)
        import hashlib
        import hmac

        raw = f"{len('TESTCODE')}TESTCODE{len('2020-06-18 08:05:46')}2020-06-18 08:05:46"
        self.assertEqual(parts["hash"], hmac.new(b"s", raw.encode(), hashlib.sha256).hexdigest())

    def test_verify_and_webhook(self):
        _keys()
        try:
            t = FakeTransport([{"RefNo": "R1", "Status": "COMPLETE", "ApproveStatus": "OK"}])
            out = TwoCheckoutAdapter().verify_payment({"order_reference": "R1"}, transport=t)
            self.assertTrue(out["verified"])
            self.assertIn('code="TESTCODE"', t.calls[0]["auth"])
            self.assertIn("/rest/6.0/orders/R1/", t.calls[0]["url"])

            t = FakeTransport([{"RefNo": "R1", "Status": "PENDING"}])
            self.assertRaises(
                frappe.ValidationError, TwoCheckoutAdapter().verify_payment, {"id": "R1"}, t
            )

            out = TwoCheckoutAdapter().handle_webhook({"sale_id": "S1", "message_type": "ORDER_CREATED"}, {})
            self.assertFalse(out["verified"])
            self.assertEqual(out["event_id"], "S1")
        finally:
            _clearkeys()

    def test_refund_via_rpc(self):
        _keys()
        try:
            t = FakeTransport([{"result": "sess_1"}, {"result": True}])
            out = TwoCheckoutAdapter()._session(transport=t)
            self.assertEqual(out, "sess_1")
            self.assertIn("/rpc/6.0/", t.calls[0]["url"])
            self.assertEqual(t.calls[0]["body"]["method"], "login")

            cust = frappe.db.get_value("Hosting Customer", {"user": "Administrator"}, "name")
            if not cust:
                cust = frappe.get_doc({"doctype": "Hosting Customer", "user": "Administrator", "status": "Active"}).insert().name
            inv = frappe.get_doc(
                {
                    "doctype": "Hosting Invoice",
                    "customer": cust,
                    "invoice_items": [{"description": "tco", "amount": 50}],
                    "status": "Unpaid",
                }
            ).insert(ignore_permissions=True)
            try:
                txn = frappe.get_doc(
                    {
                        "doctype": "Payment Transaction",
                        "invoice": inv.name,
                        "gateway": "2Checkout / Verifone",
                        "gateway_txn_id": "R1",
                        "amount": 50,
                        "status": "Success",
                    }
                ).insert(ignore_permissions=True)
                try:
                    t = FakeTransport([{"result": "sess_1"}, {"result": True}])
                    out = TwoCheckoutAdapter().refund_payment(txn.name, 50, transport=t)
                    rpc_call = t.calls[1]
                    self.assertEqual(rpc_call["body"]["method"], "issueRefund")
                    self.assertEqual(rpc_call["body"]["params"][1], "R1")
                finally:
                    frappe.delete_doc("Payment Transaction", txn.name, ignore_permissions=True, force=True)
            finally:
                frappe.delete_doc("Hosting Invoice", inv.name, ignore_permissions=True, force=True)
        finally:
            _clearkeys()
