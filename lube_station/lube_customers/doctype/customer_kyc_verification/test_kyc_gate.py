import frappe
from frappe.tests import IntegrationTestCase

from lube_station.lube_customers.doctype.customer_kyc_verification.customer_kyc_verification import (
    is_kyc_verified,
    mark_verified,
    request_kyc,
)
from lube_station.lube_station.security.roles import ensure_roles


class TestKYCGate(IntegrationTestCase):
    def tearDown(self):
        frappe.set_user("Administrator")
        super().tearDown()

    def _paid_pending_service(self, cust_name):
        group = frappe.get_doc({"doctype": "Product Group", "group_name": "KYC Desk Group"}).insert()
        plan = frappe.get_doc({"doctype": "Hosting Plan", "plan_name": "KYC Desk Plan", "product_group": group.name, "product_type": "Shared Hosting", "is_active": 1}).insert()
        order = frappe.get_doc({"doctype": "Order", "customer": cust_name, "status": "Accepted"}).insert(ignore_permissions=True)
        svc = frappe.get_doc({"doctype": "Service", "customer": cust_name, "hosting_plan": plan.name, "order_ref": order.name, "status": "Pending", "recurring_amount": 10}).insert(ignore_permissions=True)
        frappe.get_doc({"doctype": "Hosting Invoice", "customer": cust_name, "order_ref": order.name, "invoice_items": [{"description": "x", "amount": 10}], "status": "Paid"}).insert(ignore_permissions=True)
        return svc.name
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

    def test_desk_status_edit_activates_without_api(self):
        """Staff flow in Desk: open the row, set Status, Save. No API call."""
        user = frappe.get_doc({"doctype": "User", "email": "kyc-desk@test.com", "first_name": "Kyc", "enabled": 1}).insert(ignore_permissions=True)
        cust = frappe.get_doc({"doctype": "Hosting Customer", "user": user.name, "status": "Active"}).insert()
        svc_name = self._paid_pending_service(cust.name)
        req = request_kyc(cust.name, "Manual", "Aadhaar")
        doc = frappe.get_doc("Customer KYC Verification", req["name"])
        doc.status = "Verified"
        doc.save()
        self.assertTrue(is_kyc_verified(cust.name))
        self.assertEqual(frappe.db.get_value("Service", svc_name, "status"), "Active")
        self.assertTrue(frappe.db.exists("Notification Event", {"event_type": "kyc_verified"}))

    def test_support_roles_can_open_kyc_queue(self):
        ensure_roles()
        user = frappe.get_doc({"doctype": "User", "email": "kyc-queue@test.com", "first_name": "Kyc", "enabled": 1}).insert(ignore_permissions=True)
        cust = frappe.get_doc({"doctype": "Hosting Customer", "user": user.name, "status": "Active"}).insert()
        req = request_kyc(cust.name, "Manual", "PAN")
        agent = frappe.get_doc(
            {"doctype": "User", "email": "kyc-agent@test.com", "first_name": "Agent", "enabled": 1, "roles": [{"role": "Support Agent"}]}
        ).insert(ignore_permissions=True)
        frappe.set_user(agent.name)
        self.assertTrue(frappe.has_permission("Customer KYC Verification", "read", req["name"]))
        self.assertTrue(frappe.has_permission("Customer KYC Verification", "write", req["name"]))
        names = frappe.get_list("Customer KYC Verification", pluck="name")
        self.assertIn(req["name"], names)
        # And the agent can act through the same dropdown-save path.
        doc = frappe.get_doc("Customer KYC Verification", req["name"])
        doc.status = "Manual Review"
        doc.save()
        self.assertEqual(frappe.db.get_value("Customer KYC Verification", req["name"], "status"), "Manual Review")

    def test_manual_request_notifies_support_queue(self):
        ensure_roles()
        frappe.db.set_single_value("Lube Station Settings", "support_email", "staff-kyc@test.com")
        user = frappe.get_doc({"doctype": "User", "email": "kyc-staff-mail@test.com", "first_name": "Kyc", "enabled": 1}).insert(ignore_permissions=True)
        cust = frappe.get_doc({"doctype": "Hosting Customer", "user": user.name, "status": "Active"}).insert()
        frappe.set_user(user.name)
        request_kyc(cust.name, "Manual", "PAN")
        self.assertTrue(frappe.db.exists("Email Queue Recipient", {"recipient": "staff-kyc@test.com"}))
