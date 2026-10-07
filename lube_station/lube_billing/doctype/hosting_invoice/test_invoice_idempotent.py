import frappe
from frappe.tests import IntegrationTestCase

from lube_station.lube_billing.doctype.hosting_invoice.hosting_invoice import generate_invoice
from lube_station.lube_customers.doctype.order.order import place_order


class TestInvoiceIdempotent(IntegrationTestCase):
    def test_invoice_idempotent(self):
        cust = frappe.get_doc({"doctype": "Hosting Customer", "user": "Administrator", "status": "Active"}).insert()
        group = frappe.get_doc({"doctype": "Product Group", "group_name": "Inv Group"}).insert()
        plan = frappe.get_doc({"doctype": "Hosting Plan", "plan_name": "Inv Plan", "product_group": group.name, "product_type": "Shared Hosting", "is_active": 1}).insert()
        frappe.get_doc({"doctype": "Plan Pricing", "hosting_plan": plan.name, "billing_cycle": "Monthly", "recurring_amount": 80}).insert()
        cart = frappe.get_doc({"doctype": "Cart", "customer": cust.name, "session_id": "inv-1"}).insert()
        cart.append("items", {"item_type": "Hosting Plan", "hosting_plan": plan.name, "billing_cycle": "Monthly", "quantity": 1})
        cart.save()
        out = place_order(cart.name, cust.name)
        first = generate_invoice(out["order"])
        second = generate_invoice(out["order"])
        self.assertEqual(first["invoice"], second["invoice"])
        self.assertTrue(second["reused"])
