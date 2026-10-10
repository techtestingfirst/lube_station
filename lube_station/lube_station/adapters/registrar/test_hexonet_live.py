"""Live HEXONET adapter tests. Transport is faked; no network happens."""

import frappe
from frappe.tests import IntegrationTestCase

from lube_station.lube_station.adapters.registrar.hexonet import (
    HexonetAdapter,
    encode_command,
    parse_response,
)


class FakeResp:
    def __init__(self, text, status_code=200):
        self.text = text
        self.status_code = status_code


def resp(code, props=None):
    lines = ["[RESPONSE]", f"CODE = {code}", "DESCRIPTION = x"]
    for key, vals in (props or {}).items():
        for i, val in enumerate(vals):
            lines.append(f"PROPERTY[{key}][{i}] = {val}")
    lines.append("EOF")
    return FakeResp("\r\n".join(lines) + "\r\n")


class FakeTransport:
    def __init__(self, bodies):
        self.bodies = list(bodies)
        self.calls = []

    def __call__(self, url, headers, body, timeout):
        self.calls.append({"url": url, "body": body})
        item = self.bodies.pop(0) if len(self.bodies) > 1 else self.bodies[0]
        if isinstance(item, Exception):
            raise item
        return item


class TestHexonetLiveAdapter(IntegrationTestCase):
    def _account(self):
        from lube_station.lube_station.adapters.seed import seed

        seed()
        name = frappe.db.get_value("Registrar Account", {"registrar": "HEXONET"}, "name")
        if name:
            return name, False
        doc = frappe.get_doc(
            {"doctype": "Registrar Account", "registrar": "HEXONET", "active": 1}
        ).insert(ignore_permissions=True)
        doc.set("api_key", "hxuser")
        doc.set("api_secret", "hxkey")
        doc.save(ignore_permissions=True)
        return doc.name, True

    def _drop(self, name, created):
        if created:
            try:
                frappe.delete_doc("Registrar Account", name, ignore_permissions=True, force=True)
            except Exception:
                pass

    def test_protocol_roundtrip(self):
        body = encode_command("CheckDomain", {"s_login": "u", "DOMAIN": "x.com"})
        self.assertIn("COMMAND = CheckDomain", body)
        self.assertTrue(body.endswith("EOF\r\n"))
        out = parse_response(resp(210, {"REASON": ["available"]}).text)
        self.assertEqual(out["code"], "210")

    def test_availability_and_auth(self):
        name, created = self._account()
        try:
            t = FakeTransport([resp(210, {"REASON": ["ok"]})])
            out = HexonetAdapter().check_availability("example.com", transport=t)
            self.assertEqual(out["status"], "available")
            self.assertIn("api-ote.ispapi.net", t.calls[0]["url"])
            self.assertIn("s_login = hxuser", t.calls[0]["body"])

            t = FakeTransport([resp(211, {"REASON": ["taken"]})])
            self.assertEqual(
                HexonetAdapter().check_availability("example.com", transport=t)["status"], "taken"
            )
        finally:
            self._drop(name, created)

    def test_register_transfer_renew(self):
        name, created = self._account()
        try:
            t = FakeTransport([resp(200, {"CONTACT": ["P-1"]}), resp(200, {"CONTACT": ["P-2"]}), resp(200, {})])
            out = HexonetAdapter().register_domain("n.com", {}, ["ns1.x"], transport=t)
            self.assertEqual(out["registered"], "n.com")
            create = t.calls[2]["body"]
            self.assertIn("COMMAND = AddDomain", create)
            self.assertIn("PERIOD = 1Y", create)
            self.assertIn("NAMESERVER0 = ns1.x", create)

            t = FakeTransport([resp(200, {})])
            out = HexonetAdapter().transfer_domain("t.com", "epp1", transport=t)
            self.assertEqual(out["transferred"], "t.com")
            self.assertIn("AUTH = epp1", t.calls[0]["body"])

            t = FakeTransport(
                [
                    resp(200, {"EXPIRATIONDATE": ["2027-05-01 00:00:00"]}),
                    resp(200, {"EXPIRATIONDATE": ["2028-05-01 00:00:00"]}),
                ]
            )
            self.assertEqual(
                HexonetAdapter().renew_domain("r.com", 2, transport=t)["renewed"], "r.com"
            )
            self.assertIn("EXPIRATION = 2027", t.calls[1]["body"])
        finally:
            self._drop(name, created)
