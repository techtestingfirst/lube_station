import frappe
from frappe.tests import IntegrationTestCase

from lube_station.lube_catalog.doctype.product_type_schema.product_type_schema import (
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

    def test_flag_enforcement_without_field_rows(self):
        """WHMCS parity: requires_hostname/root/os/location/ns enforce canonical keys."""
        schema = frappe.get_doc(
            {
                "doctype": "Product Type Schema",
                "schema_name": "VPS-Flags",
                "product_type": "VPS",
                "requires_hostname": 1,
                "requires_root_password": 1,
                "requires_os": 1,
                "requires_location": 1,
                "requires_nameservers": 1,
            }
        ).insert()
        good = {
            "hostname": "vps1.test",
            "root_password": "s3cret-root-10",
            "os": "ubuntu-22.04",
            "location": "Mumbai",
            "ns1": "ns1.test",
            "ns2": "ns2.test",
        }
        self.assertTrue(validate_config(schema.name, good))
        # Alias root_pass accepted (older schemas).
        aliased = dict(good, root_password=None)
        aliased.pop("root_password")
        aliased["root_pass"] = "s3cret-root-10"
        self.assertTrue(validate_config(schema.name, aliased))
        for key in ("hostname", "root_password", "os", "location", "ns1"):
            bad = dict(good)
            bad.pop(key)
            if key == "root_password":
                bad.pop("root_pass", None)
            self.assertRaises(frappe.ValidationError, validate_config, schema.name, bad)

    def test_invalid_option_rejected(self):
        """Closed option sets reject off-list values (price-tamper guard)."""
        import json

        schema = frappe.get_doc(
            {
                "doctype": "Product Type Schema",
                "schema_name": "VPS-Opt-Closed",
                "product_type": "VPS",
                "fields": [
                    {
                        "field_key": "extra_disk",
                        "label": "Extra Disk",
                        "field_type": "Select",
                        "options_json": json.dumps([{"label": "None", "value": "none"}, {"label": "50GB", "value": "ssd-50", "price": 5}]),
                    }
                ],
            }
        ).insert()
        from lube_station.lube_catalog.doctype.product_type_schema.product_type_schema import option_price_delta

        self.assertEqual(option_price_delta(schema.name, {"extra_disk": "ssd-50"}), 5)
        self.assertEqual(option_price_delta(schema.name, {"extra_disk": "none"}), 0)
        self.assertRaises(frappe.ValidationError, validate_config, schema.name, {"extra_disk": "nvme-999"})
