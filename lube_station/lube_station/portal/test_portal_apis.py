import frappe
from frappe.tests import IntegrationTestCase

from lube_station.lube_station.portal import apis


class TestPortalApis(IntegrationTestCase):
    def test_portal_apis(self):
        cust = frappe.get_doc({"doctype": "Hosting Customer", "user": "Administrator", "status": "Active"}).insert()
        group = frappe.get_doc({"doctype": "Product Group", "group_name": "Portal Group"}).insert()
        plan = frappe.get_doc({"doctype": "Hosting Plan", "plan_name": "Portal Plan", "product_group": group.name, "product_type": "Shared Hosting", "is_active": 1}).insert()
        frappe.get_doc({"doctype": "Plan Pricing", "hosting_plan": plan.name, "billing_cycle": "Monthly", "recurring_amount": 10}).insert()
        frappe.get_doc({"doctype": "Service", "customer": cust.name, "hosting_plan": plan.name, "status": "Active", "recurring_amount": 10}).insert()
        store = apis.storefront()
        self.assertTrue(any(p["name"] == plan.name for p in store))
        dash = apis.dashboard()
        self.assertEqual(dash["services"], 1)
        info = apis.checkout_info(plan.name)
        self.assertTrue(info["prices"])
        invs = apis.my_invoices()
        self.assertIsInstance(invs, list)
        frappe.set_user("Guest")
        self.assertRaises(frappe.PermissionError, apis.dashboard)
        frappe.set_user("Administrator")
