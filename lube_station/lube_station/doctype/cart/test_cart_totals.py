import frappe
from frappe.tests import IntegrationTestCase


class TestCartTotals(IntegrationTestCase):
    def test_cart_totals(self):
        group = frappe.get_doc({"doctype": "Product Group", "group_name": "Cart Group"}).insert()
        plan = frappe.get_doc({"doctype": "Hosting Plan", "plan_name": "Cart Plan", "product_group": group.name, "product_type": "Shared Hosting", "is_active": 1}).insert()
        frappe.get_doc({"doctype": "Plan Pricing", "hosting_plan": plan.name, "billing_cycle": "Monthly", "recurring_amount": 100}).insert()
        cart = frappe.get_doc({"doctype": "Cart", "session_id": "sess-1"}).insert()
        cart.append("items", {"item_type": "Hosting Plan", "hosting_plan": plan.name, "billing_cycle": "Monthly", "quantity": 2})
        cart.save()
        self.assertEqual(cart.subtotal, 200)
        self.assertEqual(cart.grand_total, 200)
