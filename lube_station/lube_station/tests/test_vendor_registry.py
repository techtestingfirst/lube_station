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
        from lube_station.lube_station.adapters.registrar.test_opensrs_live import FakeTransport, ok

        acct = frappe.db.get_value("Registrar Account", {"registrar": "OpenSRS"}, "name")
        created_acct = False
        if not acct:
            doc = frappe.get_doc(
                {"doctype": "Registrar Account", "registrar": "OpenSRS", "active": 1}
            ).insert(ignore_permissions=True)
            doc.set("api_key", "reseller1")
            doc.set("api_secret", "key123")
            doc.save(ignore_permissions=True)
            acct = doc.name
            created_acct = True
        try:
            self.assertEqual(
                opensrs.check_availability("example.com", transport=FakeTransport([ok({"status": "available"})]))["status"],
                "available",
            )
        finally:
            if created_acct:
                frappe.delete_doc("Registrar Account", acct, ignore_permissions=True, force=True)
        self.assertRaises(frappe.ValidationError, get_payment_adapter, "CCAvenue")

    def test_install_seeds_registries(self):
        from lube_station.lube_station.setup import ensure_all

        ensure_all()
        self.assertEqual(frappe.db.count("Payment Gateway Adapter"), 10)
        self.assertEqual(frappe.db.count("Provisioning Adapter"), 8)
        self.assertEqual(frappe.db.count("Registrar Adapter"), 10)
