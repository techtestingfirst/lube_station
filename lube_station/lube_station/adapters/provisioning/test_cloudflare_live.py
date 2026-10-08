"""Live Cloudflare adapter tests. Transport is faked; no network happens."""

import frappe
from frappe.tests import IntegrationTestCase

from lube_station.lube_station.adapters.provisioning.cloudflare import CloudflareAdapter


class FakeResp:
    def __init__(self, body, status_code=200):
        self._body = body
        self.status_code = status_code

    def json(self):
        return self._body


def ok(result=None):
    return FakeResp({"success": True, "result": result if result is not None else {}})


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


class TestCloudflareLiveAdapter(IntegrationTestCase):
    def _server(self):
        name = frappe.db.get_value("Server", {"hostname": "cf-test.local"}, "name")
        if name:
            return name
        doc = frappe.get_doc(
            {"doctype": "Server", "hostname": "cf-test.local", "ip_address": "10.0.0.16", "control_panel": "Custom", "status": "Active"}
        ).insert(ignore_permissions=True)
        doc.set("api_secret", "cftoken")
        doc.save(ignore_permissions=True)
        return doc.name

    def _service(self, server):
        group = frappe.db.get_value("Product Group", {"group_name": "CF Group"}, "name")
        if not group:
            group = frappe.get_doc({"doctype": "Product Group", "group_name": "CF Group"}).insert().name
        plan = frappe.db.get_value("Hosting Plan", {"plan_name": "CF Plan"}, "name")
        if not plan:
            plan = frappe.get_doc(
                {"doctype": "Hosting Plan", "plan_name": "CF Plan", "product_group": group, "product_type": "Cloud", "is_active": 1}
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
                "svc_username": "cfuser1",
                "primary_domain": "cfuser1.test",
                "status": "Pending",
            }
        ).insert(ignore_permissions=True).name

    def test_create_delete_and_dns(self):
        server = self._server()
        svc = self._service(server)
        try:
            t = FakeTransport([ok({"id": "zone1"})])
            out = CloudflareAdapter().create_account(svc, transport=t)
            self.assertEqual(out["zone_id"], "zone1")
            self.assertTrue(t.calls[0]["url"].endswith("/zones"))
            self.assertTrue(t.calls[0]["auth"].startswith("Bearer "))

            t = FakeTransport([ok([{"id": "zone1"}]), ok({})])
            self.assertEqual(
                CloudflareAdapter().terminate_account(svc, transport=t)["terminated"], "cfuser1.test"
            )
            self.assertIn("/zones/zone1", t.calls[1]["url"])
            self.assertEqual(t.calls[1]["method"], "DELETE")

            t = FakeTransport([ok([{"id": "zone1"}]), ok({"id": "rec1"})])
            out = CloudflareAdapter().add_record(
                svc, {"type": "A", "name": "www", "content": "1.2.3.4"}, transport=t
            )
            self.assertEqual(out["id"], "rec1")
        finally:
            frappe.delete_doc("Service", svc, ignore_permissions=True, force=True)

    def test_reject_retry_and_unmapped(self):
        server = self._server()
        t = FakeTransport([FakeResp({"success": False, "errors": [{"message": "nope"}]})])
        self.assertRaises(
            frappe.ValidationError, CloudflareAdapter().test_connection, server, transport=t
        )
        import requests

        t = FakeTransport([requests.ConnectionError("down"), ok({"id": "tok1"})])
        out = CloudflareAdapter().test_connection(server, transport=t)
        self.assertTrue(out["ok"])
        self.assertEqual(len(t.calls), 2)

        svc = self._service(server)
        try:
            self.assertRaises(Exception, CloudflareAdapter().suspend_account, svc)
        finally:
            frappe.delete_doc("Service", svc, ignore_permissions=True, force=True)
