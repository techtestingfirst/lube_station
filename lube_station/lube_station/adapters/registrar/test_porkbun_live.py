"""Live Porkbun adapter tests. Transport is faked; no network happens."""

import frappe
from frappe.tests import IntegrationTestCase

from lube_station.lube_station.adapters.registrar.porkbun import PorkbunAdapter


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
        import json

        try:
            parsed = json.loads(body or "{}")
        except Exception:
            parsed = {}
        self.calls.append({"url": url, "body": parsed})
        item = self.bodies.pop(0) if len(self.bodies) > 1 else self.bodies[0]
        if isinstance(item, Exception):
            raise item
        return item if isinstance(item, FakeResp) else FakeResp(item)


class TestPorkbunLiveAdapter(IntegrationTestCase):
    def _account(self):
        from lube_station.lube_station.adapters.seed import seed

        seed()
        name = frappe.db.get_value("Registrar Account", {"registrar": "Porkbun"}, "name")
        if name:
            return name, False
        doc = frappe.get_doc(
            {"doctype": "Registrar Account", "registrar": "Porkbun", "active": 1}
        ).insert(ignore_permissions=True)
        doc.set("api_key", "pk1_test")
        doc.set("api_secret", "sk1_test")
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
            t = FakeTransport([ok(response={"available": "available", "premium": False})])
            out = PorkbunAdapter().check_availability("example.com", transport=t)
            self.assertEqual(out["status"], "available")
            self.assertIn("/domain/checkDomain/example.com", t.calls[0]["url"])
            self.assertEqual(t.calls[0]["body"]["apikey"], "pk1_test")

            dry = {"status": "SUCCESS", "dryRun": True, "wouldSucceed": True, "operation": "registration", "cost": 973}
            t = FakeTransport([dry, ok(domain="n.com", cost=973, orderId=5)])
            out = PorkbunAdapter().register_domain("n.com", {}, ["ns1.x"], transport=t)
            self.assertEqual(out["cost"], 973)
            self.assertEqual(t.calls[1]["body"]["cost"], 973)
            self.assertEqual(t.calls[1]["body"]["agreeToTerms"], "yes")
        finally:
            self._drop(name, created)

    def test_transfer_renew_ns(self):
        name, created = self._account()
        try:
            dry = {"status": "SUCCESS", "dryRun": True, "wouldSucceed": True, "cost": 999}
            t = FakeTransport([dry, ok(domain="t.com", orderId=6)])
            out = PorkbunAdapter().transfer_domain("t.com", "epp1", transport=t)
            self.assertEqual(t.calls[1]["body"]["authCode"], "epp1")

            dry = {"status": "SUCCESS", "dryRun": True, "wouldSucceed": True, "cost": 1099}
            t = FakeTransport([dry, ok(domain="r.com", expirationDate="2028-01-01")])
            out = PorkbunAdapter().renew_domain("r.com", 1, transport=t)
            self.assertEqual(out["cost"], 1099)

            t = FakeTransport([ok()])
            out = PorkbunAdapter().update_nameservers("x.com", ["ns1.x"], transport=t)
            self.assertEqual(t.calls[0]["body"]["ns"], ["ns1.x"])
        finally:
            self._drop(name, created)

    def test_dns_and_reject(self):
        name, created = self._account()
        try:
            t = FakeTransport([ok(id="42")])
            out = PorkbunAdapter().create_dns_record("x.com", {"host": "www", "type": "A", "value": "1.2.3.4"}, transport=t)
            self.assertEqual(out["id"], "42")
            self.assertEqual(t.calls[0]["body"]["name"], "www")

            t = FakeTransport([{"status": "ERROR", "message": "nope", "code": "X"}])
            self.assertRaises(
                frappe.ValidationError, PorkbunAdapter().check_availability, "x.com", transport=t
            )
        finally:
            self._drop(name, created)
