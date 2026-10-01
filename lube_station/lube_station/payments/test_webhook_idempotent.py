import frappe
from frappe.tests import IntegrationTestCase

from lube_station.lube_station.payments.webhooks import handle_webhook


class TestWebhookIdempotent(IntegrationTestCase):
    def test_webhook_idempotent(self):
        cust = frappe.get_doc({"doctype": "Hosting Customer", "user": "Administrator", "status": "Active"}).insert()
        inv = frappe.get_doc({"doctype": "Hosting Invoice", "customer": cust.name, "invoice_items": [{"description": "t", "amount": 100}], "status": "Unpaid"}).insert()
        payload = {"id": "txn-1", "event": "evt-1", "invoice": inv.name, "status": "paid", "amount": 100}
        first = handle_webhook("Stripe", payload)
        second = handle_webhook("Stripe", payload)
        self.assertEqual(first["transaction"], second["transaction"])
        self.assertTrue(second["reused"])
        self.assertEqual(frappe.db.get_value("Hosting Invoice", inv.name, "status"), "Paid")
        self.assertEqual(frappe.db.count("Payment Transaction", {"gateway_txn_id": "txn-1"}), 1)
