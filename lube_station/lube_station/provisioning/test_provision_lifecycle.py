import frappe
from frappe.tests import IntegrationTestCase

from lube_station.lube_station.provisioning.jobs import run_change_package, run_create, run_terminate


class TestProvisionLifecycle(IntegrationTestCase):
    def test_provision_lifecycle(self):
        frappe.get_doc({"doctype": "Provisioning Module", "module_name": "cPanel-Test", "control_panel": "cPanel", "class_path": "lube_station.lube_station.adapters.provisioning.cpanel.CpanelWhmAdapter"}).insert()
        first = run_create("SVC-1", key="idem-1")
        second = run_create("SVC-1", key="idem-1")
        self.assertFalse(first["reused"])
        self.assertTrue(second["reused"])
        self.assertTrue(run_change_package("SVC-1", new_plan="PLAN-2")["key"])
        self.assertTrue(run_terminate("SVC-1", key="term-1")["key"])
