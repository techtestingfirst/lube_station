import frappe
from frappe.tests import IntegrationTestCase
from unittest.mock import patch

from lube_station.lube_station.adapters.seed import seed
from lube_station.lube_domains.doctype.domain.domain import register_domain, renew_domain, update_nameservers


def _fake_call(self, action, obj, attributes=None, transport=None):
    """Fake vendor HTTP: lifecycle shape is what this test proves."""
    return {"status": "available"}


class TestDomainLifecycle(IntegrationTestCase):
    def test_domain_lifecycle(self):
        seed()
        cust = frappe.get_doc({"doctype": "Hosting Customer", "user": "Administrator", "status": "Active"}).insert()
        with patch(
            "lube_station.lube_station.adapters.registrar.opensrs.OpenSrsAdapter._call", _fake_call
        ):
            register_domain("lifecycletest.com", customer=cust.name, registrar="OpenSRS")
            self.assertEqual(frappe.db.get_value("Domain", "lifecycletest.com", "status"), "Registered")
            update_nameservers("lifecycletest.com", ["ns1.test", "ns2.test"])
            self.assertIn("ns1", frappe.db.get_value("Domain", "lifecycletest.com", "nameservers"))
            renew_domain("lifecycletest.com", years=1)
            self.assertTrue(frappe.db.exists("Hosting Invoice", {"customer": cust.name}))
        rec = frappe.get_doc({"doctype": "DNS Record", "domain": "lifecycletest.com", "record_type": "A", "hostname": "@", "record_value": "1.2.3.4"}).insert()
        self.assertTrue(frappe.db.exists("DNS Record", rec.name))
