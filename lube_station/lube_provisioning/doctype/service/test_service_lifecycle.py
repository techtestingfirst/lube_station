import frappe
from frappe.tests import IntegrationTestCase


class TestServiceLifecycle(IntegrationTestCase):
    def test_service_lifecycle(self):
        cust = frappe.get_doc({"doctype": "Hosting Customer", "user": "Administrator", "status": "Active"}).insert()
        group = frappe.get_doc({"doctype": "Product Group", "group_name": "Svc Group"}).insert()
        plan = frappe.get_doc({"doctype": "Hosting Plan", "plan_name": "Svc Plan", "product_group": group.name, "product_type": "Shared Hosting", "is_active": 1}).insert()
        svc = frappe.get_doc({"doctype": "Service", "customer": cust.name, "hosting_plan": plan.name, "status": "Pending", "recurring_amount": 10}).insert()
        svc.activate()
        self.assertEqual(frappe.db.get_value("Service", svc.name, "status"), "Active")
        svc.suspend("test")
        self.assertEqual(frappe.db.get_value("Service", svc.name, "status"), "Suspended")
        svc.unsuspend()
        self.assertEqual(frappe.db.get_value("Service", svc.name, "status"), "Active")
        self.assertRaises(frappe.ValidationError, svc.terminate, None)
        svc.terminate("customer cancelled, approved")
        self.assertEqual(frappe.db.get_value("Service", svc.name, "status"), "Terminated")
