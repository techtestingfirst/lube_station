import uuid

import frappe
from frappe.tests import IntegrationTestCase


def _customer():
    email = f"mail-{uuid.uuid4().hex[:8]}@test.com"
    user = frappe.get_doc({"doctype": "User", "email": email, "first_name": "Mail", "enabled": 1}).insert(ignore_permissions=True)
    return frappe.get_doc({"doctype": "Hosting Customer", "user": user.name, "status": "Active", "kyc_status": "Verified"}).insert()


def _plan():
    group = frappe.get_doc({"doctype": "Product Group", "group_name": f"Mail Group {uuid.uuid4().hex[:6]}"}).insert()
    return frappe.get_doc({"doctype": "Hosting Plan", "plan_name": f"Mail Plan {uuid.uuid4().hex[:6]}", "product_group": group.name, "product_type": "Shared Hosting", "is_active": 1}).insert()


class TestEmailLifecycle(IntegrationTestCase):
    def test_service_emails(self):
        cust = _customer()
        plan = _plan()
        svc = frappe.get_doc({"doctype": "Service", "customer": cust.name, "hosting_plan": plan.name, "status": "Pending", "recurring_amount": 10}).insert()
        svc.activate()
        self.assertTrue(frappe.db.exists("Notification Event", {"event_key": f"welcome:{svc.name}"}))
        self.assertTrue(frappe.db.exists("Notification Event", {"event_key": f"credentials:{svc.name}"}))
        svc.suspend("overdue")
        self.assertTrue(frappe.db.exists("Notification Event", {"event_key": f"suspension:{svc.name}"}))
        svc.unsuspend()
        self.assertTrue(frappe.db.exists("Notification Event", {"event_key": f"unsuspension:{svc.name}"}))
        svc.terminate("approved, test")
        self.assertTrue(frappe.db.exists("Notification Event", {"event_key": f"termination:{svc.name}"}))

    def test_credit_email(self):
        cust = _customer()
        note = frappe.get_doc({"doctype": "Credit Note", "customer": cust.name, "amount": 25}).insert(ignore_permissions=True)
        note.submit()
        self.assertTrue(frappe.db.exists("Notification Event", {"event_key": f"credit:{note.name}"}))

    def test_dunning_email(self):
        from datetime import date

        from lube_station.lube_provisioning.doctype.service.service import apply_dunning

        for name in frappe.get_all("Dunning Rule", pluck="name"):
            frappe.delete_doc("Dunning Rule", name, force=True)
        frappe.get_doc({"doctype": "Dunning Rule", "rule_name": "Email-Test-Rule", "grace_days": 7, "termination_days": 30, "active": 1}).insert()

        cust = _customer()
        inv = frappe.get_doc({"doctype": "Hosting Invoice", "customer": cust.name, "invoice_items": [{"description": "x", "amount": 50}], "due_date": date.today(), "status": "Unpaid"}).insert(ignore_permissions=True)
        apply_dunning(inv.name)
        self.assertTrue(frappe.db.exists("Notification Event", {"event_key": f"invoice_reminder:{inv.name}:reminder"}))
