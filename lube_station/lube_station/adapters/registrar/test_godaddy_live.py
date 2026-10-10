"""Live GoDaddy adapter tests. Transport is faked; no network happens."""

import frappe
from frappe.tests import IntegrationTestCase

from lube_station.lube_station.adapters.registrar.godaddy import GodaddyAdapter


class FakeResp:
    def __init__(self, body, status_code=200):
        self._body = body
        self.status_code = status_code
        self.text = "" if body is None else "x"

    def json(self):
        return self._body


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
        self.calls.append({"method": method, "url": url, "auth": headers.get("Authorization", ""), "body": parsed})
        item = self.bodies.pop(0) if len(self.bodies) > 1 else self.bodies[0]
        if isinstance(item, Exception):
            raise item
        return item


class TestGodaddyLiveAdapter(IntegrationTestCase):
    def _account(self):
        from lube_station.lube_station.adapters.seed import seed

        seed()
        name = frappe.db.get_value("Registrar Account", {"registrar": "GoDaddy"}, "name")
        if name:
            return name, False
        doc = frappe.get_doc(
            {"doctype": "Registrar Account", "registrar": "GoDaddy", "active": 1}
        ).insert(ignore_permissions=True)
        doc.set("api_key", "gdkey")
        doc.set("api_secret", "gdsecret")
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
            t = FakeTransport([FakeResp({"available": True, "price": 12000000, "period": 1})])
            out = GodaddyAdapter().check_availability("x.com", transport=t)
            self.assertEqual(out["status"], "available")
            self.assertEqual(out["premium_price"], 12.0)
            self.assertIn("api.ote-godaddy.com", t.calls[0]["url"])
            self.assertTrue(t.calls[0]["auth"].startswith("sso-key gdkey:"))

            t = FakeTransport([FakeResp({"available": False})])
            self.assertEqual(
                GodaddyAdapter().check_availability("x.com", transport=t)["status"], "taken"
            )
        finally:
            self._drop(name, created)

    def test_register_transfer_renew(self):
        name, created = self._account()
        try:
            t = FakeTransport([FakeResp([]), FakeResp(None, 204)])
            out = GodaddyAdapter().register_domain("n.com", {}, ["ns1.x"], transport=t)
            self.assertEqual(out["registered"], "n.com")
            purchase = t.calls[1]
            self.assertIn("/v1/domains/purchase", purchase["url"])
            self.assertEqual(purchase["body"]["domain"], "n.com")
            self.assertIn("consent", purchase["body"])

            t = FakeTransport([FakeResp([]), FakeResp(None, 204)])
            out = GodaddyAdapter().transfer_domain("t.com", "epp1", transport=t)
            self.assertEqual(out["transferred"], "t.com")
            self.assertIn("/v1/domains/t.com/transfer", t.calls[1]["url"])
            self.assertEqual(t.calls[1]["body"]["authCode"], "epp1")

            t = FakeTransport([FakeResp(None, 204)])
            self.assertEqual(
                GodaddyAdapter().renew_domain("r.com", 2, transport=t)["renewed"], "r.com"
            )
        finally:
            self._drop(name, created)

    def test_ns_privacy_dns(self):
        name, created = self._account()
        try:
            t = FakeTransport([FakeResp(None, 204)])
            GodaddyAdapter().update_nameservers("x.com", ["ns1.x"], transport=t)
            self.assertEqual(t.calls[0]["body"], {"nameServers": ["ns1.x"]})

            t = FakeTransport([FakeResp(None, 204)])
            GodaddyAdapter().toggle_privacy("x.com", True, transport=t)
            self.assertEqual(t.calls[0]["body"], {"exposeWhois": False})

            recs = [{"type": "A", "name": "@", "data": "1.1.1.1", "ttl": 600}]
            t = FakeTransport([FakeResp(recs), FakeResp(None, 204)])
            GodaddyAdapter().create_dns_record("x.com", {"host": "www", "type": "A", "value": "2.2.2.2"}, transport=t)
            put = t.calls[1]
            self.assertEqual(len(put["body"]), 2)
            self.assertEqual(put["body"][1]["name"], "www")
        finally:
            self._drop(name, created)
