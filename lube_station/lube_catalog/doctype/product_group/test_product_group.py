import frappe
from frappe.tests import IntegrationTestCase


class TestProductGroup(IntegrationTestCase):
    def test_product_group(self):
        doc = frappe.get_doc({"doctype": "Product Group", "group_name": "Shared Test", "show_on_portal": 1})
        doc.insert()
        self.assertTrue(frappe.db.exists("Product Group", "Shared Test"))
