import frappe
from frappe.tests import IntegrationTestCase


class TestInfrastructureProvider(IntegrationTestCase):
    def test_bad_capabilities_rejected(self):
        doc = frappe.get_doc(
            {
                "doctype": "Infrastructure Provider",
                "provider_name": "Caps Draft",
                "provider_type": "VPS API",
                "capabilities": "{not json",
                "status": "Active",
            }
        )
        self.assertRaises(frappe.ValidationError, doc.insert)

    def test_blank_capabilities_allowed(self):
        doc = frappe.get_doc(
            {
                "doctype": "Infrastructure Provider",
                "provider_name": "Caps Blank",
                "provider_type": "Local Infrastructure",
                "status": "Active",
            }
        ).insert(ignore_permissions=True)
        self.assertFalse(doc.capabilities)

    def test_capabilities_derived_from_products(self):
        provider = frappe.get_doc(
            {
                "doctype": "Infrastructure Provider",
                "provider_name": "Caps Derived",
                "provider_type": "VPS API",
                "status": "Active",
            }
        ).insert(ignore_permissions=True)
        frappe.get_doc(
            {
                "doctype": "Provider Product",
                "provider": provider.name,
                "product_type": "VPS",
                "regions_json": '["fsn1", "nbg1"]',
                "available_quantity": 3,
            }
        ).insert(ignore_permissions=True)
        provider.save(ignore_permissions=True)
        import json

        caps = json.loads(provider.capabilities)
        self.assertEqual(caps["regions"], ["fsn1", "nbg1"])
        self.assertEqual(caps["product_types"], ["VPS"])
        self.assertEqual(caps["total_available"], 3)

    def test_seller_capabilities_kept(self):
        provider = frappe.get_doc(
            {
                "doctype": "Infrastructure Provider",
                "provider_name": "Caps Manual",
                "provider_type": "VPS API",
                "capabilities": '{"snapshots": true}',
                "status": "Active",
            }
        ).insert(ignore_permissions=True)
        frappe.get_doc(
            {
                "doctype": "Provider Product",
                "provider": provider.name,
                "product_type": "VPS",
                "regions_json": '["fsn1"]',
                "available_quantity": 1,
            }
        ).insert(ignore_permissions=True)
        provider.save(ignore_permissions=True)
        self.assertEqual(provider.capabilities, '{"snapshots": true}')

    def test_bad_regions_json_rejected(self):
        provider = frappe.get_doc(
            {
                "doctype": "Infrastructure Provider",
                "provider_name": "Caps JSON",
                "provider_type": "VPS API",
                "status": "Active",
            }
        ).insert(ignore_permissions=True)
        doc = frappe.get_doc(
            {
                "doctype": "Provider Product",
                "provider": provider.name,
                "product_type": "VPS",
                "regions_json": "[broken",
                "available_quantity": 1,
            }
        )
        self.assertRaises(frappe.ValidationError, doc.insert)

    def test_bad_plans_json_rejected(self):
        provider = frappe.get_doc(
            {
                "doctype": "Infrastructure Provider",
                "provider_name": "Caps JSON2",
                "provider_type": "VPS API",
                "status": "Active",
            }
        ).insert(ignore_permissions=True)
        doc = frappe.get_doc(
            {
                "doctype": "Provider Product",
                "provider": provider.name,
                "product_type": "VPS",
                "plans_json": "{oops",
                "available_quantity": 1,
            }
        )
        self.assertRaises(frappe.ValidationError, doc.insert)
