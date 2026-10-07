"""Live Virtualizor adapter tests. Transport is faked; no network happens."""

import urllib.parse

import frappe
from frappe.tests import IntegrationTestCase

from lube_station.lube_station.adapters.provisioning.virtualizor import VirtualizorAdapter


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

    def __call__(self, method, url, headers, body, timeout):
        import urllib.parse

        query = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
        if body:
            query.update(dict(urllib.parse.parse_qsl(body)))
        self.calls.append({"method": method, "url": url, "params": query})
        item = self.bodies.pop(0) if len(self.bodies) > 1 else self.bodies[0]
        if isinstance(item, Exception):
            raise item
        return item


def ok(**extra):
    return FakeResp({"title": "Virtual Servers", "done": 1, **extra})


class TestVirtualizorLiveAdapter(IntegrationTestCase):
    def _server(self):
        name = frappe.db.get_value("Server", {"hostname": "virt-test.local"}, "name")
        if name:
            return name
        doc = frappe.get_doc(
            {
                "doctype": "Server",
                "hostname": "virt-test.local",
                "ip_address": "10.0.0.12",
                "api_username": "adminkey",
                "control_panel": "Custom",
                "status": "Active",
            }
        ).insert(ignore_permissions=True)
        doc.set("api_secret", "virtpass")
        doc.save(ignore_permissions=True)
        return doc.name

    def _service(self, server, vendor_ref="46"):
        group = frappe.db.get_value("Product Group", {"group_name": "Virt Group"}, "name")
        if not group:
            group = frappe.get_doc({"doctype": "Product Group", "group_name": "Virt Group"}).insert().name
        plan = frappe.db.get_value("Hosting Plan", {"plan_name": "Virt Plan"}, "name")
        if not plan:
            plan = frappe.get_doc(
                {
                    "doctype": "Hosting Plan",
                    "plan_name": "Virt Plan",
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
                "svc_username": "virtuser1",
                "primary_domain": "virtuser1.test",
                "vendor_ref": vendor_ref,
                "status": "Pending",
            }
        ).insert(ignore_permissions=True).name

    def test_power_lifecycle(self):
        server = self._server()
        svc = self._service(server)
        try:
            t = FakeTransport([ok()])
            self.assertEqual(VirtualizorAdapter().start(svc, transport=t)["action"], "start")
            self.assertIn(":4085/index.php", t.calls[0]["url"])
            self.assertIn("action=start", t.calls[0]["url"])
            self.assertIn("vpsid=46", t.calls[0]["url"])

            t = FakeTransport([ok()])
            VirtualizorAdapter().stop(svc, transport=t)
            self.assertIn("action=stop", t.calls[0]["url"])

            t = FakeTransport([ok()])
            VirtualizorAdapter().suspend_account(svc, transport=t)
            self.assertIn("suspend=46", t.calls[0]["url"])

            t = FakeTransport([ok()])
            VirtualizorAdapter().unsuspend_account(svc, transport=t)
            self.assertIn("unsuspend=46", t.calls[0]["url"])

            t = FakeTransport([ok()])
            self.assertEqual(
                VirtualizorAdapter().terminate_account(svc, transport=t)["terminated"],
                VirtualizorAdapter()._service(svc).name,
            )
        finally:
            frappe.delete_doc("Service", svc, ignore_permissions=True, force=True)

    def test_create_rebuild_usage(self):
        server = self._server()
        svc = self._service(server)
        try:
            t = FakeTransport([ok(vs_info={"vpsid": "46"})])
            out = VirtualizorAdapter().create_account(svc, password="Pw12345678!", osid=88, ips=["10.1.1.5"], transport=t)
            self.assertEqual(out["vpsid"], "46")
            self.assertIn("act=addvs", t.calls[0]["url"])
            self.assertEqual(t.calls[0]["params"]["osid"], "88")

            t = FakeTransport([ok()])
            out = VirtualizorAdapter().rebuild(svc, 88, password="Pw12345678!", transport=t)
            self.assertIn("act=rebuild", t.calls[0]["url"])
            self.assertEqual(t.calls[0]["params"]["newpass"], "Pw12345678!")

            t = FakeTransport([ok(vs={"46": {"used_bandwidth": "3.5", "space": "10"}})])
            out = VirtualizorAdapter().get_usage(svc, transport=t)
            self.assertEqual(out["bandwidth"], "3.5")
        finally:
            frappe.delete_doc("Service", svc, ignore_permissions=True, force=True)

    def test_reject_retry_and_missing_ref(self):
        server = self._server()
        svc = self._service(server, vendor_ref="")
        try:
            self.assertRaises(Exception, VirtualizorAdapter().start, svc, FakeTransport([ok()]))
            import requests

            svc2 = self._service(server)
            try:
                t = FakeTransport([requests.ConnectionError("down"), ok()])
                self.assertEqual(VirtualizorAdapter().start(svc2, transport=t)["action"], "start")
                self.assertEqual(len(t.calls), 2)
            finally:
                frappe.delete_doc("Service", svc2, ignore_permissions=True, force=True)
        finally:
            frappe.delete_doc("Service", svc, ignore_permissions=True, force=True)
