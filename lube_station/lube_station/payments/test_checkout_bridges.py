"""Checkout bridge tests for all one-time gateways. No network happens.

PayU/CCAvenue build their hosted form locally from Lube Station Settings
keys, so payment_link is exercised end to end. Cashfree/PayPal REST go
through _adapter_url with a faked transport. Mollie/PayPal REST refuse INR
by design until invoice currency lands; GoCardless/2Checkout stay out of
one-time checkout through supports_one_time = 0.
"""

import frappe
from frappe.tests import IntegrationTestCase

from lube_station.lube_station.adapters.seed import seed
from lube_station.lube_station.payments.links import _adapter_url, payment_link
from lube_station.lube_station.tests.helpers import make_customer


class FakeResp:
    def __init__(self, body, status_code=200):
        self._body = body
        self.status_code = status_code

    def json(self):
        return self._body


def _invoice():
    cust = make_customer()
    return frappe.get_doc(
        {
            "doctype": "Hosting Invoice",
            "customer": cust,
            "invoice_items": [{"description": "bridge", "amount": 700}],
            "status": "Unpaid",
        }
    ).insert(ignore_permissions=True)


def _activate(name):
    frappe.db.set_value("Payment Gateway Adapter", name, "active", 1)


class TestCheckoutBridges(IntegrationTestCase):
    def setUp(self):
        super().setUp()
        seed()
        self._was_active = {
            name: frappe.db.get_value("Payment Gateway Adapter", name, "active")
            for name in ("PayU India", "CCAvenue", "Cashfree Payments", "Mollie", "PayPal Checkout")
            if frappe.db.exists("Payment Gateway Adapter", name)
        }
        self.addCleanup(self._restore)

    def _restore(self):
        for name, active in self._was_active.items():
            frappe.db.set_value("Payment Gateway Adapter", name, "active", active)
        for key in (
            "payu_merchant_key",
            "payu_merchant_salt",
            "ccavenue_merchant_id",
            "ccavenue_access_code",
            "ccavenue_working_key",
            "cashfree_app_id",
            "cashfree_secret_key",
        ):
            frappe.db.set_single_value("Lube Station Settings", key, "")

    def test_payu_form_post_shape(self):
        frappe.db.set_single_value("Lube Station Settings", "payu_merchant_key", "testkey")
        frappe.db.set_single_value("Lube Station Settings", "payu_merchant_salt", "testsalt")
        _activate("PayU India")
        out = payment_link(_invoice().name, gateway="PayU India")
        self.assertIn("payu", out["post_url"])
        self.assertEqual(out["params"]["key"], "testkey")
        self.assertIn("hash", out["params"])

    def test_ccavenue_encrypted_shape(self):
        frappe.db.set_single_value("Lube Station Settings", "ccavenue_merchant_id", "mid")
        frappe.db.set_single_value("Lube Station Settings", "ccavenue_access_code", "ac")
        frappe.db.set_single_value("Lube Station Settings", "ccavenue_working_key", "0123456789abcdef0123456789abcdef")
        _activate("CCAvenue")
        out = payment_link(_invoice().name, gateway="CCAvenue")
        self.assertIn("ccavenue", out["post_url"])
        self.assertTrue(out["enc_request"])
        self.assertEqual(out["access_code"], "ac")

    def test_cashfree_session_shape(self):
        frappe.db.set_single_value("Lube Station Settings", "cashfree_app_id", "app")
        frappe.db.set_single_value("Lube Station Settings", "cashfree_secret_key", "sec")
        _activate("Cashfree Payments")

        def fake(method, url, headers, body, timeout):
            return FakeResp({"order_id": "cf1", "payment_session_id": "sess_abc"})

        inv = frappe.get_doc("Hosting Invoice", _invoice().name)
        out = _adapter_url(inv, "Cashfree Payments", transport=fake)
        self.assertEqual(out["payment_session_id"], "sess_abc")
        self.assertEqual(out["order_id"], "cf1")
        self.assertIn("sandbox", out)

    def test_approve_url_normalizes_to_redirect(self):
        # Mollie/PayPal REST return approve_url; the bridge maps it to the
        # portal redirect shape. Stubbed adapter, no network, no settings.
        from unittest.mock import patch

        from lube_station.lube_station.adapters import registry as reg

        class Stub:
            def create_payment(self, invoice):
                return {"gateway": "X", "invoice": invoice, "order_id": "O1", "approve_url": "https://pay/appr"}

        inv = frappe.get_doc("Hosting Invoice", _invoice().name)
        with patch.object(reg, "get_payment_adapter", return_value=Stub()):
            out = _adapter_url(inv, "PayPal Checkout")
        self.assertEqual(out["url"], "https://pay/appr")
        self.assertEqual(out["gateway"], "PayPal Checkout")

    def test_mollie_refuses_inr(self):
        frappe.db.set_single_value("Lube Station Settings", "mollie_secret_key", "test_x")
        _activate("Mollie")
        inv = frappe.get_doc("Hosting Invoice", _invoice().name)
        self.assertRaises(frappe.ValidationError, _adapter_url, inv, "Mollie")

    def test_mandate_and_panel_gateways_stay_out(self):
        inv = _invoice().name
        self.assertRaises(frappe.ValidationError, payment_link, inv, gateway="GoCardless")
        self.assertRaises(frappe.ValidationError, payment_link, inv, gateway="2Checkout / Verifone")
