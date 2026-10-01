import frappe
from frappe.tests import IntegrationTestCase

from lube_station.lube_station.doctype.product_type_schema.product_type_schema import (
    get_product_requirements,
    validate_config,
)


class TestProductRequirements(IntegrationTestCase):
    def test_product_requirements(self):
        schema = frappe.get_doc(
            {
                "doctype": "Product Type Schema",
                "schema_name": "VPS-Test",
                "product_type": "VPS",
                "requires_hostname": 1,
                "requires_os": 1,
                "fields": [
                    {"field_key": "hostname", "label": "Hostname", "field_type": "Text", "required": 1},
                    {"field_key": "os", "label": "OS", "field_type": "Select", "required": 1},
                ],
            }
        ).insert()
        out = get_product_requirements(schema=schema.name)
        self.assertEqual(len(out["fields"]), 2)
        self.assertRaises(frappe.ValidationError, validate_config, schema.name, {"hostname": "h"})
        self.assertTrue(validate_config(schema.name, {"hostname": "h", "os": "ubuntu-24.04"}))
