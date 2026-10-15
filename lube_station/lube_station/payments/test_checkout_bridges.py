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
            for name in ("PayU India", "CCAvenue", "Cashfree Payments", "Mollie", "PayPal Checkout", "PayTM", "Braintree")
            if frappe.db.exists("Payment Gateway Adapter", name)
        }
        self.addCleanup(self._restore)

    def _restore(self):
        for name, active in self._was_active.items():
            frappe.db.set_value("Payment Gateway Adapter", name, "active", active)
        for name in ("PayTM", "Braintree"):
            if frappe.db.exists("Payment Gateway Adapter", name) and name not in self._was_active:
                frappe.db.delete("Payment Gateway Adapter", name)
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

    def _paytm_keys(self, merchant_id="mid", merchant_key="mk"):
        if not frappe.db.exists("Paytm Settings", "Paytm Settings"):
            frappe.get_doc({"doctype": "Paytm Settings"}).insert(ignore_permissions=True)
        doc = frappe.get_doc("Paytm Settings", "Paytm Settings")
        doc.merchant_id = merchant_id
        doc.merchant_key = merchant_key
        doc.save(ignore_permissions=True)

    def _braintree_keys(self):
        if not frappe.db.exists("DocType", "Braintree Settings"):
            self.skipTest("Braintree Settings (payments app) not installed")
        doc = None
        for row in frappe.get_all("Braintree Settings", ["name"]):
            doc = frappe.get_doc("Braintree Settings", row.name)
            break
        if doc is None:
            doc = frappe.get_doc({"doctype": "Braintree Settings", "gateway_name": "Test"})
            doc.flags.ignore_mandatory = True
            doc.insert(ignore_permissions=True)
        doc.merchant_id = "mid"
        doc.public_key = "pub"
        doc.private_key = "priv"
        doc.use_sandbox = 1
        doc.save(ignore_permissions=True)
        return doc

    def test_paytm_checkout_shape(self):
        self._paytm_keys()
        _activate("PayTM")
        self.addCleanup(frappe.db.set_value, "Paytm Settings", "Paytm Settings", "merchant_id", "")
        out = payment_link(_invoice().name, gateway="PayTM")
        self.assertIn("paytm_checkout", out["url"])

    def test_paytm_verify_rejects_bad_checksum(self):
        from lube_station.lube_station.adapters.payments.paytm import PaytmAdapter

        self._paytm_keys()
        out = PaytmAdapter().verify_payment({"ORDERID": "IR-1", "TXN_AMOUNT": "700.00", "CHECKSUMHASH": "bad"})
        self.assertFalse(out["verified"])
        self.assertEqual(out["gateway_reference"], "IR-1")
        self.assertRaises(frappe.ValidationError, PaytmAdapter().verify_payment, {"ORDERID": "IR-1"})

    def test_paytm_missing_keys_throws(self):
        _activate("PayTM")
        self.addCleanup(frappe.db.set_value, "Payment Gateway Adapter", "PayTM", "active", 0)
        if frappe.db.exists("Paytm Settings", "Paytm Settings"):
            frappe.db.set_value("Paytm Settings", "Paytm Settings", "merchant_id", "")
        inv = frappe.get_doc("Hosting Invoice", _invoice().name)
        self.assertRaises(frappe.ValidationError, _adapter_url, inv, "PayTM")

    def test_braintree_checkout_shape(self):
        self._braintree_keys()
        _activate("Braintree")
        out = payment_link(_invoice().name, gateway="Braintree")
        self.assertIn("braintree_checkout", out["url"])

    def test_mandate_and_panel_gateways_stay_out(self):
        inv = _invoice().name
        self.assertRaises(frappe.ValidationError, payment_link, inv, gateway="GoCardless")
        self.assertRaises(frappe.ValidationError, payment_link, inv, gateway="2Checkout / Verifone")
