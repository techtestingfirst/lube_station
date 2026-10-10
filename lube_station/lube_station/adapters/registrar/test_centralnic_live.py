"""Live CentralNic adapter tests. Transport is faked; no network happens."""

import frappe
from frappe.tests import IntegrationTestCase

from lube_station.lube_station.adapters.registrar.centralnic import CentralNicAdapter


class FakeResp:
    def __init__(self, body, status_code=200):
        self._body = body
        self.status_code = status_code

    def json(self):
        return self._body


def envelope(prop):
    return FakeResp({"code": 200, "description": "ok", "property": prop})


class FakeTransport:
    def __init__(self, bodies):
        self.bodies = list(bodies)
        self.calls = []

    def __call__(self, method, url, headers, body, timeout):
        import json

        try:
            parsed = json.loads(body or "{}")
        except Exception:
            parsed = {}
        self.calls.append(
            {"method": method, "url": url, "auth": headers.get("Authorization", ""), "body": parsed}
        )
        item = self.bodies.pop(0) if len(self.bodies) > 1 else self.bodies[0]
        if isinstance(item, Exception):
            raise item
        return item if isinstance(item, FakeResp) else FakeResp(item)


class TestCentralNicLiveAdapter(IntegrationTestCase):
    def _account(self):
        from lube_station.lube_station.adapters.seed import seed

        seed()
        name = frappe.db.get_value("Registrar Account", {"registrar": "CentralNic Reseller"}, "name")
        if name:
            return name, False
        doc = frappe.get_doc(
            {"doctype": "Registrar Account", "registrar": "CentralNic Reseller", "active": 1}
        ).insert(ignore_permissions=True)
        doc.set("api_key", "cnruser")
        doc.set("api_secret", "cnrkey")
        doc.save(ignore_permissions=True)
        return doc.name, True

    def _drop(self, name, created):
        if created:
            try:
                frappe.delete_doc("Registrar Account", name, ignore_permissions=True, force=True)
            except Exception:
                pass

    def test_availability_and_auth(self):
        name, created = self._account()
        try:
            t = FakeTransport([envelope({"available": True})])
            out = CentralNicAdapter().check_availability("example.com", transport=t)
            self.assertEqual(out["status"], "available")
            self.assertIn("rest-ote.rrpproxy.net", t.calls[0]["url"])
            self.assertTrue(t.calls[0]["auth"].startswith("Basic "))
            self.assertIn("/domain/example.com/availability", t.calls[0]["url"])

            t = FakeTransport([FakeResp({"code": 500, "description": "nope"})])
            self.assertRaises(
                frappe.ValidationError, CentralNicAdapter().check_availability, "x.com", transport=t
            )
        finally:
            self._drop(name, created)

    def test_register_transfer_renew(self):
        name, created = self._account()
        try:
            t = FakeTransport([envelope({"handle": "P-1"}), envelope({"handle": "P-2"}), envelope({})])
            out = CentralNicAdapter().register_domain("n.com", {}, ["ns1.x"], transport=t)
            self.assertEqual(out["registered"], "n.com")
            create = t.calls[2]
            self.assertEqual(create["method"], "POST")
            self.assertTrue(create["url"].endswith("/domain"))
            self.assertEqual(create["body"]["nameserver"], ["ns1.x"])
            self.assertEqual(create["body"]["ownercontact0"], "P-1")

            t = FakeTransport([envelope({})])
            out = CentralNicAdapter().transfer_domain("t.com", "epp1", transport=t)
            self.assertEqual(out["transferred"], "t.com")
            self.assertEqual(t.calls[0]["body"]["action"], "REQUEST")
            self.assertEqual(t.calls[0]["body"]["auth"], "epp1")

            t = FakeTransport(
                [
                    envelope({"expires": "2027-05-01"}),
                    envelope({}),
                ]
            )
            self.assertEqual(
                CentralNicAdapter().renew_domain("r.com", 2, transport=t)["renewed"], "r.com"
            )
            renew = t.calls[1]
            self.assertEqual(renew["body"], {"expiration": 2027, "period": 2})
        finally:
            self._drop(name, created)

    def test_ns_and_unmapped(self):
        name, created = self._account()
        try:
            t = FakeTransport([envelope({})])
            out = CentralNicAdapter().update_nameservers("x.com", ["ns1.x"], transport=t)
            self.assertEqual(out["nameservers"], ["ns1.x"])
            self.assertEqual(t.calls[0]["method"], "PATCH")
            self.assertRaises(Exception, CentralNicAdapter().toggle_privacy, "x.com", True)
            self.assertRaises(Exception, CentralNicAdapter().create_dns_record, "x.com", {})
        finally:
            self._drop(name, created)
