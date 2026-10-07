"""Live Proxmox adapter tests. Transport is faked; no network happens."""

import urllib.parse

import frappe
from frappe.tests import IntegrationTestCase

from lube_station.lube_station.adapters.provisioning.proxmox import ProxmoxAdapter


class FakeResp:
    def __init__(self, body, status_code=200):
        self._body = body
        self.status_code = status_code

    def json(self):
        return self._body


def ok(data=None):
    return FakeResp({"data": data if data is not None else {}})


class FakeTransport:
    def __init__(self, bodies):
        self.bodies = list(bodies)
        self.calls = []

    def __call__(self, method, url, headers, body, timeout, cookies=None):
        self.calls.append(
            {
                "method": method,
                "url": url,
                "auth": (headers or {}).get("Authorization", ""),
                "csrf": (headers or {}).get("CSRFPreventionToken", ""),
                "headers": dict(headers or {}),
                "cookies": dict(cookies or {}),
                "params": dict(urllib.parse.parse_qsl(body or "")),
            }
        )
        item = self.bodies.pop(0) if len(self.bodies) > 1 else self.bodies[0]
        if isinstance(item, Exception):
            raise item
        return item


class TestProxmoxLiveAdapter(IntegrationTestCase):
    def _server(self, username="root@pam!admintoken"):
        name = frappe.db.get_value("Server", {"hostname": "pve-test.local"}, "name")
        if name:
            doc = frappe.get_doc("Server", name)
            if doc.api_username != username:
                doc.api_username = username
                doc.save(ignore_permissions=True)
            return name
        doc = frappe.get_doc(
            {
                "doctype": "Server",
                "hostname": "pve-test.local",
                "ip_address": "10.0.0.13",
                "api_username": username,
                "control_panel": "Custom",
                "status": "Active",
            }
        ).insert(ignore_permissions=True)
        doc.set("api_secret", "toksecret")
        doc.save(ignore_permissions=True)
        return doc.name

    def _service(self, server, vendor_ref="101", node="pve1"):
        group = frappe.db.get_value("Product Group", {"group_name": "PVE Group"}, "name")
        if not group:
            group = frappe.get_doc({"doctype": "Product Group", "group_name": "PVE Group"}).insert().name
        plan = frappe.db.get_value("Hosting Plan", {"plan_name": "PVE Plan"}, "name")
        if not plan:
            plan = frappe.get_doc(
                {
                    "doctype": "Hosting Plan",
                    "plan_name": "PVE Plan",
                    "product_group": group,
                    "product_type": "VPS",
                    "is_active": 1,
                }
            ).insert().name
        cust = frappe.db.get_value("Hosting Customer", {"user": "Administrator"}, "name")
        if not cust:
            cust = frappe.get_doc({"doctype": "Hosting Customer", "user": "Administrator", "status": "Active"}).insert().name
        return frappe.get_doc(
            {
                "doctype": "Service",
                "customer": cust,
                "hosting_plan": plan,
                "server": server,
                "svc_username": "pveuser1",
                "primary_domain": "pveuser1.test",
                "vendor_ref": vendor_ref,
                "node": node,
                "status": "Pending",
            }
        ).insert(ignore_permissions=True).name

    def test_token_auth_and_power(self):
        server = self._server()
        svc = self._service(server)
        try:
            t = FakeTransport([ok({"data": "UPID:1"})])
            out = ProxmoxAdapter().start(svc, transport=t)
            self.assertIn(":8006/api2/json/nodes/pve1/qemu/101/status/start", t.calls[0]["url"])
            self.assertTrue(t.calls[0]["auth"].startswith("PVEAPIToken="))
            self.assertEqual(out["action"], "start")

            t = FakeTransport([ok({})])
            ProxmoxAdapter().stop(svc, transport=t)
            self.assertIn("/status/stop", t.calls[0]["url"])

            t = FakeTransport([ok({})])
            self.assertEqual(
                ProxmoxAdapter().terminate_account(svc, transport=t)["terminated"],
                ProxmoxAdapter()._service(svc).name,
            )
            self.assertEqual(t.calls[0]["method"], "DELETE")
        finally:
            frappe.delete_doc("Service", svc, ignore_permissions=True, force=True)

    def test_ticket_auth_and_usage(self):
        server = self._server("root@pam")
        svc = self._service(server)
        try:
            bodies = [{"mem": 512, "disk": 2048, "netin": 100, "uptime": 3600}]

            class TicketTransport(FakeTransport):
                def __call__(self, method, url, headers, body, timeout, cookies=None):
                    if url.endswith("/access/ticket"):
                        self.calls.append({"method": method, "url": url, "ticket": True})
                        return FakeResp({"data": {"ticket": "TICKET", "CSRFPreventionToken": "CSRF"}})
                    return super().__call__(method, url, headers, body, timeout, cookies)

            t = TicketTransport([ok(bodies[0])])
            out = ProxmoxAdapter().get_usage(svc, transport=t)
            self.assertEqual(out, {"disk": 2048, "bandwidth": 100, "memory": 512, "uptime": 3600})
            self.assertTrue(t.calls[0].get("ticket"))
            usage_call = t.calls[1]
            self.assertIn("/status/current", usage_call["url"])
            self.assertEqual(usage_call["cookies"], {"PVEAuthCookie": "TICKET"})
            self.assertEqual(usage_call["headers"].get("CSRFPreventionToken"), "CSRF")
        finally:
            frappe.delete_doc("Service", svc, ignore_permissions=True, force=True)

    def test_reject_and_missing_ref(self):
        server = self._server()
        svc = self._service(server, vendor_ref="")
        try:
            self.assertRaises(Exception, ProxmoxAdapter().start, svc, FakeTransport([ok({})]))
            svc2 = self._service(server)
            try:
                t = FakeTransport([FakeResp({"errors": "x"}, 400)])
                self.assertRaises(
                    frappe.ValidationError, ProxmoxAdapter().start, svc2, transport=t
                )
            finally:
                frappe.delete_doc("Service", svc2, ignore_permissions=True, force=True)
        finally:
            frappe.delete_doc("Service", svc, ignore_permissions=True, force=True)
