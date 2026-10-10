import frappe

from lube_station.lube_station.tests.helpers import make_customer, make_user
from frappe.tests import IntegrationTestCase

from lube_station.lube_station.adapters.seed import seed
from lube_station.lube_station.payments.links import payment_link


class TestPaymentLink(IntegrationTestCase):
    def setUp(self):
        super().setUp()
        if not frappe.db.exists("DocType", "Stripe Settings"):
            self.skipTest("Stripe Settings (payments app) not installed")

    def test_payment_link(self):
        seed()
        cust = frappe.get_doc({"doctype": "Hosting Customer", "user": make_user(__name__.split(".")[-1]), "status": "Active"}).insert()
        inv = frappe.get_doc(
            {"doctype": "Hosting Invoice", "customer": cust.name, "invoice_items": [{"description": "t", "amount": 100}], "status": "Unpaid"}
        ).insert()
        if not frappe.db.exists("Stripe Settings", "Test"):
            settings = frappe.get_doc(
                {
                    "doctype": "Stripe Settings",
                    "gateway_name": "Test",
                    "publishable_key": "pk_test_bridge",
                    "secret_key": "sk_test_bridge",
                }
            )
            settings.flags.ignore_mandatory = True
            settings.insert(ignore_permissions=True)
        out = payment_link(inv.name, gateway="Stripe")
        self.assertIn(inv.name, out["url"])
        self.assertIn("stripe_checkout", out["url"])
        manual = payment_link(inv.name, gateway="Bank Transfer")
        self.assertTrue(manual["manual"])
        self.assertRaises(frappe.ValidationError, payment_link, inv.name, gateway="CCAvenue")
