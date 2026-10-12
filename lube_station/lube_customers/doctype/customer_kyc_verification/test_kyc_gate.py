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
