import frappe
from frappe.tests import IntegrationTestCase


class TestHostingPlan(IntegrationTestCase):
    def test_hosting_plan(self):
        group = frappe.get_doc({"doctype": "Product Group", "group_name": "Plan Test Group"}).insert()
        schema = frappe.get_doc(
            {"doctype": "Product Type Schema", "schema_name": "Plan-Test-Schema", "product_type": "Shared Hosting"}
        ).insert()
        plan = frappe.get_doc(
            {
                "doctype": "Hosting Plan",
                "plan_name": "Starter Shared",
                "product_group": group.name,
                "product_type": "Shared Hosting",
                "product_type_schema": schema.name,
                "is_active": 1,
            }
        ).insert()
        price = frappe.get_doc(
            {"doctype": "Plan Pricing", "hosting_plan": plan.name, "billing_cycle": "Monthly", "recurring_amount": 100}
        ).insert()
        self.assertTrue(frappe.db.exists("Hosting Plan", plan.name))
        self.assertTrue(frappe.db.exists("Plan Pricing", price.name))
