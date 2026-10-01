import frappe
from frappe.tests import IntegrationTestCase

from lube_station.lube_station.adapters.seed import seed
from lube_station.lube_station.doctype.domain.domain import register_domain, renew_domain, update_nameservers


class TestDomainLifecycle(IntegrationTestCase):
    def test_domain_lifecycle(self):
        seed()
        cust = frappe.get_doc({"doctype": "Hosting Customer", "user": "Administrator", "status": "Active"}).insert()
        register_domain("lifecycletest.com", customer=cust.name, registrar="OpenSRS")
        self.assertEqual(frappe.db.get_value("Domain", "lifecycletest.com", "status"), "Registered")
        update_nameservers("lifecycletest.com", ["ns1.test", "ns2.test"])
        self.assertIn("ns1", frappe.db.get_value("Domain", "lifecycletest.com", "nameservers"))
        renew_domain("lifecycletest.com", years=1)
        self.assertTrue(frappe.db.exists("Hosting Invoice", {"customer": cust.name}))
        rec = frappe.get_doc({"doctype": "DNS Record", "domain": "lifecycletest.com", "record_type": "A", "hostname": "@", "record_value": "1.2.3.4"}).insert()
        self.assertTrue(frappe.db.exists("DNS Record", rec.name))
