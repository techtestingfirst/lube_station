import frappe
from frappe.tests import IntegrationTestCase

from lube_station.lube_station.provisioning.dedicated import release_inventory, reserve_inventory


class TestDedicatedLease(IntegrationTestCase):
    def test_dedicated_lease(self):
        provider = frappe.get_doc({"doctype": "Infrastructure Provider", "provider_name": "DS-Test", "provider_type": "Dedicated Server Provider", "status": "Active"}).insert()
        inv = frappe.get_doc({"doctype": "Dedicated Server Inventory", "provider": provider.name, "location": "eu-1", "status": "Available"}).insert()
        group = frappe.get_doc({"doctype": "Product Group", "group_name": "DS Group"}).insert()
        plan = frappe.get_doc({"doctype": "Hosting Plan", "plan_name": "DS Plan", "product_group": group.name, "product_type": "Dedicated Server", "is_active": 1}).insert()
        cfg = frappe.get_doc({"doctype": "Dedicated Server Configuration", "hosting_plan": plan.name, "location": "eu-1"}).insert()
        out = reserve_inventory(cfg.name, "lease-1")
        self.assertEqual(frappe.db.get_value("Dedicated Server Inventory", out["inventory"], "status"), "Reserved")
        mid = release_inventory(out["inventory"], wipe_confirmed=False)
        self.assertEqual(mid["status"], "Wipe Pending")
        final = release_inventory(out["inventory"], wipe_confirmed=True)
        self.assertEqual(final["status"], "Available")
