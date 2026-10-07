"""Live Internet.bs adapter tests. Transport is faked; no network happens."""

import frappe
from frappe.tests import IntegrationTestCase

from lube_station.lube_station.adapters.registrar.internetbs import InternetBsAdapter


class FakeResp:
    def __init__(self, body, status_code=200):
        self._body = body
        self.status_code = status_code

    def json(self):
        return self._body


def ok(**extra):
    return FakeResp({"status": "SUCCESS", **extra})


class FakeTransport:
    def __init__(self, bodies):
        self.bodies = list(bodies)
        self.calls = []

    def __call__(self, url, headers, body, timeout):
        import urllib.parse

        self.calls.append({"url": url, "params": dict(urllib.parse.parse_qsl(body))})
        item = self.bodies.pop(0) if len(self.bodies) > 1 else self.bodies[0]
        if isinstance(item, Exception):
            raise item
        return item if isinstance(item, FakeResp) else FakeResp(item)


class TestInternetBsLiveAdapter(IntegrationTestCase):
    def _account(self):
        name = frappe.db.get_value("Registrar Account", {"registrar": "Internet.bs"}, "name")
        if name:
            return name, False
        doc = frappe.get_doc(
            {"doctype": "Registrar Account", "registrar": "Internet.bs", "active": 1}
        ).insert(ignore_permissions=True)
        doc.set("api_key", "ibsuser")
        doc.set("api_secret", "ibspw")
        doc.save(ignore_permissions=True)
        return doc.name, True

    def _drop(self, name, created):
        if created:
            try:
                frappe.delete_doc("Registrar Account", name, ignore_permissions=True, force=True)
            except Exception:
                pass

    def test_check_and_register(self):
        name, created = self._account()
        try:
            t = FakeTransport([ok(availability="available")])
            out = InternetBsAdapter().check_availability("example.com", transport=t)
            self.assertEqual(out["status"], "available")
            self.assertIn("testapi.internet.bs/Domain/Check", t.calls[0]["url"])
            self.assertEqual(t.calls[0]["params"]["Domain"], "example.com")

            t = FakeTransport([ok()])
            out = InternetBsAdapter().register_domain("n.com", {}, ["ns1.x"], transport=t)
            self.assertEqual(out["registered"], "n.com")
            self.assertIn("Domain/Create", t.calls[0]["url"])
            self.assertEqual(t.calls[0]["params"]["Ns_list"], "ns1.x")
        finally:
            self._drop(name, created)

    def test_transfer_renew_ns_privacy(self):
        name, created = self._account()
        try:
            t = FakeTransport([ok()])
            out = InternetBsAdapter().transfer_domain("t.com", "epp1", transport=t)
            self.assertEqual(t.calls[0]["params"]["transferAuthInfo"], "epp1")

            t = FakeTransport([ok(expiration="2028-01-01"), ok()])
            self.assertEqual(
                InternetBsAdapter().renew_domain("r.com", 2, transport=t)["renewed"], "r.com"
            )
            self.assertEqual(t.calls[1]["params"]["Period"], "2Y")

            t = FakeTransport([ok()])
            InternetBsAdapter().update_nameservers("x.com", ["ns1.x"], transport=t)
            self.assertIn("Domain/Update", t.calls[0]["url"])

            t = FakeTransport([ok()])
            out = InternetBsAdapter().toggle_privacy("x.com", True, transport=t)
            self.assertIn("PrivateWhois/Enable", t.calls[0]["url"])
        finally:
            self._drop(name, created)

    def test_reject_and_retry(self):
        name, created = self._account()
        try:
            t = FakeTransport([FakeResp({"status": "FAILURE", "message": "nope"})])
            self.assertRaises(
                frappe.ValidationError, InternetBsAdapter().check_availability, "x.com", transport=t
            )
            import requests

            t = FakeTransport([requests.ConnectionError("down"), ok(availability="available")])
            self.assertEqual(
                InternetBsAdapter().check_availability("x.com", transport=t)["status"], "available"
            )
            self.assertEqual(len(t.calls), 2)
        finally:
            self._drop(name, created)
