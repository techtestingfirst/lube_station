"""Live DirectAdmin adapter tests. Transport is faked; no network happens."""

import urllib.parse

import frappe
from frappe.tests import IntegrationTestCase

from lube_station.lube_station.adapters.provisioning.directadmin import DirectAdminAdapter


class FakeResp:
    def __init__(self, text, status_code=200):
        self.text = text
        self.status_code = status_code


def ok(**extra):
    params = {"error": "0", "text": "ok", **{k: str(v) for k, v in extra.items()}}
    return FakeResp(urllib.parse.urlencode(params))


class FakeTransport:
    def __init__(self, bodies):
        self.bodies = list(bodies)
        self.calls = []

    def __call__(self, url, headers, body, timeout):
        self.calls.append(
            {"url": url, "auth": headers.get("Authorization", ""), "params": dict(urllib.parse.parse_qsl(body))}
        )
        item = self.bodies.pop(0) if len(self.bodies) > 1 else self.bodies[0]
        if isinstance(item, Exception):
            raise item
        return item


class TestDirectAdminLiveAdapter(IntegrationTestCase):
    def _server(self):
        name = frappe.db.get_value("Server", {"hostname": "da-test.local"}, "name")
        if name:
            return name
        doc = frappe.get_doc(
            {
                "doctype": "Server",
                "hostname": "da-test.local",
                "ip_address": "10.0.0.11",
                "api_username": "admin",
                "control_panel": "DirectAdmin",
                "status": "Active",
            }
        ).insert(ignore_permissions=True)
        doc.set("api_secret", "sek123")
        doc.save(ignore_permissions=True)
        return doc.name

    def _service(self, server):
        group = frappe.db.get_value("Product Group", {"group_name": "DA Group"}, "name")
        if not group:
            group = frappe.get_doc({"doctype": "Product Group", "group_name": "DA Group"}).insert().name
        plan = frappe.db.get_value("Hosting Plan", {"plan_name": "DA Plan"}, "name")
        if not plan:
            plan = frappe.get_doc(
                {
                    "doctype": "Hosting Plan",
                    "plan_name": "DA Plan",
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
                "svc_username": "dauser1",
                "primary_domain": "dauser1.test",
                "status": "Pending",
            }
        ).insert(ignore_permissions=True).name

    def test_lifecycle_commands(self):
        server = self._server()
        svc = self._service(server)
        try:
            t = FakeTransport([ok()])
            out = DirectAdminAdapter().create_account(svc, password="Pw12345678!", transport=t)
            self.assertEqual(out["created"], "dauser1")
            self.assertIn("CMD_API_ACCOUNT_USER", t.calls[0]["url"])
            self.assertTrue(t.calls[0]["auth"].startswith("Basic "))
            self.assertEqual(t.calls[0]["params"]["username"], "dauser1")
            self.assertEqual(t.calls[0]["params"]["action"], "create")

            t = FakeTransport([ok()])
            DirectAdminAdapter().suspend_account(svc, transport=t)
            self.assertIn("CMD_API_SELECT_USERS", t.calls[0]["url"])
            self.assertEqual(t.calls[0]["params"]["suspend"], "Suspend")

            t = FakeTransport([ok()])
            DirectAdminAdapter().unsuspend_account(svc, transport=t)
            self.assertEqual(t.calls[0]["params"]["suspend"], "Unsuspend")

            t = FakeTransport([ok()])
            self.assertEqual(
                DirectAdminAdapter().terminate_account(svc, transport=t)["terminated"], "dauser1"
            )
            self.assertEqual(t.calls[0]["params"]["delete"], "yes")
        finally:
            frappe.delete_doc("Service", svc, ignore_permissions=True, force=True)

    def test_reject_retry_usage(self):
        server = self._server()
        t = FakeTransport([FakeResp("error=1&text=nope")])
        self.assertRaises(
            frappe.ValidationError, DirectAdminAdapter().test_connection, server, transport=t
        )
        import requests

        t = FakeTransport([requests.ConnectionError("down"), ok()])
        self.assertTrue(DirectAdminAdapter().test_connection(server, transport=t)["ok"])
        self.assertEqual(len(t.calls), 2)

        svc = self._service(server)
        try:
            t = FakeTransport([ok(bandwidth="100", quota="500")])
            self.assertEqual(
                DirectAdminAdapter().get_usage(svc, transport=t),
                {"disk": 500.0, "bandwidth": 100.0},
            )
            self.assertIn("CMD_API_SHOW_USER_USAGE", t.calls[0]["url"])
        finally:
            frappe.delete_doc("Service", svc, ignore_permissions=True, force=True)

    def test_missing_credentials(self):
        name = frappe.get_doc(
            {"doctype": "Server", "hostname": "danocred.local", "status": "Active"}
        ).insert(ignore_permissions=True).name
        try:
            self.assertRaises(Exception, DirectAdminAdapter().test_connection, name, transport=FakeTransport([ok()]))
        finally:
            frappe.delete_doc("Server", name, ignore_permissions=True, force=True)

    def test_create_sso_session(self):
        server = self._server()
        svc = self._service(server)
        try:
            t = FakeTransport([ok()])
            out = DirectAdminAdapter().create_sso_session(svc, transport=t)
            self.assertIn("CMD_API_LOGIN_KEYS", t.calls[0]["url"])
            self.assertEqual(t.calls[0]["params"]["user"], "dauser1")
            self.assertTrue(out["url"].startswith("https://"))
            self.assertIn("CMD_LOGIN", out["url"])
        finally:
            frappe.delete_doc("Service", svc, ignore_permissions=True, force=True)
