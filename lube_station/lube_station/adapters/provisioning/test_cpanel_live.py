"""Live cPanel adapter tests. Transport is faked; no network happens."""

import frappe
from frappe.tests import IntegrationTestCase

from lube_station.lube_station.adapters.provisioning.cpanel import CpanelWhmAdapter


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

    def __call__(self, url, headers, params, timeout):
        self.calls.append({"url": url, "auth": headers.get("Authorization"), "params": params})
        body = self.bodies.pop(0) if len(self.bodies) > 1 else self.bodies[0]
        if isinstance(body, Exception):
            raise body
        return body


def ok(data=None):
    return FakeResp({"metadata": {"result": 1}, "data": data or {}})


class TestCpanelLiveAdapter(IntegrationTestCase):
    def _server(self):
        name = frappe.db.get_value("Server", {"hostname": "whm-test.local"}, "name")
        if name:
            return name
        doc = frappe.get_doc(
            {
                "doctype": "Server",
                "hostname": "whm-test.local",
                "ip_address": "10.0.0.9",
                "api_username": "root",
                "control_panel": "cPanel / WHM",
                "status": "Active",
            }
        ).insert(ignore_permissions=True)
        doc.set("api_secret", "tok123")
        doc.save(ignore_permissions=True)
        return doc.name

    def _service(self, server):
        group = frappe.db.get_value("Product Group", {"group_name": "WHM Group"}, "name")
        if not group:
            group = frappe.get_doc({"doctype": "Product Group", "group_name": "WHM Group"}).insert().name
        plan = frappe.db.get_value("Hosting Plan", {"plan_name": "WHM Plan"}, "name")
        if not plan:
            plan = frappe.get_doc(
                {
                    "doctype": "Hosting Plan",
                    "plan_name": "WHM Plan",
                    "product_group": group,
                    "product_type": "Shared Hosting",
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
                "svc_username": "whmuser1",
                "primary_domain": "whmuser1.test",
                "status": "Pending",
            }
        ).insert(ignore_permissions=True).name

    def test_lifecycle_calls_whm(self):
        server = self._server()
        svc = self._service(server)
        try:
            t = FakeTransport([ok()])
            out = CpanelWhmAdapter().create_account(svc, password="Pw12345678!", transport=t)
            self.assertEqual(out["created"], "whmuser1")
            call = t.calls[0]
            self.assertIn("/json-api/createacct", call["url"])
            self.assertTrue(call["auth"].startswith("whm root:"))
            self.assertEqual(call["params"]["user"] if "user" in call["params"] else call["params"]["username"], "whmuser1")

            t = FakeTransport([ok()])
            self.assertEqual(CpanelWhmAdapter().suspend_account(svc, transport=t)["suspended"], "whmuser1")
            self.assertIn("suspendacct", t.calls[0]["url"])

            t = FakeTransport([ok()])
            self.assertEqual(CpanelWhmAdapter().unsuspend_account(svc, transport=t)["unsuspended"], "whmuser1")

            t = FakeTransport([ok()])
            self.assertEqual(CpanelWhmAdapter().terminate_account(svc, transport=t)["terminated"], "whmuser1")
        finally:
            frappe.delete_doc("Service", svc, ignore_permissions=True, force=True)

    def test_reject_and_retry(self):
        server = self._server()
        t = FakeTransport([FakeResp({"metadata": {"result": 0, "reason": "exists"}})])
        self.assertRaises(
            frappe.ValidationError, CpanelWhmAdapter().test_connection, server, transport=t
        )
        import requests

        t = FakeTransport([requests.ConnectionError("down"), ok()])
        out = CpanelWhmAdapter().test_connection(server, transport=t)
        self.assertTrue(out["ok"])
        self.assertEqual(len(t.calls), 2)

    def test_missing_credentials(self):
        name = frappe.get_doc(
            {"doctype": "Server", "hostname": "nocred.local", "status": "Active"}
        ).insert(ignore_permissions=True).name
        try:
            self.assertRaises(Exception, CpanelWhmAdapter().test_connection, name, transport=FakeTransport([ok()]))
        finally:
            frappe.delete_doc("Server", name, ignore_permissions=True, force=True)
