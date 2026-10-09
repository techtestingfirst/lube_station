import uuid

import frappe
from frappe.tests import IntegrationTestCase

from lube_station.lube_station.usage.collect import collect_usage


def _fixtures(disk_rate=2, bw_rate=0.5):
    email = f"use-{uuid.uuid4().hex[:8]}@test.com"
    user = frappe.get_doc({"doctype": "User", "email": email, "first_name": "Use", "enabled": 1}).insert(ignore_permissions=True)
    cust = frappe.get_doc({"doctype": "Hosting Customer", "user": user.name, "status": "Active"}).insert()
    group = frappe.get_doc({"doctype": "Product Group", "group_name": f"Use Group {uuid.uuid4().hex[:6]}"}).insert()
    plan = frappe.get_doc({"doctype": "Hosting Plan", "plan_name": f"Use Plan {uuid.uuid4().hex[:6]}", "product_group": group.name, "product_type": "VPS", "is_active": 1}).insert()
    frappe.get_doc({"doctype": "VPS Configuration", "hosting_plan": plan.name, "storage_gb": 20, "bandwidth_gb": 100, "disk_overage_rate": disk_rate, "bandwidth_overage_rate": bw_rate}).insert()
    svc = frappe.get_doc({"doctype": "Service", "customer": cust.name, "hosting_plan": plan.name, "status": "Active", "recurring_amount": 10}).insert()
    return svc


class TestUsageOverage(IntegrationTestCase):
    def test_usage_overage(self):
        svc = _fixtures()
        out = collect_usage(svc.name, snap_date="2026-01-01", disk=25, bandwidth=120)
        self.assertTrue(out["overage"])
        again = collect_usage(svc.name, snap_date="2026-01-01", disk=25, bandwidth=120)
        self.assertTrue(again["reused"])
        inv = frappe.get_doc("Hosting Invoice", {"idempotency_key": f"overage:{svc.name}:2026-01-01"})
        # 5 GB disk x $2 + 20 GB bw x $0.5 = $20, due-dated like other invoices.
        self.assertEqual(sum(i.amount for i in inv.invoice_items), 20)
        self.assertTrue(inv.due_date)

    def test_unpriced_metric_not_invoiced(self):
        svc = _fixtures(disk_rate=0, bw_rate=0)
        out = collect_usage(svc.name, snap_date="2026-02-01", disk=25, bandwidth=120)
        self.assertTrue(out["overage"])
        self.assertFalse(frappe.db.exists("Hosting Invoice", {"idempotency_key": f"overage:{svc.name}:2026-02-01"}))

    def test_within_limits_no_invoice(self):
        svc = _fixtures()
        out = collect_usage(svc.name, snap_date="2026-03-01", disk=10, bandwidth=50)
        self.assertFalse(out["overage"])
        self.assertFalse(frappe.db.exists("Hosting Invoice", {"idempotency_key": f"overage:{svc.name}:2026-03-01"}))
