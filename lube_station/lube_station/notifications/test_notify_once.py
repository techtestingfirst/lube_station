from frappe.tests import IntegrationTestCase

from lube_station.lube_station.notifications.events import fire


class TestNotifyOnce(IntegrationTestCase):
    def test_notify_once(self):
        first = fire("invoice", "INV-TEST-1", "a@test.com")
        second = fire("invoice", "INV-TEST-1", "a@test.com")
        self.assertFalse(first["reused"])
        self.assertTrue(second["reused"])
