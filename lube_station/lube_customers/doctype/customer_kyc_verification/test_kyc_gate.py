import frappe
from frappe.tests import IntegrationTestCase

from lube_station.lube_customers.doctype.customer_kyc_verification.customer_kyc_verification import (
    is_kyc_verified,
    mark_verified,
    request_kyc,
)


class TestKYCGate(IntegrationTestCase):
    def test_kyc_per_customer_blocks_activate(self):
        user = frappe.get_doc({"doctype": "User", "email": "kyc-gate@test.com", "first_name": "Kyc", "enabled": 1}).insert(ignore_permissions=True)
        cust = frappe.get_doc({"doctype": "Hosting Customer", "user": user.name, "status": "Active"}).insert()
        self.assertFalse(is_kyc_verified(cust.name))
        group = frappe.get_doc({"doctype": "Product Group", "group_name": "KYC Group"}).insert()
        plan = frappe.get_doc({"doctype": "Hosting Plan", "plan_name": "KYC Plan", "product_group": group.name, "product_type": "Shared Hosting", "is_active": 1}).insert()
        svc = frappe.get_doc({"doctype": "Service", "customer": cust.name, "hosting_plan": plan.name, "status": "Pending", "recurring_amount": 10}).insert()
        self.assertRaises(Exception, svc.activate)
        req = request_kyc(cust.name, "Manual", "Passport")
        mark_verified(req["name"], "foreign passport checked")
        self.assertTrue(is_kyc_verified(cust.name))
        svc.reload()
        svc.activate()
        self.assertEqual(svc.status, "Active")

    def test_paid_invoice_leaves_pending_until_verified(self):
        from lube_station.lube_provisioning.doctype.service.service import on_invoice_paid

        user = frappe.get_doc({"doctype": "User", "email": "kyc-pay@test.com", "first_name": "Kyc", "enabled": 1}).insert(ignore_permissions=True)
        cust = frappe.get_doc({"doctype": "Hosting Customer", "user": user.name, "status": "Active"}).insert()
        group = frappe.get_doc({"doctype": "Product Group", "group_name": "KYC Pay Group"}).insert()
        plan = frappe.get_doc({"doctype": "Hosting Plan", "plan_name": "KYC Pay Plan", "product_group": group.name, "product_type": "Shared Hosting", "is_active": 1}).insert()
        order = frappe.get_doc({"doctype": "Order", "customer": cust.name, "status": "Accepted"}).insert(ignore_permissions=True)
        svc = frappe.get_doc({"doctype": "Service", "customer": cust.name, "hosting_plan": plan.name, "order_ref": order.name, "status": "Pending", "recurring_amount": 10}).insert(ignore_permissions=True)
        inv = frappe.get_doc({"doctype": "Hosting Invoice", "customer": cust.name, "order_ref": order.name, "invoice_items": [{"description": "x", "amount": 10}], "status": "Paid"}).insert(ignore_permissions=True)
        out = on_invoice_paid(inv.name)
        self.assertEqual(frappe.db.get_value("Service", svc.name, "status"), "Pending")
        self.assertEqual(out["action"], "activated")
        self.assertEqual(out["services"], [])
