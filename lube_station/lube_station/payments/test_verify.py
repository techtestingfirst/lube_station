from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from lube_station.lube_station.payments.verify import verify_razorpay_payment


def _customer():
    name = frappe.db.get_value("Hosting Customer", {"user": "Administrator"}, "name")
    if name:
        return frappe.get_doc("Hosting Customer", name)
    return frappe.get_doc({"doctype": "Hosting Customer", "user": "Administrator", "status": "Active"}).insert()


class TestVerifyRazorpay(IntegrationTestCase):
    def setUp(self):
        super().setUp()
        if not frappe.db.exists("DocType", "Razorpay Settings"):
            self.skipTest("Razorpay Settings (payments app) not installed")
        try:
            import razorpay  # noqa: F401
        except ImportError:
            import sys
            import types

            fake = types.ModuleType("razorpay")
            fake.Client = object
            sys.modules["razorpay"] = fake

    def _invoice(self, cust_name, amount=80):
        return frappe.get_doc(
            {
                "doctype": "Hosting Invoice",
                "customer": cust_name,
                "invoice_items": [{"description": "x", "amount": amount}],
                "status": "Unpaid",
            }
        ).insert(ignore_permissions=True)

    def _log_order(self, inv_name, order_id="order_verify_1"):
        import json

        return frappe.get_doc(
            {
                "doctype": "Integration Request",
                "integration_request_service": "Razorpay",
                "status": "Queued",
                "data": json.dumps(
                    {
                        "reference_doctype": "Hosting Invoice",
                        "reference_docname": inv_name,
                        "order_id": order_id,
                        "amount": 80,
                    }
                ),
            }
        ).insert(ignore_permissions=True)

    def test_pending_without_order(self):
        cust = _customer()
        inv = self._invoice(cust.name)
        out = verify_razorpay_payment(inv.name)
        self.assertEqual(out["status"], "pending")

    def test_paid_when_captured(self):
        cust = _customer()
        inv = self._invoice(cust.name)
        self._log_order(inv.name)

        class FakeOrders:
            def payments(self, order_id):
                assert order_id == "order_verify_1"
                return {"items": [{"id": "pay_verify_1", "status": "captured"}]}

        class FakeClient:
            def __init__(self, auth=None):
                self.order = FakeOrders()

        with patch("razorpay.Client", FakeClient):
            out = verify_razorpay_payment(inv.name)

        self.assertEqual(out["status"], "paid")
        self.assertEqual(frappe.db.get_value("Hosting Invoice", inv.name, "status"), "Paid")
        self.assertTrue(frappe.db.exists("Payment Transaction", {"gateway_txn_id": "pay_verify_1"}))

    def test_pending_when_nothing_captured(self):
        cust = _customer()
        inv = self._invoice(cust.name)
        self._log_order(inv.name, "order_verify_empty")

        class FakeOrders:
            def payments(self, order_id):
                return {"items": [{"id": "pay_x", "status": "failed"}]}

        class FakeClient:
            def __init__(self, auth=None):
                self.order = FakeOrders()

        with patch("razorpay.Client", FakeClient):
            out = verify_razorpay_payment(inv.name)

        self.assertEqual(out["status"], "pending")
        self.assertEqual(frappe.db.get_value("Hosting Invoice", inv.name, "status"), "Unpaid")
