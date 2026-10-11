import uuid

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
        frappe.db.set_value(
            "Hosting Customer",
            cust.name,
            {"company": "Acme Ltd", "tax_id": "VAT123", "address_line1": "1 Main St", "city": "Springfield", "country": "India"},
        )
        group = frappe.get_doc({"doctype": "Product Group", "group_name": f"PDF Group {uuid.uuid4().hex[:6]}"}).insert()
        plan = frappe.get_doc({"doctype": "Hosting Plan", "plan_name": f"PDF Plan {uuid.uuid4().hex[:6]}", "product_group": group.name, "product_type": "Shared Hosting", "is_active": 1}).insert()
        svc = frappe.get_doc({"doctype": "Service", "customer": cust.name, "hosting_plan": plan.name, "status": "Active", "recurring_amount": 10, "primary_domain": "example.com"}).insert()
        inv = frappe.get_doc(
            {
                "doctype": "Hosting Invoice",
                "customer": cust.name,
                "invoice_items": [{"description": f"Hosting Plan: {plan.name} x1", "service_ref": svc.name, "amount": 25}],
                "status": "Unpaid",
            }
        ).insert(ignore_permissions=True)
        html = frappe.get_print("Hosting Invoice", inv.name, "Hosting Invoice")
        self.assertIn(inv.name, html)
        self.assertIn("Total due", html)
        # Billing identity, never the raw customer ID.
        self.assertIn("Acme Ltd", html)
        self.assertIn("1 Main St", html)
        self.assertIn("VAT123", html)
        self.assertNotIn(cust.name, html.replace(inv.name, ""))
        # Plan group + name, purchased domain, service period.
        self.assertIn(plan.plan_name, html)
        self.assertIn("example.com", html)
        self.assertIn("Start", html)
        self.assertIn("End", html)
        self.assertNotIn(plan.name, html)
        self.assertNotIn(svc.name, html)

    def test_unpaid_hides_period_paid_shows_cycle(self):
        from frappe.utils import add_months, formatdate, getdate, today

        cust = _customer()
        group = frappe.get_doc({"doctype": "Product Group", "group_name": f"PDF Cycle Group {uuid.uuid4().hex[:6]}"}).insert()
        plan = frappe.get_doc({"doctype": "Hosting Plan", "plan_name": f"PDF Cycle Plan {uuid.uuid4().hex[:6]}", "product_group": group.name, "product_type": "Shared Hosting", "is_active": 1}).insert()
        svc = frappe.get_doc({"doctype": "Service", "customer": cust.name, "hosting_plan": plan.name, "status": "Active", "recurring_amount": 10, "primary_domain": "example.com", "billing_cycle": "Monthly"}).insert()
        inv = frappe.get_doc(
            {
                "doctype": "Hosting Invoice",
                "customer": cust.name,
                "invoice_items": [{"description": f"Hosting Plan: {plan.name} x2", "service_ref": svc.name, "amount": 200}],
                "status": "Unpaid",
            }
        ).insert(ignore_permissions=True)
        html = frappe.get_print("Hosting Invoice", inv.name, "Hosting Invoice")
        self.assertIn("Qty", html)
        self.assertIn(">2</td>", html)
        # Unpaid: service not started, no period shown, no payment line.
        self.assertNotIn(formatdate(getdate(today())), html.replace(f"Due:</strong> {formatdate(inv.due_date)}", ""))
        self.assertNotIn("Paid via", html)
        frappe.get_doc({"doctype": "Payment Transaction", "invoice": inv.name, "gateway": "Stripe", "gateway_txn_id": "txn_test_123", "status": "Success", "amount": 200}).insert(ignore_permissions=True)
        inv.status = "Paid"
        inv.save(ignore_permissions=True)
        html = frappe.get_print("Hosting Invoice", inv.name, "Hosting Invoice")
        self.assertIn(formatdate(getdate(today())), html)
        self.assertIn(formatdate(add_months(getdate(today()), 1)), html)
        # Colored status pill and transactions table.
        self.assertIn("#16a34a", html)
        self.assertIn("Transactions", html)
        self.assertIn("txn_test_123", html)
        self.assertIn("Stripe", html)
        self.assertNotIn("Paid via", html)

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

    def test_tax_code_column_and_seller_tax_id(self):
        cust = _customer()
        frappe.get_doc({"doctype": "Tax Code", "code": "9984", "label": "SAC", "description": "Hosting"}).insert(ignore_permissions=True)
        group = frappe.get_doc({"doctype": "Product Group", "group_name": f"PDF Tax Group {uuid.uuid4().hex[:6]}"}).insert()
        plan = frappe.get_doc({"doctype": "Hosting Plan", "plan_name": f"PDF Tax Plan {uuid.uuid4().hex[:6]}", "product_group": group.name, "product_type": "Shared Hosting", "is_active": 1, "tax_code": "9984"}).insert()
        svc = frappe.get_doc({"doctype": "Service", "customer": cust.name, "hosting_plan": plan.name, "status": "Active", "recurring_amount": 10}).insert()
        frappe.db.set_single_value("Lube Station Settings", "company_tax_id", "29TEST1234F1Z5")
        inv = frappe.get_doc(
            {
                "doctype": "Hosting Invoice",
                "customer": cust.name,
                "invoice_items": [{"description": "Hosting", "service_ref": svc.name, "amount": 25}],
                "status": "Unpaid",
            }
        ).insert(ignore_permissions=True)
        html = frappe.get_print("Hosting Invoice", inv.name, "Hosting Invoice")
        # Seller-entered code resolved via service -> plan; header line.
        self.assertIn("SAC:", html)
        self.assertIn("9984", html)
        thead = html.split("<thead>")[1].split("</thead>")[0]
        self.assertNotIn("SAC", thead)
        self.assertIn("Tax ID: 29TEST1234F1Z5", html)

    def test_company_logo_slot(self):
        cust = _customer()
        frappe.db.set_single_value("Lube Station Settings", "company_logo", "")
        inv = frappe.get_doc(
            {
                "doctype": "Hosting Invoice",
                "customer": cust.name,
                "invoice_items": [{"description": "Hosting", "amount": 10}],
                "status": "Unpaid",
            }
        ).insert(ignore_permissions=True)
        html = frappe.get_print("Hosting Invoice", inv.name, "Hosting Invoice")
        self.assertNotIn("<img", html)
        frappe.db.set_single_value("Lube Station Settings", "company_logo", "/assets/lube_station/images/logo.svg")
        html = frappe.get_print("Hosting Invoice", inv.name, "Hosting Invoice")
        self.assertIn("/assets/lube_station/images/logo.svg", html)
        frappe.db.set_single_value("Lube Station Settings", "company_logo", "")

    def test_tax_code_column_hidden_when_empty(self):
        cust = _customer()
        frappe.db.set_single_value("Lube Station Settings", "company_tax_id", "")
        frappe.db.set_single_value("Lube Station Settings", "default_tax_code", "")
        inv = frappe.get_doc(
            {
                "doctype": "Hosting Invoice",
                "customer": cust.name,
                "invoice_items": [{"description": "Hosting", "amount": 10}],
                "status": "Unpaid",
            }
        ).insert(ignore_permissions=True)
        html = frappe.get_print("Hosting Invoice", inv.name, "Hosting Invoice")
        self.assertNotIn("Tax code", html)
