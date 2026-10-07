"""Live eNom adapter tests. Transport is faked; no network happens."""

import frappe
from frappe.tests import IntegrationTestCase

from lube_station.lube_station.adapters.registrar.enom import EnomAdapter, split_domain


class FakeResp:
    def __init__(self, text, status_code=200):
        self.text = text
        self.status_code = status_code


def rrp(code, text="ok", extra=""):
    return FakeResp(
        f'<?xml version="1.0"?><interface-response><RRPCode>{code}</RRPCode><RRPText>{text}</RRPText>{extra}</interface-response>'
    )


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
        return item


class TestEnomLiveAdapter(IntegrationTestCase):
    def _account(self):
        name = frappe.db.get_value("Registrar Account", {"registrar": "eNom"}, "name")
        if name:
            return name, False
        doc = frappe.get_doc(
            {"doctype": "Registrar Account", "registrar": "eNom", "active": 1}
        ).insert(ignore_permissions=True)
        doc.set("api_key", "reseller1")
        doc.set("api_secret", "pw123")
        doc.save(ignore_permissions=True)
        return doc.name, True

    def _drop(self, name, created):
        if created:
            try:
                frappe.delete_doc("Registrar Account", name, ignore_permissions=True, force=True)
            except Exception:
                pass

    def test_split_and_availability(self):
        self.assertEqual(split_domain("Example.COM"), ("example", "com"))
        name, created = self._account()
        try:
            t = FakeTransport([rrp("210", "Domain available")])
            out = EnomAdapter().check_availability("example.com", transport=t)
            self.assertEqual(out["status"], "available")
            self.assertIn("resellertest.enom.com", t.calls[0]["url"])
            self.assertEqual(t.calls[0]["params"]["command"], "check")

            t = FakeTransport([rrp("211", "Taken")])
            self.assertEqual(
                EnomAdapter().check_availability("example.com", transport=t)["status"], "taken"
            )
        finally:
            self._drop(name, created)

    def test_register_transfer_renew(self):
        name, created = self._account()
        try:
            t = FakeTransport([rrp("200")])
            out = EnomAdapter().register_domain("n.com", {}, ["ns1.x"], transport=t)
            self.assertEqual(out["registered"], "n.com")
            self.assertEqual(t.calls[0]["params"]["command"], "purchase")
            self.assertEqual(t.calls[0]["params"]["NS1"], "ns1.x")

            t = FakeTransport([rrp("200")])
            out = EnomAdapter().transfer_domain("t.com", "epp1", transport=t)
            self.assertEqual(out["transferred"], "t.com")
            self.assertEqual(t.calls[0]["params"]["AuthInfo"], "epp1")

            t = FakeTransport([rrp("200")])
            self.assertEqual(EnomAdapter().renew_domain("r.com", 2, transport=t)["renewed"], "r.com")
            self.assertEqual(t.calls[0]["params"]["NumYears"], "2")
        finally:
            self._drop(name, created)

    def test_reject_and_retry(self):
        name, created = self._account()
        try:
            t = FakeTransport([rrp("400", "bad")])
            self.assertRaises(
                frappe.ValidationError, EnomAdapter().check_availability, "x.com", transport=t
            )
            import requests

            t = FakeTransport([requests.ConnectionError("down"), rrp("210")])
            self.assertEqual(
                EnomAdapter().check_availability("x.com", transport=t)["status"], "available"
            )
            self.assertEqual(len(t.calls), 2)
        finally:
            self._drop(name, created)
