import frappe
from frappe.tests import IntegrationTestCase

from lube_station.lube_station.portal.apis import signup_customer


class TestSignup(IntegrationTestCase):
    def test_signup(self):
        out = signup_customer("Portal User", "portal-signup@test.com", "secret123", "Acme", tos_accepted=True)
        self.assertTrue(frappe.db.exists("Hosting Customer", out["customer"]))
        self.assertTrue(frappe.db.exists("User", "portal-signup@test.com"))
        self.assertRaises(frappe.ValidationError, signup_customer, "Dup", "portal-signup@test.com", "secret123", tos_accepted=True)
        self.assertRaises(frappe.ValidationError, signup_customer, "Bad", "not-an-email", "secret123", tos_accepted=True)
        self.assertRaises(frappe.ValidationError, signup_customer, "NoTos", "no-tos@test.com", "secret123")
