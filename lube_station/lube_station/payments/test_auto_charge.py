import frappe
from frappe.tests import IntegrationTestCase

from lube_station.lube_station.adapters.seed import seed
from lube_station.lube_station.payments.methods import auto_charge_invoice


class TestAutoCharge(IntegrationTestCase):
    def test_auto_charge(self):
        seed()
        cust = frappe.get_doc({"doctype": "Hosting Customer", "user": "Administrator", "status": "Active"}).insert()
        method = frappe.get_doc({"doctype": "Saved Payment Method", "customer": cust.name, "gateway": "Stripe", "token": "tok_123", "default_method": 1, "last_four": "4242"}).insert()
        inv = frappe.get_doc({"doctype": "Hosting Invoice", "customer": cust.name, "invoice_items": [{"description": "t", "amount": 60}], "status": "Unpaid"}).insert()
        out = auto_charge_invoice(inv.name)
        self.assertEqual(out["action"], "charged")
        self.assertEqual(frappe.db.get_value("Hosting Invoice", inv.name, "status"), "Paid")
        self.assertEqual(frappe.get_doc("Saved Payment Method", method.name).get_password("token"), "tok_123")
