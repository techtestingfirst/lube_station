import frappe
from frappe.tests import IntegrationTestCase

from lube_station.lube_station.permissions import (
    has_customer_document_permission,
    hosting_invoice_query,
)


def _customer(user="Administrator"):
    name = frappe.db.get_value("Hosting Customer", {"user": user}, "name")
    if name:
        return frappe.get_doc("Hosting Customer", name)
    return frappe.get_doc({"doctype": "Hosting Customer", "user": user, "status": "Active"}).insert()


class TestInvoicePdf(IntegrationTestCase):
    def test_format_renders(self):
        self.assertTrue(frappe.db.exists("Print Format", "Hosting Invoice"))
        cust = _customer()
        inv = frappe.get_doc(
            {
                "doctype": "Hosting Invoice",
                "customer": cust.name,
                "invoice_items": [{"description": "Test line", "service_ref": "SVC-1", "amount": 25}],
                "status": "Unpaid",
            }
        ).insert(ignore_permissions=True)
        html = frappe.get_print("Hosting Invoice", inv.name, "Hosting Invoice")
        self.assertIn(inv.name, html)
        self.assertIn("Total due", html)

    def test_owner_can_print_stranger_cannot(self):
        cust = _customer()
        inv = frappe.get_doc(
            {
                "doctype": "Hosting Invoice",
                "customer": cust.name,
                "invoice_items": [{"description": "x", "amount": 10}],
                "status": "Unpaid",
            }
        ).insert(ignore_permissions=True)
        self.assertTrue(has_customer_document_permission(inv.as_dict(), "Administrator"))
        stranger = frappe.get_doc(
            {"doctype": "User", "email": "stranger-pdf@test.com", "first_name": "Stranger", "enabled": 1}
        ).insert(ignore_permissions=True)
        stranger_cust = frappe.get_doc({"doctype": "Hosting Customer", "user": stranger.name, "status": "Active"}).insert(
            ignore_permissions=True
        )
        self.assertFalse(has_customer_document_permission(inv.as_dict(), stranger.name))
        cond = hosting_invoice_query(stranger.name)
        self.assertNotIn("1=0", cond)
        self.assertIn(stranger_cust.name, cond)
        self.assertNotIn(cust.name, cond)
