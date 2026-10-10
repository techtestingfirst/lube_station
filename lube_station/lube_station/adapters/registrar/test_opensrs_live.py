"""Live OpenSRS adapter tests. Transport is faked; no network happens."""

import frappe
from frappe.tests import IntegrationTestCase

from lube_station.lube_station.adapters.registrar.opensrs import OpenSrsAdapter, _signature


class FakeResp:
    def __init__(self, body, status_code=200):
        self._body = body
        self.status_code = status_code

    def json(self):
        return self._body


class FakeTransport:
    def __init__(self, bodies):
        self.bodies = list(bodies)
        self.calls = []

    def __call__(self, url, headers, body, timeout):
        import json

        self.calls.append({"url": url, "headers": headers, "body": json.loads(body)})
        item = self.bodies.pop(0) if len(self.bodies) > 1 else self.bodies[0]
        if isinstance(item, Exception):
            raise item
        return item


def ok(attrs=None):
    return FakeResp({"response_code": 200, "response_text": "OK", "attributes": attrs or {}})


class TestOpenSrsLiveAdapter(IntegrationTestCase):
    def _account(self):
        from lube_station.lube_station.adapters.seed import seed

        seed()
        name = frappe.db.get_value("Registrar Account", {"registrar": "OpenSRS"}, "name")
        if name:
            return name, False
        doc = frappe.get_doc(
            {"doctype": "Registrar Account", "registrar": "OpenSRS", "active": 1}
        ).insert(ignore_permissions=True)
        doc.set("api_key", "reseller1")
        doc.set("api_secret", "key123")
        doc.save(ignore_permissions=True)
        return doc.name, True

    def _drop(self, name, created):
        if created:
            try:
                frappe.delete_doc("Registrar Account", name, ignore_permissions=True, force=True)
            except Exception:
                pass

    def test_signature_and_headers(self):
        name, created = self._account()
        try:
            t = FakeTransport([ok({"status": "available"})])
            out = OpenSrsAdapter().check_availability("example.com", transport=t)
            self.assertEqual(out["status"], "available")
            call = t.calls[0]
            self.assertIn("horizon.opensrs.net", call["url"])
            self.assertEqual(call["headers"]["X-Username"], "reseller1")
            self.assertRegex(call["headers"]["X-Signature"], r"^[0-9a-f]{32}$")
            self.assertEqual(call["body"]["action"], "lookup")
            self.assertEqual(_signature('{"a":1}', "k"), _signature('{"a":1}', "k"))
            self.assertNotEqual(_signature('{"a":1}', "k"), _signature('{"a":2}', "k"))
        finally:
            self._drop(name, created)

    def test_status_mapping_and_reject(self):
        name, created = self._account()
        try:
            t = FakeTransport([ok({"status": "taken"})])
            self.assertEqual(
                OpenSrsAdapter().check_availability("taken.com", transport=t)["status"], "taken"
            )
            t = FakeTransport([FakeResp({"response_code": 400, "response_text": "bad"})])
            self.assertRaises(
                frappe.ValidationError,
                OpenSrsAdapter().check_availability,
                "bad.com",
                transport=t,
            )
        finally:
            self._drop(name, created)

    def test_register_and_retry(self):
        name, created = self._account()
        try:
            t = FakeTransport([ok({})])
            out = OpenSrsAdapter().register_domain(
                "new.com", {"owner": {"email": "a@b.c"}}, ["ns1.x"], transport=t
            )
            self.assertEqual(out["registered"], "new.com")
            self.assertEqual(t.calls[0]["body"]["action"], "sw_register")

            import requests

            t = FakeTransport([requests.ConnectionError("down"), ok({})])
            OpenSrsAdapter().renew_domain("new.com", 2, transport=t)
            self.assertEqual(len(t.calls), 2)
            self.assertEqual(t.calls[1]["body"]["attributes"]["period"], 2)
        finally:
            self._drop(name, created)

    def test_privacy_unmapped(self):
        self.assertRaises(Exception, OpenSrsAdapter().toggle_privacy, "x.com", True)
