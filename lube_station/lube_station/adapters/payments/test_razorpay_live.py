"""Live Razorpay adapter tests. SDK client is faked; no network happens."""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from lube_station.lube_station.adapters.payments.razorpay import RazorpayAdapter


class _Orders:
    def __init__(self, calls):
        self.calls = calls

    def create(self, data):
        self.calls.append(("order.create", data))
        return {"id": "order_live_1", "amount": data["amount"]}


class _Payments:
    def __init__(self, calls):
        self.calls = calls

    def createRecurring(self, data):
        self.calls.append(("payment.createRecurring", data))
        return {"id": "pay_live_1"}


class _Refunds:
    def __init__(self, calls):
        self.calls = calls

    def create(self, data):
        self.calls.append(("refund.create", data))
        return {"id": "rfnd_live_1"}


class _Utility:
    def verify_payment_signature(self, data):
        from razorpay.errors import SignatureVerificationError

        if data["razorpay_signature"] != "good":
            raise SignatureVerificationError("bad")
        return True

    def verify_webhook_signature(self, body, signature, secret):
        from razorpay.errors import SignatureVerificationError

        if signature != "good":
            raise SignatureVerificationError("bad")
        return True


class FakeClient:
    def __init__(self, calls, auth=None):
        self.calls = calls
        self.auth = auth or ("key", "secret")
        self.order = _Orders(calls)
        self.payment = _Payments(calls)
        self.refund = _Refunds(calls)
        self.utility = _Utility()


def _invoice(amount=250):
    cust = frappe.db.get_value("Hosting Customer", {"user": "Administrator"}, "name")
    if not cust:
        cust = frappe.get_doc({"doctype": "Hosting Customer", "user": "Administrator", "status": "Active"}).insert().name
    return frappe.get_doc(
        {
            "doctype": "Hosting Invoice",
            "customer": cust,
            "invoice_items": [{"description": "rzp", "amount": amount}],
            "status": "Unpaid",
        }
    ).insert(ignore_permissions=True)


class TestRazorpayLiveAdapter(IntegrationTestCase):
    def _patched(self, calls):
        return patch("razorpay.Client", lambda auth=None: FakeClient(calls, auth))

    def _require_settings(self):
        if not (
            frappe.db.exists("DocType", "Razorpay Settings")
            and frappe.db.exists("Razorpay Settings", "Razorpay Settings")
        ):
            self.skipTest("Razorpay Settings not configured")

    def test_create_payment_uses_paise(self):
        self._require_settings()
        inv = _invoice(250)
        calls = []
        try:
            with self._patched(calls):
                out = RazorpayAdapter().create_payment(inv.name)
            self.assertEqual(out["order_id"], "order_live_1")
            self.assertEqual(calls[0][1]["amount"], 25000)
            self.assertEqual(calls[0][1]["receipt"], inv.name[:40])
        finally:
            frappe.delete_doc("Hosting Invoice", inv.name, ignore_permissions=True, force=True)

    def test_verify_payment_signature(self):
        self._require_settings()
        with self._patched([]):
            out = RazorpayAdapter().verify_payment(
                {"razorpay_order_id": "o", "razorpay_payment_id": "p", "razorpay_signature": "good"}
            )
        self.assertTrue(out["verified"])
        with self._patched([]):
            self.assertRaises(Exception, RazorpayAdapter().verify_payment, {"razorpay_signature": "bad"})

    def test_webhook_signature(self):
        self._require_settings()
        settings = frappe.get_doc("Razorpay Settings", "Razorpay Settings")
        had = settings.get_password(fieldname="webhook_secret", raise_exception=False)
        settings.set("webhook_secret", "testsecret")
        settings.save(ignore_permissions=True)
        try:
            with self._patched([]):
                out = RazorpayAdapter().handle_webhook(
                    {"id": "evt_1", "event": "payment.captured", "_raw_body": "body"},
                    {"X-Razorpay-Signature": "good"},
                )
            self.assertEqual(out["event_id"], "evt_1")
            with self._patched([]):
                self.assertRaises(
                    Exception,
                    RazorpayAdapter().handle_webhook,
                    {"id": "evt_1", "_raw_body": "body"},
                    {"X-Razorpay-Signature": "bad"},
                )
        finally:
            settings.set("webhook_secret", had or "")
            settings.save(ignore_permissions=True)

    def test_refund_and_charge(self):
        self._require_settings()
        inv = _invoice(100)
        calls = []
        try:
            txn = frappe.get_doc(
                {
                    "doctype": "Payment Transaction",
                    "invoice": inv.name,
                    "gateway": "Razorpay",
                    "gateway_txn_id": "pay_live_0",
                    "amount": 100,
                    "status": "Success",
                }
            ).insert(ignore_permissions=True)
            try:
                with self._patched(calls):
                    out = RazorpayAdapter().refund_payment(txn.name, 100)
                self.assertEqual(out["refund_id"], "rfnd_live_1")
                self.assertEqual(calls[0][1], {"payment_id": "pay_live_0", "amount": 10000})
            finally:
                frappe.delete_doc("Payment Transaction", txn.name, ignore_permissions=True, force=True)
        finally:
            frappe.delete_doc("Hosting Invoice", inv.name, ignore_permissions=True, force=True)
