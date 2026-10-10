import frappe
from frappe.tests import IntegrationTestCase

from lube_station.lube_station.notifications.events import TEMPLATES, fire, notify_customer


class TestNotifyOnce(IntegrationTestCase):
    def test_notify_once(self):
        first = fire("invoice", "INV-TEST-1", "a@test.com")
        second = fire("invoice", "INV-TEST-1", "a@test.com")
        self.assertFalse(first["reused"])
        self.assertTrue(second["reused"])

    def test_whmcs_lifecycle_keys(self):
        # WHMCS parity: all lifecycle events fire once and dedupe.
        for event in ("signup", "order", "invoice", "payment", "welcome", "credentials", "suspension", "unsuspension", "termination", "renewal", "renewal_confirm", "refund", "credit", "domain_registered", "domain_renewed", "support_opened", "affiliate_commission", "download"):
            self.assertIn(event, TEMPLATES)
            ref = f"TEST-{event}-1"
            first = fire(event, ref, "a@test.com", {"service": "SVC-1"})
            second = fire(event, ref, "a@test.com")
            self.assertFalse(first["reused"])
            self.assertTrue(second["reused"])

    def test_unknown_event_rejected(self):
        self.assertRaises(frappe.ValidationError, fire, "nope", "X-1", "a@test.com")

    def test_notify_customer_without_email(self):
        out = notify_customer(None, "invoice", "INV-NO-CUST-1", {"amount": 10})
        self.assertFalse(out["reused"])
        # No recipient: event logged, no mail crash.
