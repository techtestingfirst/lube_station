import frappe
from frappe.tests import IntegrationTestCase

from lube_station.lube_billing.doctype.hosting_invoice.hosting_invoice import generate_invoice, generate_renewal
from lube_station.lube_customers.doctype.order.order import place_order


class TestInvoiceIdempotent(IntegrationTestCase):
    def test_invoice_idempotent(self):
        import uuid

        email = f"inv-{uuid.uuid4().hex[:8]}@test.com"
        user = frappe.get_doc({"doctype": "User", "email": email, "first_name": "Inv", "enabled": 1}).insert(ignore_permissions=True)
        cust = frappe.get_doc({"doctype": "Hosting Customer", "user": user.name, "status": "Active"}).insert()
        group = frappe.get_doc({"doctype": "Product Group", "group_name": "Inv Group"}).insert()
        plan = frappe.get_doc({"doctype": "Hosting Plan", "plan_name": "Inv Plan", "product_group": group.name, "product_type": "Shared Hosting", "is_active": 1}).insert()
        frappe.get_doc({"doctype": "Plan Pricing", "hosting_plan": plan.name, "billing_cycle": "Monthly", "recurring_amount": 80}).insert()
        cart = frappe.get_doc({"doctype": "Cart", "customer": cust.name, "session_id": "inv-1"}).insert()
        cart.append("items", {"item_type": "Hosting Plan", "hosting_plan": plan.name, "billing_cycle": "Monthly", "quantity": 1})
        cart.save()
        out = place_order(cart.name, cust.name)
        first = generate_invoice(out["order"])
        second = generate_invoice(out["order"])
        self.assertEqual(first["invoice"], second["invoice"])
        self.assertTrue(second["reused"])

    def test_setup_fee_first_invoice_only(self):
        """WHMCS setup fee: billed on the initial invoice, never on renewal."""
        import uuid

        email = f"inv-setup-{uuid.uuid4().hex[:8]}@test.com"
        user = frappe.get_doc({"doctype": "User", "email": email, "first_name": "Setup", "enabled": 1}).insert(ignore_permissions=True)
        cust = frappe.get_doc({"doctype": "Hosting Customer", "user": user.name, "status": "Active"}).insert()
        group = frappe.get_doc({"doctype": "Product Group", "group_name": "Inv Setup Group"}).insert()
        plan = frappe.get_doc({"doctype": "Hosting Plan", "plan_name": "Inv Setup Plan", "product_group": group.name, "product_type": "Shared Hosting", "is_active": 1}).insert()
        frappe.get_doc({"doctype": "Plan Pricing", "hosting_plan": plan.name, "billing_cycle": "Monthly", "recurring_amount": 80, "setup_fee": 25}).insert()
        cart = frappe.get_doc({"doctype": "Cart", "customer": cust.name, "session_id": "inv-setup"}).insert()
        cart.append("items", {"item_type": "Hosting Plan", "hosting_plan": plan.name, "billing_cycle": "Monthly", "quantity": 1})
        cart.save()
        out = place_order(cart.name, cust.name)
        inv = frappe.get_doc("Hosting Invoice", generate_invoice(out["order"])["invoice"])
        setup_lines = [i for i in inv.invoice_items if i.description.startswith("Setup fee:")]
        self.assertEqual(len(setup_lines), 1)
        self.assertEqual(setup_lines[0].amount, 25)
        renew = frappe.get_doc("Hosting Invoice", generate_renewal(out["order"], "2026-11")["invoice"])
        self.assertFalse(any(i.description.startswith("Setup fee:") for i in renew.invoice_items))
        # Renewal carries only the recurring amount (pre-tax base 80).
        self.assertEqual(sum(i.amount for i in renew.invoice_items), 80)
