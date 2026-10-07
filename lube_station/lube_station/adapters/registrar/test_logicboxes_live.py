"""Live LogicBoxes adapter tests. Transport is faked; no network happens."""

import urllib.parse

import frappe
from frappe.tests import IntegrationTestCase

from lube_station.lube_station.adapters.registrar.logicboxes import LogicBoxesAdapter


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
        self.calls.append({"url": url, "params": dict(urllib.parse.parse_qsl(body))})
        item = self.bodies.pop(0) if len(self.bodies) > 1 else self.bodies[0]
        if isinstance(item, Exception):
            raise item
        return item if isinstance(item, FakeResp) else FakeResp(item)


def ok(**extra):
    return FakeResp({"status": "Success", **extra})


class TestLogicBoxesLiveAdapter(IntegrationTestCase):
    def _account(self):
        name = frappe.db.get_value("Registrar Account", {"registrar": "ResellerClub / LogicBoxes"}, "name")
        if name:
            return name, False
        doc = frappe.get_doc(
            {"doctype": "Registrar Account", "registrar": "ResellerClub / LogicBoxes", "active": 1}
        ).insert(ignore_permissions=True)
        doc.set("api_key", "111")
        doc.set("api_secret", "lbkey")
        doc.save(ignore_permissions=True)
        return doc.name, True

    def _drop(self, name, created):
        if created:
            try:
                frappe.delete_doc("Registrar Account", name, ignore_permissions=True, force=True)
            except Exception:
                pass

    def _ids(self):
        return {
            "customer_id": "7",
            "reg_contact_id": "1",
            "admin_contact_id": "2",
            "tech_contact_id": "3",
            "billing_contact_id": "4",
        }

    def test_availability_and_register(self):
        name, created = self._account()
        try:
            t = FakeTransport(
                [
                    {"example.com": {"status": "available"}},
                    {"status": "Success", "price": 0},
                ]
            )
            out = LogicBoxesAdapter().check_availability("example.com", transport=t)
            self.assertEqual(out["status"], "available")
            self.assertIn("test.httpapi.com", t.calls[0]["url"])
            self.assertEqual(t.calls[0]["params"]["auth-userid"], "111")

            t = FakeTransport([{"taken.com": {"status": "regthroughothers"}}])
            self.assertEqual(
                LogicBoxesAdapter().check_availability("taken.com", transport=t)["status"], "taken"
            )

            t = FakeTransport([ok(entityid="9")])
            out = LogicBoxesAdapter().register_domain("n.com", self._ids(), ["ns1.x"], transport=t)
            self.assertEqual(out["registered"], "n.com")
            self.assertIn("domains/register.json", t.calls[0]["url"])
            self.assertEqual(t.calls[0]["params"]["invoice-option"], "NoInvoice")
        finally:
            self._drop(name, created)

    def test_transfer_renew_ns(self):
        name, created = self._account()
        try:
            t = FakeTransport([ok(entityid="9")])
            out = LogicBoxesAdapter().transfer_domain("t.com", "epp1", transport=t, contacts=self._ids())
            self.assertEqual(out["transferred"], "t.com")
            self.assertIn("domains/transfer.json", t.calls[0]["url"])
            self.assertEqual(t.calls[0]["params"]["auth-code"], "epp1")

            t = FakeTransport(
                [
                    {"status": "Success", "response": "555"},
                    {"status": "Success", "endtime": 1900000000},
                    ok(entityid="9"),
                ]
            )
            self.assertEqual(
                LogicBoxesAdapter().renew_domain("r.com", 2, transport=t)["renewed"], "r.com"
            )
            self.assertEqual(t.calls[2]["params"]["exp-date"], "1900000000")

            t = FakeTransport([{"status": "Success", "response": "555"}, ok(entityid="9")])
            out = LogicBoxesAdapter().update_nameservers("x.com", ["ns1.x"], transport=t)
            self.assertEqual(out["nameservers"], ["ns1.x"])
            self.assertIn("domains/modify-ns.json", t.calls[1]["url"])
        finally:
            self._drop(name, created)

    def test_dns_unmapped_and_reject(self):
        self.assertRaises(Exception, LogicBoxesAdapter().create_dns_record, "x.com", {})
        name, created = self._account()
        try:
            t = FakeTransport([{"status": "ERROR", "message": "bad"}])
            self.assertRaises(
                frappe.ValidationError, LogicBoxesAdapter().check_availability, "x.com", transport=t
            )
        finally:
            self._drop(name, created)
