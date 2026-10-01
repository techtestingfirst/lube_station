import frappe
from frappe.tests import IntegrationTestCase

from lube_station.lube_station.doctype.tax_rule.tax_rule import tax_for


class TestTaxMulti(IntegrationTestCase):
    def test_tax_multi(self):
        cust = frappe.get_doc({"doctype": "Hosting Customer", "user": "Administrator", "status": "Active"}).insert()
        frappe.get_doc({"doctype": "Tax Rule", "tax_name": "GST", "percentage": 10, "active": 1}).insert()
        frappe.get_doc({"doctype": "Tax Rule", "tax_name": "Cess", "percentage": 5, "active": 1}).insert()
        self.assertEqual(tax_for(cust.name, 100), 15)
