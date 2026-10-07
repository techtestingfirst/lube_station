import frappe
from frappe.tests import IntegrationTestCase

from lube_station.lube_station.portal import apis


class TestWhmcsFlow(IntegrationTestCase):
    def _setup(self):
        cust_name = frappe.db.get_value("Hosting Customer", {"user": "Administrator"}, "name")
        if not cust_name:
            cust_name = frappe.get_doc(
                {"doctype": "Hosting Customer", "user": "Administrator", "status": "Active", "tos_accepted": 1}
            ).insert().name
        else:
            frappe.db.set_value("Hosting Customer", cust_name, "tos_accepted", 1)
        group = frappe.db.get_value("Product Group", {"group_name": "Flow Group"}, "name") or frappe.get_doc(
            {"doctype": "Product Group", "group_name": "Flow Group"}
        ).insert().name
        plan = frappe.db.get_value("Hosting Plan", {"plan_name": "Flow Plan"}, "name")
        if not plan:
            plan = frappe.get_doc(
                {
                    "doctype": "Hosting Plan",
                    "plan_name": "Flow Plan",
                    "product_group": group,
                    "product_type": "Shared Hosting",
                    "is_active": 1,
                }
            ).insert().name
        if not frappe.db.exists("Plan Pricing", {"hosting_plan": plan, "billing_cycle": "Monthly"}):
            frappe.get_doc(
                {"doctype": "Plan Pricing", "hosting_plan": plan, "billing_cycle": "Monthly", "recurring_amount": 50}
            ).insert()
        return cust_name, plan

    def test_configure_domain_cart_notes(self):
        cust_name, plan = self._setup()
        cart = apis.cart_add(hosting_plan=plan, billing_cycle="Monthly", quantity=2)
        row = cart["items"][-1]["row"]
        self.assertEqual(cart["items"][-1]["quantity"], 2)
        cart = apis.cart_set_domain(cart=cart["cart"], row=row, domain="flowexample.com", domain_action="own")
        self.assertEqual(cart["items"][-1]["domain"], "flowexample.com")

    def test_checkout_notes_and_fulfillment(self):
        from lube_station.lube_customers.doctype.order.order import place_order

        cust_name, plan = self._setup()
        cart = apis.cart_add(hosting_plan=plan, billing_cycle="Monthly", quantity=1)
        out = place_order(cart["cart"], cust_name, "Please provision fast")
        order = frappe.get_doc("Order", out["order"])
        self.assertEqual(order.customer_notes, "Please provision fast")
        self.assertGreaterEqual(order.fraud_score, 0)
        inv = frappe.get_doc(
            {
                "doctype": "Hosting Invoice",
                "customer": cust_name,
                "order_ref": order.name,
                "invoice_items": [{"description": "x", "amount": 50}],
                "status": "Unpaid",
            }
        ).insert(ignore_permissions=True)
        frappe.flags.data = {"razorpay_payment_id": "pay_flow_whmcs"}
        inv.on_payment_authorized("Completed")
        self.assertEqual(frappe.db.get_value("Order", order.name, "status"), "Accepted")
        self.assertTrue(frappe.db.exists("Service", {"order_ref": order.name, "status": "Active"}))
