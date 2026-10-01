import frappe
from frappe.tests import IntegrationTestCase

from lube_station.lube_station.usage.collect import collect_usage


class TestUsageOverage(IntegrationTestCase):
    def test_usage_overage(self):
        cust = frappe.get_doc({"doctype": "Hosting Customer", "user": "Administrator", "status": "Active"}).insert()
        group = frappe.get_doc({"doctype": "Product Group", "group_name": "Use Group"}).insert()
        plan = frappe.get_doc({"doctype": "Hosting Plan", "plan_name": "Use Plan", "product_group": group.name, "product_type": "VPS", "is_active": 1}).insert()
        frappe.get_doc({"doctype": "VPS Configuration", "hosting_plan": plan.name, "storage_gb": 20, "bandwidth_gb": 100}).insert()
        svc = frappe.get_doc({"doctype": "Service", "customer": cust.name, "hosting_plan": plan.name, "status": "Active", "recurring_amount": 10}).insert()
        out = collect_usage(svc.name, snap_date="2026-01-01", disk=25, bandwidth=120)
        self.assertTrue(out["overage"])
        again = collect_usage(svc.name, snap_date="2026-01-01", disk=25, bandwidth=120)
        self.assertTrue(again["reused"])
        self.assertTrue(frappe.db.exists("Hosting Invoice", {"idempotency_key": f"overage:{svc.name}:2026-01-01"}))
