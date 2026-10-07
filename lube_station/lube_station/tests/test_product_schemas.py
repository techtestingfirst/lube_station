import frappe
from frappe.tests import IntegrationTestCase

from lube_station.lube_catalog.doctype.product_type_schema.product_type_schema import (
    get_product_requirements,
)
from lube_station.lube_station.setup import PRODUCT_TYPE_SCHEMAS, ensure_product_schemas


class TestProductSchemas(IntegrationTestCase):
    def test_all_types_seeded(self):
        ensure_product_schemas()
        seeded = {s for s, _t, _f, _fields in PRODUCT_TYPE_SCHEMAS}
        self.assertEqual(len(seeded), 11)
        for schema_name, product_type, _flags, _fields in PRODUCT_TYPE_SCHEMAS:
            doc = frappe.get_doc("Product Type Schema", schema_name)
            self.assertEqual(doc.product_type, product_type)

    def test_seed_never_overwrites(self):
        ensure_product_schemas()
        frappe.db.set_value("Product Type Schema", "Shared Hosting Default", "requires_domain", 0)
        ensure_product_schemas()
        self.assertEqual(
            frappe.db.get_value("Product Type Schema", "Shared Hosting Default", "requires_domain"),
            0,
        )

    def test_lookup_by_product_type(self):
        ensure_product_schemas()
        out = get_product_requirements(product_type="VPS")
        self.assertEqual(out["schema"], "VPS Default")
        self.assertTrue(out["flags"]["requires_hostname"])
        self.assertTrue(out["flags"]["requires_root_password"])
        ssl = get_product_requirements(product_type="SSL")
        self.assertEqual(ssl["fields"][0]["field_key"], "common_name")
        self.assertTrue(ssl["fields"][0]["required"])
