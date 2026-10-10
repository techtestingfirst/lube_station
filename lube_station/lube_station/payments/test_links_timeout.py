import time
from unittest import mock

import frappe
from frappe.tests import IntegrationTestCase

from lube_station.lube_station.payments import links


def _fast(**kwargs):
    return {"gateway": "Test", "url": "http://example.com/pay"}


def _boom(**kwargs):
    frappe.throw("provider blew up")


def _slow(**kwargs):
    time.sleep(5)
    return {"gateway": "Test"}


class TestBoundedGatewayCall(IntegrationTestCase):
    def test_passthrough(self):
        self.assertEqual(links._bounded(_fast)["url"], "http://example.com/pay")

    def test_reraise(self):
        with self.assertRaises(frappe.ValidationError):
            links._bounded(_boom)

    def test_timeout(self):
        with mock.patch.object(links, "GATEWAY_TIMEOUT", 1):
            with self.assertRaises(frappe.ValidationError) as cm:
                links._bounded(_slow)
        self.assertIn("timed out", str(cm.exception))
