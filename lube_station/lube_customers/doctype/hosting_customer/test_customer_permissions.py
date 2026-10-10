import frappe
from frappe.tests import IntegrationTestCase

from lube_station.lube_station.permissions import hosting_customer_query


class TestCustomerPermissions(IntegrationTestCase):
    def test_customer_permissions(self):
        group = frappe.get_doc({"doctype": "Client Group", "group_name": "Perm-Test"}).insert()
        cust_name = frappe.db.get_value("Hosting Customer", {"user": "Administrator"}, "name")
        if not cust_name:
            cust_name = frappe.get_doc(
                {"doctype": "Hosting Customer", "user": "Administrator", "client_group": group.name, "status": "Active"}
            ).insert().name
        cust = frappe.get_doc("Hosting Customer", cust_name)
        self.assertTrue(frappe.db.exists("Hosting Customer", cust.name))
        cond = hosting_customer_query("Administrator")
        self.assertEqual(cond, "")
        cond_guest = hosting_customer_query("Guest")
        self.assertIn("1=0", cond_guest)
