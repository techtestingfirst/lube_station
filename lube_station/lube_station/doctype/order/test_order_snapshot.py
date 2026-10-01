import frappe
from frappe.tests import IntegrationTestCase

from lube_station.lube_station.doctype.order.order import place_order


class TestOrderSnapshot(IntegrationTestCase):
    def test_order_snapshot(self):
        group = frappe.get_doc({"doctype": "Product Group", "group_name": "Order Group"}).insert()
        plan = frappe.get_doc({"doctype": "Hosting Plan", "plan_name": "Order Plan", "product_group": group.name, "product_type": "Shared Hosting", "is_active": 1}).insert()
        frappe.get_doc({"doctype": "Plan Pricing", "hosting_plan": plan.name, "billing_cycle": "Monthly", "recurring_amount": 50}).insert()
        cart = frappe.get_doc({"doctype": "Cart", "session_id": "ord-1"}).insert()
        cart.append("items", {"item_type": "Hosting Plan", "hosting_plan": plan.name, "billing_cycle": "Monthly", "quantity": 1, "configuration_json": '{"domain": "x.test"}'})
        cart.save()
        out = place_order(cart.name)
        order = frappe.get_doc("Order", out["order"])
        self.assertEqual(order.status, "Pending Review")
        snap_before = order.items[0].configuration_snapshot
        cart.items[0].configuration_json = '{"domain": "changed.test"}'
        cart.save()
        order.reload()
        self.assertEqual(order.items[0].configuration_snapshot, snap_before)
