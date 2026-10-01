import frappe
from frappe.tests import IntegrationTestCase

from lube_station.lube_station.adapters.registry import (
    get_payment_adapter,
    get_provisioning_adapter,
    get_registrar_adapter,
)
from lube_station.lube_station.adapters.seed import seed


class TestVendorRegistry(IntegrationTestCase):
    def test_registry(self):
        seed()
        self.assertEqual(frappe.db.count("Payment Gateway Adapter"), 10)
        self.assertEqual(frappe.db.count("Provisioning Adapter"), 8)
        self.assertEqual(frappe.db.count("Registrar Adapter"), 10)
        stripe = get_payment_adapter("Stripe")
        self.assertTrue(hasattr(stripe, "handle_webhook"))
        cpanel = get_provisioning_adapter("cPanel / WHM")
        self.assertTrue(hasattr(cpanel, "create_account"))
        opensrs = get_registrar_adapter("OpenSRS")
        self.assertEqual(opensrs.check_availability("example.com")["status"], "available")
        self.assertRaises(frappe.ValidationError, get_payment_adapter, "CCAvenue")
