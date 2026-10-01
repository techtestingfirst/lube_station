import frappe
from frappe.tests import IntegrationTestCase

from lube_station.lube_station.doctype.downloadable_asset.downloadable_asset import check_entitlement


class TestDownloadEntitlement(IntegrationTestCase):
    def test_download_entitlement(self):
        cat = frappe.get_doc({"doctype": "Download Category", "category_name": "Docs-Test"}).insert()
        pub = frappe.get_doc(
            {"doctype": "Downloadable Asset", "title": "Public file", "category": cat.name, "storage_type": "Remote URL", "remote_url": "https://example.com/f.zip", "access_policy": "Public", "active": 1}
        ).insert()
        priv = frappe.get_doc(
            {"doctype": "Downloadable Asset", "title": "Login file", "category": cat.name, "storage_type": "Remote URL", "remote_url": "https://example.com/g.zip", "access_policy": "Logged-in Customers", "active": 1}
        ).insert()
        self.assertTrue(check_entitlement(pub.name, "Guest")["allowed"])
        self.assertFalse(check_entitlement(priv.name, "Guest")["allowed"])
        self.assertTrue(check_entitlement(priv.name, "Administrator")["allowed"])
