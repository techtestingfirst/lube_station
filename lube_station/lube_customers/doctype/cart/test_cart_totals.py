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

    def test_cart_option_delta(self):
        """WHMCS Configurable Options: Select delta added to unit price server-side."""
        import json

        group = frappe.get_doc({"doctype": "Product Group", "group_name": "Cart Opt Group"}).insert()
        schema = frappe.get_doc(
            {
                "doctype": "Product Type Schema",
                "schema_name": "Cart Opt Schema",
                "product_type": "VPS",
                "fields": [
                    {
                        "field_key": "extra_disk",
                        "label": "Extra Disk",
                        "field_type": "Select",
                        "options_json": json.dumps(
                            [
                                {"label": "None", "value": "none"},
                                {"label": "Extra 50GB SSD", "value": "ssd-50", "price": 5},
                            ]
                        ),
                    }
                ],
            }
        ).insert()
        plan = frappe.get_doc(
            {
                "doctype": "Hosting Plan",
                "plan_name": "Cart Opt Plan",
                "product_group": group.name,
                "product_type": "VPS",
                "product_type_schema": schema.name,
                "is_active": 1,
            }
        ).insert()
        frappe.get_doc({"doctype": "Plan Pricing", "hosting_plan": plan.name, "billing_cycle": "Monthly", "recurring_amount": 100}).insert()
        cart = frappe.get_doc({"doctype": "Cart", "session_id": "sess-opt"}).insert()
        cart.append(
            "items",
            {
                "item_type": "Hosting Plan",
                "hosting_plan": plan.name,
                "billing_cycle": "Monthly",
                "quantity": 2,
                "configuration_json": json.dumps({"extra_disk": "ssd-50"}),
            },
        )
        cart.save()
        self.assertEqual(cart.items[0].unit_price, 105)
        self.assertEqual(cart.subtotal, 210)
