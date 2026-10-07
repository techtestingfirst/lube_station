from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import IntegrationTestCase

from lube_station.lube_station.adapters.seed import seed
from lube_station.lube_domains.doctype.domain.domain import check_availability


class TestDomainAvailability(IntegrationTestCase):
    def test_domain_availability(self):
        seed()
        frappe.cache().delete_value("domain-avail:example-test.com:default")
        first = check_availability("example-test.com")
        self.assertIn(first["status"], ("Available", "Taken", "Premium", "Unknown"))
        second = check_availability("example-test.com")
        self.assertEqual(first, second)
        mock = MagicMock()
        mock.check_availability.return_value = {"domain": "vip.test", "status": "premium", "premium_price": 999}
        with patch("lube_station.lube_station.adapters.registry.get_registrar_adapter", return_value=mock):
            frappe.cache().delete_value("domain-avail:vip.test:OpenSRS")
            out = check_availability("vip.test", registrar="OpenSRS")
            self.assertEqual(out["status"], "Premium")
