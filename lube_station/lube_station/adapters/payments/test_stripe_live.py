"""Live Stripe adapter tests. SDK surface is faked; no network happens."""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from lube_station.lube_station.adapters.payments.stripe import StripeAdapter

try:
    import stripe  # noqa: F401

    HAS_STRIPE = True
except ImportError:
    HAS_STRIPE = False

CALLS = []


class FakePI:
    @staticmethod
    def create(params):
        CALLS.append(("pi.create", params))
        return {"id": "pi_live_1", "status": "succeeded"}

    @staticmethod
    def retrieve(pid):
        return {"id": pid, "status": "succeeded"}


class FakeRefund:
    @staticmethod
    def create(params):
        CALLS.append(("refund.create", params))
        return {"id": "re_live_1"}


class FakePM:
    @staticmethod
    def retrieve(token):
        return {"id": token}


class FakeWebhook:
    @staticmethod
    def construct_event(raw, sig, secret):
        if sig != "good":
            raise ValueError("bad signature")
        return {"id": "evt_1", "type": "payment_intent.succeeded"}


def _invoice(amount=300):
    cust = frappe.db.get_value("Hosting Customer", {"user": "Administrator"}, "name")
    if not cust:
        cust = frappe.get_doc({"doctype": "Hosting Customer", "user": "Administrator", "status": "Active"}).insert().name
    return frappe.get_doc(
        {
            "doctype": "Hosting Invoice",
            "customer": cust,
            "invoice_items": [{"description": "stripe", "amount": amount}],
            "status": "Unpaid",
        }
    ).insert(ignore_permissions=True)


class FakeSettings:
    api_key = "pk_test_x"

    def get_password(self, fieldname=None, raise_exception=True):
        return "sk_test_x"

    def get(self, key, default=None):
        return default


class TestStripeLiveAdapter(IntegrationTestCase):
    def _patched(self):
        return (
            patch("stripe.PaymentIntent", FakePI),
            patch("stripe.Refund", FakeRefund),
            patch("stripe.PaymentMethod", FakePM),
            patch(
                "lube_station.lube_station.adapters.payments.stripe._settings",
                lambda: FakeSettings(),
            ),
        )

    def _run(self, fn):
        if not HAS_STRIPE:
            self.skipTest("stripe library not installed")
        CALLS.clear()
        patches = self._patched()
        for p in patches:
            p.start()
        try:
            return fn()
        finally:
            for p in patches:
                p.stop()

    def test_create_payment_uses_cents(self):
        inv = _invoice(300)
        try:
            out = self._run(lambda: StripeAdapter().create_payment(inv.name))
            self.assertEqual(out["payment_intent"], "pi_live_1")
            self.assertEqual(CALLS[0][1]["amount"], 30000)
            self.assertEqual(CALLS[0][1]["metadata"], {"invoice": inv.name})
        finally:
            frappe.delete_doc("Hosting Invoice", inv.name, ignore_permissions=True, force=True)

    def test_verify_and_refund(self):
        out = self._run(lambda: StripeAdapter().verify_payment({"id": "pi_live_1"}))
        self.assertTrue(out["verified"])
        inv = _invoice(100)
        try:
            txn = frappe.get_doc(
                {
                    "doctype": "Payment Transaction",
                    "invoice": inv.name,
                    "gateway": "Stripe",
                    "gateway_txn_id": "pi_live_0",
                    "amount": 100,
                    "status": "Success",
                }
            ).insert(ignore_permissions=True)
            try:
                out = self._run(lambda: StripeAdapter().refund_payment(txn.name, 100))
                self.assertEqual(out["refund_id"], "re_live_1")
                self.assertEqual(CALLS[0][1], {"payment_intent": "pi_live_0", "amount": 10000})
            finally:
                frappe.delete_doc("Payment Transaction", txn.name, ignore_permissions=True, force=True)
        finally:
            frappe.delete_doc("Hosting Invoice", inv.name, ignore_permissions=True, force=True)

    def test_webhook_verified_flag(self):
        # No webhook-secret field on Stripe Settings: envelope parses,
        # flagged unverified. Signature path activates once configured.
        out = self._run(
            lambda: StripeAdapter().handle_webhook({"id": "evt_1", "type": "x"}, {"Stripe-Signature": "s"})
        )
        self.assertFalse(out["verified"])
        self.assertEqual(out["event_id"], "evt_1")
