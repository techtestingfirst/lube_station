import frappe
from frappe.tests import IntegrationTestCase

from lube_station.lube_station.providers.factory import get_provider_adapter


class TestProviderAdapter(IntegrationTestCase):
    def test_provider_adapter(self):
        provider = frappe.get_doc({"doctype": "Infrastructure Provider", "provider_name": "Manual-Test", "provider_type": "Local Infrastructure", "status": "Active"}).insert()
        product = frappe.get_doc({"doctype": "Provider Product", "provider": provider.name, "product_type": "VPS", "available_quantity": 1}).insert()
        adapter = get_provider_adapter(provider.name)
        self.assertTrue(hasattr(adapter, "create_instance"))
        adapter.allocate_inventory(product.name, "key-1")
        self.assertEqual(frappe.db.get_value("Provider Product", product.name, "available_quantity"), 0)
        self.assertTrue(frappe.db.exists("Provider API Log", {"idempotency_key": "key-1"}))
        log = frappe.get_doc("Provider API Log", {"idempotency_key": "key-1"})
        self.assertNotIn("secret", (log.error_text or "").lower())
        adapter.release_inventory(product.name, "key-1")
        self.assertEqual(frappe.db.get_value("Provider Product", product.name, "available_quantity"), 1)
