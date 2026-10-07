import frappe
from frappe.tests import IntegrationTestCase

from lube_station.lube_station.settings import gateway_order, get_setting


class TestSettings(IntegrationTestCase):
    def test_defaults_before_save(self):
        self.assertEqual(get_setting("domain_year_price"), 15)
        self.assertEqual(get_setting("tos_required"), 1)
        self.assertEqual(gateway_order(), ["Stripe", "Razorpay", "Bank Transfer"])

    def test_override_applies(self):
        frappe.db.set_single_value("Lube Station Settings", "domain_year_price", 25)
        try:
            self.assertEqual(get_setting("domain_year_price"), 25)
        finally:
            frappe.db.set_single_value("Lube Station Settings", "domain_year_price", 15)

    def test_gateway_order_follows_settings(self):
        frappe.db.set_single_value("Lube Station Settings", "enabled_gateways", "Bank Transfer\nStripe")
        try:
            self.assertEqual(gateway_order(), ["Bank Transfer", "Stripe"])
        finally:
            frappe.db.set_single_value(
                "Lube Station Settings", "enabled_gateways", "Stripe\nRazorpay\nBank Transfer"
            )

    def test_unknown_gateway_dropped(self):
        frappe.db.set_single_value("Lube Station Settings", "enabled_gateways", "Stripe\nPayPal Checkout")
        try:
            self.assertEqual(gateway_order(), ["Stripe"])
        finally:
            frappe.db.set_single_value(
                "Lube Station Settings", "enabled_gateways", "Stripe\nRazorpay\nBank Transfer"
            )

    def test_fraud_rule_zero_disables(self):
        from types import SimpleNamespace

        from lube_station.lube_customers.doctype.order.order import _fraud_score

        frappe.db.set_single_value("Lube Station Settings", "fraud_free_email_score", 0)
        try:
            cart = SimpleNamespace(items=[])
            self.assertEqual(_fraud_score(None, cart), 0)
        finally:
            frappe.db.set_single_value("Lube Station Settings", "fraud_free_email_score", 10)
