"""Live Namecheap adapter tests. Transport is faked; no network happens."""

import urllib.parse
import xml.etree.ElementTree as ET

import frappe
from frappe.tests import IntegrationTestCase

from lube_station.lube_station.adapters.registrar.namecheap import NamecheapAdapter


class FakeResp:
    def __init__(self, text, status_code=200):
        self.text = text
        self.status_code = status_code


def ok(inner=""):
    return FakeResp(
        f'<?xml version="1.0"?><ApiResponse Status="OK"><CommandResponse>{inner}</CommandResponse></ApiResponse>'
    )


class FakeTransport:
    def __init__(self, bodies):
        self.bodies = list(bodies)
        self.calls = []

    def __call__(self, url, headers, body, timeout):
        self.calls.append({"url": url, "params": dict(urllib.parse.parse_qsl(body))})
        item = self.bodies.pop(0) if len(self.bodies) > 1 else self.bodies[0]
        if isinstance(item, Exception):
            raise item
        return item


class TestNamecheapLiveAdapter(IntegrationTestCase):
    def _account(self):
        from lube_station.lube_station.adapters.seed import seed

        seed()
        name = frappe.db.get_value("Registrar Account", {"registrar": "Namecheap"}, "name")
        if name:
            return name, False
        doc = frappe.get_doc(
            {"doctype": "Registrar Account", "registrar": "Namecheap", "active": 1, "client_ip": "127.0.0.1"}
        ).insert(ignore_permissions=True)
        doc.set("api_key", "ncuser")
        doc.set("api_secret", "nckey")
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
            t = FakeTransport([ok('<DomainCheckResult Domain="x.com" Available="true" />')])
            out = NamecheapAdapter().check_availability("x.com", transport=t)
            self.assertEqual(out["status"], "available")
            self.assertIn("sandbox.namecheap.com", t.calls[0]["url"])
            self.assertEqual(t.calls[0]["params"]["Command"], "namecheap.domains.check")

            t = FakeTransport([ok('<DomainCheckResult Domain="x.com" Available="false" />')])
            self.assertEqual(
                NamecheapAdapter().check_availability("x.com", transport=t)["status"], "taken"
            )

            t = FakeTransport([ok("<DomainCreateResult Domain='n.com' Registered='true' />")])
            out = NamecheapAdapter().register_domain("n.com", {}, ["ns1.x"], transport=t)
            self.assertEqual(out["registered"], "n.com")
            self.assertEqual(t.calls[0]["params"]["Nameservers"], "ns1.x")
        finally:
            self._drop(name, created)

    def test_reject_retry_and_dns(self):
        name, created = self._account()
        try:
            t = FakeTransport([FakeResp('<ApiResponse Status="ERROR"><Errors><Error>nope</Error></Errors></ApiResponse>')])
            self.assertRaises(
                frappe.ValidationError, NamecheapAdapter().renew_domain, "x.com", 1, transport=t
            )
            import requests

            t = FakeTransport([requests.ConnectionError("down"), ok("")])
            self.assertEqual(
                NamecheapAdapter().renew_domain("x.com", 2, transport=t)["renewed"], "x.com"
            )
            self.assertEqual(len(t.calls), 2)

            hosts = (
                '<host HostId="1" Name="@" Type="A" Address="1.1.1.1" MXPref="10" TTL="1800" />'
                '<host HostId="2" Name="www" Type="A" Address="2.2.2.2" MXPref="10" TTL="1800" />'
            )
            t = FakeTransport([ok(hosts), ok("")])
            NamecheapAdapter().create_dns_record("x.com", {"host": "mail", "type": "MX", "value": "m.x"}, transport=t)
            push = t.calls[1]["params"]
            self.assertEqual(push["Command"], "namecheap.domains.dns.setHosts")
            self.assertEqual(push["HostName3"], "mail")
            self.assertEqual(push["HostName1"], "@")

            t = FakeTransport([ok(hosts), ok("")])
            NamecheapAdapter().delete_dns_record("x.com", "1", transport=t)
            push = t.calls[1]["params"]
            self.assertNotIn("HostName2", push)
            self.assertEqual(push["HostName1"], "www")
        finally:
            self._drop(name, created)

    def test_privacy_disable_unmapped(self):
        self.assertRaises(Exception, NamecheapAdapter().toggle_privacy, "x.com", False)
