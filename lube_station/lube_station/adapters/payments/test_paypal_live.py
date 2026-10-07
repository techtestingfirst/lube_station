"""Live PayPal adapter tests. Transport is faked; no network happens."""

from contextlib import contextmanager
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from lube_station.lube_station.adapters.payments.paypal import PayPalCheckoutAdapter


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
        import urllib.parse

        try:
            parsed = json.loads(body or "{}")
        except Exception:
            parsed = dict(urllib.parse.parse_qsl(body or ""))
        self.calls.append({"method": method, "url": url, "body": parsed})
        item = self.bodies.pop(0) if len(self.bodies) > 1 else self.bodies[0]
        if isinstance(item, Exception):
            raise item
        return item


class FakeSettings:
    def get(self, key, default=None):
        return {"paypal_sandbox": 1, "api_username": "cid_test"}.get(key, default)

    def get_password(self, fieldname=None, raise_exception=True):
        return {"api_username": "cid_test", "api_password": "sec_test"}.get(fieldname)


def token_ok():
    return FakeResp({"access_token": "tok", "token_type": "Bearer"})


@contextmanager
def _live():
    from lube_station.lube_station.adapters.payments.paypal import PayPalCheckoutAdapter

    with patch.object(
        PayPalCheckoutAdapter,
        "_settings",
        lambda self: (FakeSettings(), "https://api-m.sandbox.paypal.com", "cid_test", "sec_test"),
    ):
        yield


def _invoice(amount=500):
    cust = frappe.db.get_value("Hosting Customer", {"user": "Administrator"}, "name")
    if not cust:
        cust = frappe.get_doc({"doctype": "Hosting Customer", "user": "Administrator", "status": "Active"}).insert().name
    return frappe.get_doc(
        {
            "doctype": "Hosting Invoice",
            "customer": cust,
            "invoice_items": [{"description": "pp", "amount": amount}],
            "status": "Unpaid",
        }
    ).insert(ignore_permissions=True)


class TestPayPalLiveAdapter(IntegrationTestCase):
    def test_create_rejects_inr(self):
        inv = _invoice(500)
        try:
            with _live():
                self.assertRaises(
                    frappe.ValidationError,
                    PayPalCheckoutAdapter().create_payment,
                    inv.name,
                    "INR",
                    FakeTransport([token_ok()]),
                )
        finally:
            frappe.delete_doc("Hosting Invoice", inv.name, ignore_permissions=True, force=True)

    def test_create_order_and_verify(self):
        inv = _invoice(500)
        try:
            with _live():
                t = FakeTransport(
                    [
                        token_ok(),
                        FakeResp({"id": "ord_1", "links": [{"rel": "approve", "href": "https://pp/ok"}]}),
                    ]
                )
                out = PayPalCheckoutAdapter().create_payment(inv.name, "USD", transport=t)
                self.assertEqual(out["order_id"], "ord_1")
                self.assertEqual(
                    t.calls[1]["body"]["purchase_units"][0]["amount"],
                    {"currency_code": "USD", "value": "500.00"},
                )

                t = FakeTransport([token_ok(), FakeResp({"id": "ord_1", "status": "COMPLETED"})])
                self.assertTrue(
                    PayPalCheckoutAdapter().verify_payment({"id": "ord_1"}, transport=t)["verified"]
                )

                t = FakeTransport([token_ok(), FakeResp({"id": "ord_1", "status": "APPROVED"})])
                self.assertRaises(
                    frappe.ValidationError,
                    PayPalCheckoutAdapter().verify_payment,
                    {"id": "ord_1"},
                    t,
                )
        finally:
            frappe.delete_doc("Hosting Invoice", inv.name, ignore_permissions=True, force=True)

    def test_webhook_and_refund(self):
        with _live():
            t = FakeTransport([token_ok(), FakeResp({"verification_status": "SUCCESS"})])
            out = PayPalCheckoutAdapter().handle_webhook(
                {"id": "evt_1", "event_type": "PAYMENT.CAPTURE.COMPLETED"},
                {"Webhook-Id": "wh_1", "Transmission-Id": "t", "Transmission-Time": "now",
                 "Cert-Url": "c", "Auth-Algo": "a", "Transmission-Sig": "s"},
                transport=t,
            )
            self.assertTrue(out["verified"])
            self.assertEqual(out["event_id"], "evt_1")

            out = PayPalCheckoutAdapter().handle_webhook(
                {"id": "evt_2", "event_type": "x"}, {}, transport=FakeTransport([])
            )
            self.assertFalse(out["verified"])

        inv = _invoice(200)
        try:
            txn = frappe.get_doc(
                {
                    "doctype": "Payment Transaction",
                    "invoice": inv.name,
                    "gateway": "PayPal Checkout",
                    "gateway_txn_id": "cap_1",
                    "amount": 200,
                    "status": "Success",
                }
            ).insert(ignore_permissions=True)
            try:
                with _live():
                    t = FakeTransport(
                        [
                            token_ok(),
                            FakeResp({"message": "not an order"}, 404),
                            FakeResp({"id": "re_1"}),
                        ]
                    )
                    out = PayPalCheckoutAdapter().refund_payment(txn.name, 200, "USD", transport=t)
                    self.assertEqual(out["refund_id"], "re_1")
                    self.assertIn("/v2/payments/captures/cap_1/refund", t.calls[-1]["url"])
            finally:
                frappe.delete_doc("Payment Transaction", txn.name, ignore_permissions=True, force=True)
        finally:
            frappe.delete_doc("Hosting Invoice", inv.name, ignore_permissions=True, force=True)
